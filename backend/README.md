# Ядро Model Checker

Backend проверяет конечную `BehavioralModel`, генерирует модуль TLA+ и конфигурацию
TLC, запускает TLC через Java и возвращает структурированный `VerificationResult`.
Схема входного JSON показана в `tests/fixtures/buggy_model.json` и
`tests/fixtures/fixed_model.json`.

Имена переменных, переходов и свойств — ASCII-идентификаторы. Значения `enum` —
непустые печатные ASCII-строки. Для `integer` нужны включительные границы `min`
и `max`.

Для запуска требуются Python 3.11+, Pydantic v2, Java и `tla2tools.jar` из TLA+
Tools. Пути и ограничения задаются переменными окружения:

- `MODEL_CHECKER_JAVA` — команда `java` или путь к исполняемому файлу;
- `MODEL_CHECKER_TLA2TOOLS_JAR` — путь к `tla2tools.jar`;
- `MODEL_CHECKER_TIMEOUT_SECONDS` — время проверки в секундах, по умолчанию 60;
- `MODEL_CHECKER_TEMP_DIR` — родительский каталог для временных файлов, по
  умолчанию системный каталог.

Использование из каталога `backend/`:

```python
import json
from pathlib import Path

from model_checker import verify

model = json.loads(Path("tests/fixtures/buggy_model.json").read_text(encoding="utf-8"))
result = verify(model)
print(result.model_dump_json(indent=2))
```

TLC получает временные `Model.tla` и `Model.cfg`. При превышении времени процесс
завершается, а результат получает статус `TIMEOUT`. Успех возвращается только
после явного сообщения TLC о завершённой проверке и нулевого кода выхода.
`forbidden_state` компилируется в отрицание проверяемого инварианта.

Для запуска тестов из `backend/`:

```powershell
python -m pytest -q
```

Два интеграционных теста запускают настоящий TLC. Если Java или JAR не настроены,
pytest помечает их как пропущенные.
