import assert from "node:assert/strict";
import { test } from "node:test";
import { POST } from "../src/app/api/analyze/route.ts";

function request(body = JSON.stringify({ requirements: "Заявка и отмена" })) {
  return new Request("http://localhost/api/analyze", { method: "POST", body });
}

test("прокси передаёт запрос FastAPI и возвращает его ответ", async (t) => {
  const previous = process.env.BACKEND_URL;
  process.env.BACKEND_URL = "http://127.0.0.1:8123/";
  t.after(() => {
    if (previous === undefined) delete process.env.BACKEND_URL;
    else process.env.BACKEND_URL = previous;
  });
  const result = { verification_result: { status: "TIMEOUT" }, explanation: "Проверка не завершена" };
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "http://127.0.0.1:8123/api/analyze");
    assert.equal(options.method, "POST");
    assert.equal(options.cache, "no-store");
    assert.deepEqual(JSON.parse(options.body), { requirements: "Заявка и отмена" });
    return Response.json(result);
  });
  const response = await POST(request());
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), result);
});

test("прокси сохраняет HTTP-статус и сообщение ошибки backend", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "LLM недоступна" }, { status: 503 }));
  const response = await POST(request());
  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), { detail: "LLM недоступна" });
});

test("невалидный JSON не отправляется в backend", async (t) => {
  const mockedFetch = t.mock.method(globalThis, "fetch", async () => { throw new Error("Не должен вызываться"); });
  assert.equal((await POST(request("{"))).status, 422);
  assert.equal(mockedFetch.mock.callCount(), 0);
});

test("недоступный backend возвращает 502", async (t) => {
  t.mock.method(globalThis, "fetch", async () => { throw new TypeError("ECONNREFUSED"); });
  const response = await POST(request());
  assert.equal(response.status, 502);
  assert.match((await response.json()).detail, /Backend недоступен/);
});

test("timeout прокси возвращает 504", async (t) => {
  t.mock.method(globalThis, "fetch", async () => { throw new DOMException("timeout", "TimeoutError"); });
  const response = await POST(request());
  assert.equal(response.status, 504);
  assert.match((await response.json()).detail, /5 минут/);
});

test("ответ backend вне JSON возвращает 502", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("Bad gateway", { status: 502 }));
  assert.equal((await POST(request())).status, 502);
});
