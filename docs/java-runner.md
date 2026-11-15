# Java runner

`backend/java_runner` компилирует автономный Java-артефакт и проверяет его
поведение относительно уже принятой `BehavioralModel`. Runner не получает
произвольные shell-команды от LLM и не запускает Maven/Gradle.

## Артефакт

```json
{
  "model_fingerprint": "model-1",
  "main_class": "Machine",
  "files": [
    {"path": "Machine.java", "content": "..."}
  ]
}
```

Пути только относительные `.java` без `..`, повторов и каталогов за пределами
артефакта. Ограничены количество файлов и размер исходников. Предварительный фильтр запрещённых API — только диагностика. Изоляцию обеспечивает
одноразовый Docker-контейнер: network=none, read-only root, non-root, cap-drop ALL,
no-new-privileges, 1 CPU, 384 MB, 128 PID, ограниченные tmpfs. В контейнер передаются
только временные исходники read-only, без репозитория/.env/ключей/Docker socket.
JVM ограничена 128 MB heap; javac запускается с -proc:none. Полный контракт —
[java-contract.md](java-contract.md).

## Протокол машины

Главный класс запускается фиксированной командой Java внутри контейнера.
На хосте генерируемый Java не запускается.
Он должен поддерживать построчный протокол:

```text
stdout: READY
stdin:  SNAPSHOT
stdout: STATE status=Created;approved=false
stdin:  FIRE Approve
stdout: APPLIED
stdout: STATE status=Approved;approved=true
```

Если guard события ложен, машина обязана вернуть `REJECTED`. Все значения
состояния должны быть представлены в `STATE`; runner проверяет их типы и
конечные домены. После каждого события effects сравниваются с состоянием,
рассчитанным по старому снимку модели, поэтому одновременно проверяются
неизменённые переменные и чтение старого состояния.

## Результат и ограничения

`run_java_module()` возвращает отдельный `JavaCheckResult` со статусами
`PASSED`, `COMPILE_ERROR`, `BEHAVIOR_VIOLATED`, `TIMEOUT`,
`OUTPUT_LIMIT_REACHED`, `CHECK_LIMIT_REACHED`, `ENVIRONMENT_UNAVAILABLE`, `INVALID_ARTIFACT` или
`RUNNER_ERROR`. В результат входят отпечаток артефакта, число проверок,
неудавшееся событие и ограниченный вывод.

Runner проверяет полный достижимый набор состояний только в пределах
`max_checks`; это детерминированная проверка реализации, а не замена TLC и
не формальное доказательство эквивалентности произвольного Java-кода.
Вывод ограничивается во время чтения stdout и stderr, включая javac.
При timeout/ошибке удаляется контейнер со всем деревом процессов, затем временный
каталог. Успех содержит compilation=PASSED и coverage=COMPLETE_STATE_EVENT;
незавершённое покрытие не даёт PASSED. Проверяется и сохранение состояния при REJECTED.


## Подготовка среды

Нужен установленный Docker с Linux daemon. Образ скачивается отдельно оператором:

```powershell
docker pull eclipse-temurin:17-jdk
```

Runner использует `--pull never`: самостоятельно инструменты не скачивает,
при отсутствии среды возвращает ENVIRONMENT_UNAVAILABLE.
Параметры JavaRunnerConfig: docker_executable/docker_image, timeout_seconds
(10 секунд на запуск JVM), total_timeout_seconds (120 секунд на весь артефакт),
max_checks (1000), max_output_bytes (256000 суммарно stdout+stderr на процесс), temp_root.
Компиляция и старт контейнера ограничены 20 секундами каждый. Настройки javac/java
старого локального runner сохранены в сигнатуре только для совместимости,
не дают небезопасного запуска на хосте.

Из backend/ для реальных контейнерных тестов:

```powershell
$env:JAVA_RUNNER_INTEGRATION='1'
python -m pytest -q tests/test_java_runner.py tests/test_java_isolation.py
```

Контроль окружения: `docker ps -a --filter name=mai-java-` после завершения не
должен показывать оставшихся контейнеров. Нельзя запускать одновременно один
и тот же каталог временных исходников вручную или подменять Docker endpoint
недоверенным сервером. Граница изоляции — локальный Docker Linux daemon.
