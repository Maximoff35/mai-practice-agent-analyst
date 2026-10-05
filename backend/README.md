# Backend аналитика и Model Checker

`POST /api/analyze` принимает текст требований, строит `BehavioralModel` через
`AnalystAgent`, проверяет её существующим Model Checker и возвращает модель,
`VerificationResult`, контрпример и объяснение. Провайдер задаётся интерфейсом
`LLMProvider`. Доступны `FakeLLMProvider` для локальных тестов без сети и
`OpenRouterProvider` для работы с внешней моделью через HTTPS. Формальную
проверку в обоих случаях выполняет только TLC.

`FakeLLMProvider` поддерживает только демонстрационный сценарий заявки с отменой.
По умолчанию он возвращает модель с ошибкой: `Cancel` сохраняет `approved = true`.
Если в тексте явно указать `approved = false`, провайдер добавит исправляющий
эффект в `Cancel`. Для других предметных областей API возвращает HTTP 422.

Провайдер выбирается переменной `LLM_PROVIDER`: `fake` по умолчанию или
`openrouter`. `OpenRouterProvider` читает `OPENROUTER_API_KEY` и
`OPENROUTER_MODEL` из переменных окружения либо из локального `backend/.env`;
переменные окружения имеют приоритет. Файл `.env` исключён из Git. Для
бесплатного роутера можно задать `OPENROUTER_MODEL=openrouter/free`. У OpenRouter
запрашивается JSON-объект, который затем проходит проверку Pydantic и валидатора
`BehavioralModel`. Невалидный ответ или ошибка OpenRouter возвращают HTTP 502.

Backend проверяет конечную `BehavioralModel`, генерирует модуль TLA+ и конфигурацию
TLC, запускает TLC через Java и возвращает структурированный `VerificationResult`.
Схема входного JSON показана в `tests/fixtures/buggy_model.json` и
`tests/fixtures/fixed_model.json`.

Имена переменных, переходов и свойств — ASCII-идентификаторы. Значения `enum` —
непустые печатные ASCII-строки. Для `integer` нужны включительные границы `min`
и `max`.

Для запуска требуются Python 3.11+, Pydantic v2, FastAPI, Uvicorn, HTTPX, Java и
`tla2tools.jar` из TLA+ Tools. Пути и ограничения задаются переменными окружения:

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

Для локального запуска API из `backend/` с уже скачанными инструментами:

```powershell
$env:MODEL_CHECKER_JAVA = (Resolve-Path '.tools/java/bin/java.exe').Path
$env:MODEL_CHECKER_TLA2TOOLS_JAR = (Resolve-Path '.tools/tla2tools.jar').Path
$env:MODEL_CHECKER_TEMP_DIR = (Resolve-Path '.tools').Path
python -m uvicorn api.main:app
```

Для реального OpenRouter перед запуском API установите в этом сеансе
`$env:LLM_PROVIDER = 'openrouter'`. Ключ и модель могут оставаться в `.env`;
их значения не нужно добавлять в командную строку или исходный код.

`GET /health` возвращает `{"status":"ok"}`. Пример запроса к
`POST /api/analyze`:

```json
{
  "requirements": "Заявка после согласования может быть исполнена. Пользователь может отменить заявку до исполнения."
}
```

Для проверки исправленной модели добавьте в `requirements` предложение
`При отмене заявки approved = false.`. Ответ содержит поля `requirements`,
`behavioral_model`, `verification_result`, `counterexample` и `explanation`.

Интеграционные тесты запускают настоящий TLC. Если Java или JAR не настроены,
тесты Model Checker помечаются как пропущенные. Тесты API используют локальные
файлы в `.tools/`, если они доступны.
