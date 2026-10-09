// Браузер обращается к своему origin; адрес backend остаётся на сервере Next.js.
export async function POST(request: Request): Promise<Response> {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ detail: "Тело запроса должно содержать JSON." }, { status: 422 });
  }

  const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${backendUrl.replace(/\/$/, "")}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal: AbortSignal.timeout(300_000),
    });
    const data = await response.json();
    return Response.json(data, { status: response.status });
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "TimeoutError";
    return Response.json(
      { detail: timedOut
        ? "Сервер не завершил анализ за 5 минут. Повторите запрос."
        : "Backend недоступен или вернул некорректный ответ. Проверьте запуск сервера." },
      { status: timedOut ? 504 : 502 },
    );
  }
}
