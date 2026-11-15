import assert from "node:assert/strict";
import test from "node:test";
import { GET, POST, DELETE } from "../src/app/api/v2/cases/[[...segments]]/route.ts";

test("case-прокси сохраняет бинарный ZIP и 204 удаления", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(new Uint8Array([80, 75, 1, 2]), { headers: { "content-type": "application/zip" } });
    const zip = await GET(new Request("http://localhost/api/v2/cases/abc/download"), { params: Promise.resolve({ segments: ["abc", "download"] }) });
    assert.equal(zip.headers.get("content-type"), "application/zip");
    assert.deepEqual([...new Uint8Array(await zip.arrayBuffer())], [80, 75, 1, 2]);
    globalThis.fetch = async () => new Response(null, { status: 204 });
    const response = await DELETE(new Request("http://localhost/api/v2/cases/abc", { method: "DELETE" }), { params: Promise.resolve({ segments: ["abc"] }) });
    assert.equal(response.status, 204);
  } finally { globalThis.fetch = original; }
});

test("case-прокси отклоняет произвольный путь и сохраняет отказ backend", async () => {
  const original = globalThis.fetch;
  try {
    const invalid = await GET(new Request("http://localhost"), { params: Promise.resolve({ segments: ["..", "secret"] }) });
    assert.equal(invalid.status, 404);
    globalThis.fetch = async () => Response.json({ detail: "Модель не принята" }, { status: 409 });
    const response = await POST(new Request("http://localhost", { method: "POST" }), { params: Promise.resolve({ segments: ["abc", "generate"] }) });
    assert.equal(response.status, 409);
  } finally { globalThis.fetch = original; }
});
