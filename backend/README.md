# Backend аналитика и Model Checker

`POST /api/analyze` принимает текст требований, строит `BehavioralModel` через
`AnalystAgent`, проверяет её существующим Model Checker и возвращает модель,
`VerificationResult`, контрпример и объяснение. Провайдер задаётся интерфейсом
`LLMProvider`. Доступны `FakeLLMProvider` для локальных тестов без сети и
`OpenRouterProvider` и `MAIProvider` для работы с внешними моделями через HTTPS.
Формальную проверку во всех режимах выполняет только TLC.

`FakeLLMProvider` поддерживает только демонстрационный сценарий заявки с отменой.
По умолчанию он возвращает модель с ошибкой: `Cancel` сохраняет `approved = true`.
Если в тексте явно указать `approved = false`, провайдер добавит исправляющий
эффект в `Cancel`. Для других предметных областей API возвращает HTTP 422.

Провайдер выбирается переменной `LLM_PROVIDER`: `fake` по умолчанию или
`mai` либо `openrouter`. `OpenRouterProvider` читает `OPENROUTER_API_KEY` и
`OPENROUTER_MODEL` из переменных окружения либо из локального `backend/.env`;
переменные окружения имеют приоритет. Файл `.env` исключён из Git. Для
бесплатного роутера можно задать `OPENROUTER_MODEL=openrouter/free`. У OpenRouter
запрашивается JSON-объект, который затем проходит проверку Pydantic и валидатора
`BehavioralModel`. Невалидный ответ или ошибка OpenRouter возвращают HTTP 502.

Если модель уже проверена, ошибка или пустой ответ при генерации объяснения
не теряют результат: API возвращает HTTP 200 с исходными моделью, статусом,
статистикой и трассой TLC. В `explanation` приходит явно помеченное русское
«Шаблонное сообщение», без предположений о причине результата и без текста
ошибки провайдера. Checker повторно не запускается. Это правило действует для
всех статусов, включая `TIMEOUT` и `ENGINE_ERROR`; статус не заменяется успехом.
Ошибка построения модели по-прежнему возвращает HTTP 502 без результата анализа.

## LLM МАИ

`LLM_PROVIDER=mai` выбирает API МАИ. В локальном `backend/.env` задайте
`MAI_API_KEY` и `MAI_MODEL=qwen3.6-35b-a3b`. Шаблон без ключей —
[.env.example](.env.example). Окружение имеет приоритет над `.env`.
`MAI_BASE_URL` по умолчанию `https://api-ai.mai.ru` (без `/v1`),
`MAI_TIMEOUT_SECONDS` — 90 секунд на один запрос. Ключ остаётся на backend.
`fake` остаётся режимом по умолчанию; OpenRouter доступен как альтернатива.

Контракт проверен по [официальному OpenAPI МАИ](https://api-ai.mai.ru/openapi.json)
и реальным запросам 16.10.2026: `POST /v1/chat/completions`, заголовок
`x-litellm-api-key`, `model/messages`, `stream=false`, ответ
`choices[0].message.content` с `finish_reason=stop`. При построении модели
передаётся `response_format={"type":"json_object"}`, `temperature=0`,
`max_tokens=8192`. Опция OpenRouter `provider` сюда не отправляется.
TLS проверяется через системные доверенные сертификаты, перенаправления
автоматически не выполняются. Параметры и поддержка моделей зависят от сервиса;
универсальная совместимость со всеми маршрутами LiteLLM не заявляется.

Отсутствие ключа/модели и некорректные настройки дают HTTP 503. Ошибка
авторизации, rate limit, сеть, timeout, оборванный ответ или невалидная модель
на этапе построения дают HTTP 502 с безопасным сообщением без тела ответа
провайдера. Ошибка объяснения сохраняет результат по правилу выше. Повторных
запросов и автоматического переключения провайдеров нет.

Контрольные сценарии, сравнение моделей и ограничения интерпретации:
[отчёт об оценке](../docs/llm-quality.md). Ручной запуск из `backend/`
с настроенными Java/TLC и локальным ключом:

```powershell
python evaluation/run_mai.py --model qwen3.6-35b-a3b --output ../.local/mai-evaluation.json
```

Этот запуск обращается к внешнему API. Обычный `pytest` использует подмену HTTP;
интеграционные тесты проверяют сохранённые модели настоящим TLC без LLM-запросов.

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

Переходы и свойства могут опционально содержать ссылку на исходное требование:
`"source_reference": {"id": "REQ-1", "fragment": "Заявка после согласования может быть исполнена."}`.
Во входном тексте при этом должен присутствовать маркер `[REQ-1]`, а `fragment` должен
совпадать с фрагментом текста дословно. Подтверждённые ссылки агрегируются в
`related_requirements` результата и трассы. Ссылки не обязательны и не влияют на TLC;
выдуманная ссылка, пустая цитата и повторяющийся используемый маркер отклоняются.
Проверка выполняется до TLC в Analyst Agent и в обоих внешних провайдерах (МАИ/OpenRouter).
Самостоятельный вызов Model Checker не получает исходный текст: в таком случае
проверку цитат вызывающий код выполняет через `validate_source_references`.

Например, для текста `[REQ-1] Заявка после согласования может быть исполнена.`
ответ может содержать:

```json
{
  "behavioral_model": {
    "transitions": [{
      "name": "Approve",
      "source_reference": {
        "id": "REQ-1",
        "fragment": "Заявка после согласования может быть исполнена."
      }
    }]
  },
  "verification_result": {
    "related_requirements": [{
      "id": "REQ-1",
      "fragment": "Заявка после согласования может быть исполнена."
    }]
  }
}
```

Интеграционные тесты запускают настоящий TLC. Если Java или JAR не настроены,
тесты Model Checker помечаются как пропущенные. Тесты API используют локальные
файлы в `.tools/`, если они доступны.
