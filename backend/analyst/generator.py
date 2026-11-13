"""MAI-backed Java artifact generation for an accepted BehavioralModel."""

from __future__ import annotations

import json

from java_runner import JavaArtifact
from model_checker import BehavioralModel

from .config import get_setting
from .mai import MAIConfigurationError, MAIError, MAIProvider


JAVA_GENERATOR_INSTRUCTIONS = """Ты генератор автономной Java-машины состояний.
Верни только один JSON-объект без Markdown:
{
  "model_fingerprint": "...",
  "main_class": "Machine",
  "files": [{"path": "Machine.java", "content": "..."}],
  "instruction": "краткая инструкция протокола"
}

Реализуй только переданную BehavioralModel, не исходный текст отдельно.
Поддержи все variables, initial, transitions, guards и effects модели.
Операции guards: var, eq, in, and, or, not. Effects вычисляются одновременно
по состоянию до перехода; неуказанные переменные сохраняются. Ложный guard
обязан отвечать REJECTED, истинный — APPLIED и затем STATE.
Протокол stdin/stdout: после старта READY; SNAPSHOT -> STATE key=value;...;
FIRE Event -> APPLIED и новое STATE либо REJECTED. Выводи все переменные в
каждом STATE и используй true/false для boolean.
Сделай автономный исходник без package, Maven, Gradle, сети, файлов, subprocess,
reflection и внешних зависимостей. Не добавляй переходы, переменные или правила,
которых нет в модели. Пути файлов — только относительные .java.
"""


class JavaGenerationError(MAIError):
    """The generator response cannot be used as a Java artifact."""


class JavaGenerator:
    def __init__(self, provider: MAIProvider) -> None:
        self.provider = provider
        self.model = provider.model

    @classmethod
    def from_env(cls, *, client=None) -> "JavaGenerator":
        model = get_setting("MAI_GENERATOR_MODEL") or get_setting("MAI_MODEL") or ""
        try:
            timeout = float(get_setting("MAI_TIMEOUT_SECONDS", "90") or "90")
        except ValueError as error:
            raise MAIConfigurationError("MAI_TIMEOUT_SECONDS должен быть числом") from error
        return cls(
            MAIProvider(
                api_key=get_setting("MAI_API_KEY") or "",
                model=model,
                base_url=get_setting("MAI_BASE_URL") or "https://api-ai.mai.ru",
                timeout_seconds=timeout,
                client=client,
            )
        )

    def generate(
        self,
        requirements: str,
        model: BehavioralModel,
        model_fingerprint: str,
    ) -> JavaArtifact:
        context = {
            "requirements": requirements,
            "model_fingerprint": model_fingerprint,
            "behavioral_model": model.model_dump(mode="json"),
        }
        try:
            content = self.provider.complete(
                [
                    {"role": "system", "content": JAVA_GENERATOR_INSTRUCTIONS},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
                structured=True,
            )
            artifact = JavaArtifact.model_validate(json.loads(content))
        except MAIError:
            raise
        except (ValueError, TypeError) as error:
            raise JavaGenerationError("API МАИ вернул невалидный Java-артефакт") from error
        if artifact.model_fingerprint != model_fingerprint:
            raise JavaGenerationError("Java-артефакт относится к другой версии BehavioralModel")
        return artifact
