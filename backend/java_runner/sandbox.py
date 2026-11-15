"""Одноразовый Docker-контейнер: JDK без сети, секретов и рабочего репозитория."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from threading import Event, Lock, Thread
import time
from uuid import uuid4


def bounded_process(command: list[str], *, timeout: float, limit: int, data: str = "") -> tuple[int, str, str, str | None]:
    """Ограничить суммарный вывод во время чтения, а не после communicate()."""
    env = {key: value for key, value in os.environ.items() if key.upper() in {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOME",
        "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "DOCKER_CERT_PATH", "DOCKER_TLS_VERIFY",
    }}
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    chunks: list[list[bytes]] = [[], []]
    size = [0]
    exceeded = Event()
    lock = Lock()

    def read(stream, index):
        try:
            while chunk := stream.read1(4096):
                with lock:
                    available = max(0, limit - size[0])
                    if available:
                        chunks[index].append(chunk[:available])
                    size[0] += len(chunk)
                    if size[0] > limit:
                        exceeded.set()
        finally:
            stream.close()

    def write():
        try:
            process.stdin.write(data.encode("utf-8"))
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    readers = [Thread(target=read, args=(process.stdout, 0), daemon=True),
               Thread(target=read, args=(process.stderr, 1), daemon=True)]
    for thread in readers:
        thread.start()
    Thread(target=write, daemon=True).start()
    deadline = time.monotonic() + timeout
    reason = None
    try:
        while process.poll() is None:
            if exceeded.is_set():
                reason = "OUTPUT_LIMIT_REACHED"
                break
            if time.monotonic() >= deadline:
                reason = "TIMEOUT"
                break
            time.sleep(0.01)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for thread in readers:
            thread.join(timeout=2)
    if exceeded.is_set():
        reason = "OUTPUT_LIMIT_REACHED"
    return process.returncode, *(b"".join(part).decode("utf-8", errors="replace") for part in chunks), reason


class DockerSandbox:
    def __init__(self, executable: str, image: str, sources: Path, timeout: float, limit: int):
        self.executable, self.image = executable, image
        self.name = "mai-java-" + uuid4().hex
        self.sources, self.timeout, self.limit = sources, timeout, limit

    def start(self):
        # --pull never: приложение не скачивает инструменты самостоятельно.
        command = [self.executable, "run", "-d", "--pull", "never", "--rm", "--name", self.name,
                   "--network", "none", "--read-only", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges", "--pids-limit", "128",
                   "--memory", "384m", "--memory-swap", "384m", "--cpus", "1",
                   "--user", "65534:65534", "--log-driver", "none",
                   "--tmpfs", "/work:rw,nosuid,nodev,size=64m,mode=1777",
                   "--tmpfs", "/tmp:rw,nosuid,nodev,size=32m,mode=1777",
                   "--mount", f"type=bind,source={self.sources.resolve()},target=/sources,readonly",
                   "--workdir", "/work", self.image, "sleep", "600"]
        code, out, err, reason = bounded_process(command, timeout=min(self.timeout, 20), limit=16_000)
        if code != 0 or reason:
            raise OSError("Изоляция Docker/JDK недоступна: проверьте daemon и локальный образ")

    def execute(self, args: list[str], *, data: str = "", timeout: float | None = None):
        return bounded_process([self.executable, "exec", "-i", self.name, *args],
                               timeout=min(self.timeout, timeout) if timeout is not None else self.timeout,
                               limit=self.limit, data=data)

    def close(self):
        # Удаляет контейнер и всё дерево его процессов, включая потомков JVM.
        code, _, error, reason = bounded_process([self.executable, "rm", "-f", self.name], timeout=15, limit=4000)
        if reason or (code != 0 and "no such container" not in error.lower()):
            raise OSError("Не удалось подтвердить удаление контейнера Java")
