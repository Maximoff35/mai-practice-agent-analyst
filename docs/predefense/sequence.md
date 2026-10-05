# Последовательность анализа требования

Запрос проходит от Frontend через FastAPI и Analyst Agent к Model Checker. После проверки агент получает объяснение через LLMProvider и возвращает полный результат клиенту. Ниже показан сценарий с `OpenRouterProvider`.

```mermaid
sequenceDiagram
    actor U as User
    participant F as Frontend (внешний)
    participant API as FastAPI
    participant A as Analyst Agent
    participant P as LLMProvider / OpenRouterProvider
    participant L as Внешняя LLM
    participant B as BehavioralModel (данные)
    participant C as Model Checker / verify
    participant V as Validator
    participant G as TLA+ Generator
    participant R as TLC Runner
    participant T as TLC
    participant PAR as Result Parser
    participant VR as VerificationResult (данные)

    U->>F: Текст требования
    F->>API: POST /api/analyze {requirements}
    API->>A: analyze(requirements)
    A->>P: build_model(requirements)
    P->>L: Инструкция DSL и текст, запрос JSON
    L-->>P: JSON предполагаемой модели
    P->>V: validate_model(JSON)
    V->>B: Pydantic-разбор схемы
    B-->>V: Объект модели
    V->>V: Типы, домены, ссылки, выражения
    V-->>P: Валидная BehavioralModel
    P-->>A: BehavioralModel
    Note over A,L: Интерпретация текста вероятностная

    A->>C: verify(model)
    C->>V: validate_model(model)
    V-->>C: Проверенная модель
    C->>G: generate_tla(model)
    G->>V: Повторная валидация
    V-->>G: Модель
    G->>G: Компиляция выражений и переходов
    G-->>C: TlaFiles: tla, cfg
    C->>R: Записать временные файлы, запустить процесс
    R->>T: java tlc2.TLC, Model.tla, Model.cfg
    T-->>R: stdout, stderr, exit code
    R->>PAR: parse_tlc_output(..., model, timed_out)
    PAR->>VR: Статус, трасса, статистика, логи
    VR-->>PAR: Объект результата
    PAR-->>C: VerificationResult
    C-->>A: VerificationResult
    Note over C,VR: Проверка формальной модели без LLM

    A->>P: explain_result(requirements, model, result)
    P->>L: Текст, модель, результат и трасса без логов
    L-->>P: Объяснение на русском
    P-->>A: explanation
    A-->>API: AnalysisResult
    API-->>F: HTTP 200, модель, результат, контрпример, объяснение
    F-->>U: Показ результата
```

## Обработка запроса

1. FastAPI принимает непустой `requirements` и передаёт его Analyst Agent.
2. `LLMProvider.build_model` формирует `BehavioralModel`. OpenRouter возвращает JSON, который проходит проверку Pydantic и Validator.
3. Агент вызывает `verify`. Model Checker валидирует модель и генерирует TLA+ с конфигурацией TLC.
4. TLC Runner запускает Java-процесс и контролирует время выполнения. TLC проверяет достижимые состояния.
5. Result Parser формирует `VerificationResult`: статус, статистику и контрпример с переходами.
6. `LLMProvider.explain_result` объясняет результат на языке требований. FastAPI возвращает модель, результат проверки и объяснение в `AnalysisResult`.

С `FakeLLMProvider` модель и объяснение выбираются из фиксированного демонстрационного сценария. Проверка через Validator, Generator и настоящий TLC остаётся той же.

## Обработка ошибок

- Некорректный HTTP-вход или неподдерживаемая тема для fake: HTTP 422. Ошибка конфигурации провайдера: HTTP 503. Ошибка OpenRouter или невалидная модель от LLM: HTTP 502.
- При прямом вызове `verify` невалидная модель даёт `MODEL_INVALID`, отсутствие Java/JAR — `ENGINE_ERROR`.
- При timeout процесс TLC завершается со статусом `TIMEOUT`. Этот статус и `STATE_LIMIT_REACHED` не означают успешную проверку свойства.
- Ошибка генерации объяснения возвращается как HTTP 502 без частичного результата TLC. Повторные запросы и переключение провайдера выполняются вручную.

Поля ответа и настройки описаны в [архитектуре системы](architecture.md).
