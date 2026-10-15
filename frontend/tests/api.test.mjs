import assert from "node:assert/strict";
import { test } from "node:test";
import { analyzeRequirements } from "../src/lib/api.ts";

test("клиент отправляет требования и сохраняет статус проверки backend", async (t) => {
  const statuses = ["PROPERTY_VIOLATED", "PROPERTY_HOLDS", "TIMEOUT", "STATE_LIMIT_REACHED", "MODEL_INVALID", "ENGINE_ERROR"];
  for (const status of statuses) {
    const result = { behavioral_model: { properties: [] }, verification_result: { status }, explanation: "Результат TLC" };
    const mockedFetch = t.mock.method(globalThis, "fetch", async (url, options) => {
      assert.equal(url, "/api/analyze");
      assert.equal(options.method, "POST");
      assert.deepEqual(JSON.parse(options.body), { requirements: "Текст требований" });
      return Response.json(result);
    });
    assert.deepEqual(await analyzeRequirements("Текст требований"), result);
    mockedFetch.mock.restore();
  }
});

test("HTTP-ошибка показывает объяснение backend вместо mock-результата", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "Неподдерживаемый сценарий" }, { status: 422 }));
  await assert.rejects(analyzeRequirements("Лифт"), /Неподдерживаемый сценарий/);
});

test("ошибки валидации FastAPI отображаются пользователю", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: [{ msg: "Поле обязательно" }] }, { status: 422 }));
  await assert.rejects(analyzeRequirements("Текст"), /Поле обязательно/);
});

test("недоступный сервер не выдаёт успешный результат", async (t) => {
  t.mock.method(globalThis, "fetch", async () => { throw new TypeError("Failed to fetch"); });
  await assert.rejects(analyzeRequirements("Текст"), /Проверьте соединение/);
});

test("невалидный ответ сервера отклоняется", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("<html>Ошибка</html>"));
  await assert.rejects(analyzeRequirements("Текст"), /неизвестного формата/);
});
