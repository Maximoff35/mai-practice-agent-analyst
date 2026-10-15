# Агент-аналитик — практика МАИ

Учебный MVP команды **it plow**: текст требований → BehavioralModel →
детерминированная проверка TLC → результат, контрпример и объяснение.
Frontend на Next.js подключён к FastAPI через серверный маршрут `/api/analyze`.

## Требования

- Python 3.11+ и Node.js 24;
- Java 11+ и `tla2tools.jar`;
- зависимости Python и npm;
- для OpenRouter — ключ и модель в локальном `backend/.env` либо окружении.

Для воспроизводимой демонстрации используйте `LLM_PROVIDER=fake`: он возвращает
фиксированную модель заявки и шаблонное объяснение, но **проверку выполняет
настоящий TLC**. Произвольные требования в этом режиме не поддерживаются.
Для анализа через внешнюю LLM задайте `LLM_PROVIDER=openrouter`; подробности —
в [инструкции backend](backend/README.md).

## Запуск в двух терминалах

В первом терминале из корня репозитория:

```powershell
cd backend
python -m pip install -e ".[test]"
$env:LLM_PROVIDER = 'fake'
$env:MODEL_CHECKER_JAVA = (Resolve-Path '.tools/java/bin/java.exe').Path
$env:MODEL_CHECKER_TLA2TOOLS_JAR = (Resolve-Path '.tools/tla2tools.jar').Path
$env:MODEL_CHECKER_TEMP_DIR = (Resolve-Path '.tools').Path
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Команды предполагают, что Java и JAR уже размещены в `backend/.tools/`.
Эти инструменты не входят в Git: при другом расположении укажите свои пути
в `MODEL_CHECKER_JAVA` и `MODEL_CHECKER_TLA2TOOLS_JAR`, а временный каталог —
в `MODEL_CHECKER_TEMP_DIR`. Каталог должен существовать и быть доступен для записи.

Во втором терминале из корня репозитория:

```powershell
cd frontend
npm ci
npm run dev
```

Откройте `http://localhost:3000`. По умолчанию Next.js обращается к backend на
`http://127.0.0.1:8000`. Для другого адреса установите `BACKEND_URL` в окружении
сервера Next.js. Ключи OpenRouter остаются в backend.

Для демонстрации production-сборки вместо `npm run dev` выполните
`npm run build`, затем `npm run start`. Первая сборка загружает шрифт Google Fonts.

## Два контрольных сценария

1. Нажмите «Подставить пример», затем «Проанализировать». Ожидаются
   `PROPERTY_VIOLATED`, четыре состояния контрпримера и объяснение причины:
   при отмене сохраняется `approved=true`.
2. Нажмите «Новая модель», добавьте к тексту
   `При отмене заявки approved = false.` и повторите анализ. Ожидается
   `PROPERTY_HOLDS` без контрпримера.

Полный [сценарий предзащиты](docs/predefense/demo.md) включает проверки ошибок.
Модель автоматически не исправляется: изменение правила задаёт пользователь.

## Проверки

Из `backend/` с настроенными Java и TLC:

```powershell
python -m pytest -q
```

Из `frontend/`:

```powershell
npm test
npm run lint
npm run build
```

Интеграционные тесты backend требуют настоящего TLC; без настроенных
инструментов они пропускаются. Тесты OpenRouter подменяют HTTP и не доказывают
стабильность внешних моделей.

## Архитектура и ограничения

[Требования](docs/predefense/requirements.md),
[архитектура](docs/predefense/architecture.md) и
[состояние прототипа](docs/predefense/prototype.md).

[План проекта, milestones и исполнители](docs/roadmap.md): ближайший этап
включает подключение предоставленного API LLM МАИ и оценку формализации.
Интеграция API МАИ пока запланирована; текущие провайдеры — fake и OpenRouter.

Поддерживаются конечные модели с `enum`, `boolean`, ограниченными `integer`
и свойства `invariant`, `forbidden_state`. `reachable`, `deadlock_free`,
ссылки на исходные требования и диалог уточнений ещё не реализованы.
`PROPERTY_HOLDS` относится к выбранным свойствам построенной модели и не
доказывает корректность реальной системы. `TIMEOUT` и `STATE_LIMIT_REACHED`
не подтверждают выполнение свойства.

Рабочая схема Git: `feature/* → develop → main`. `.local/`, `.env` и
локальные инструменты не включаются в коммиты.
