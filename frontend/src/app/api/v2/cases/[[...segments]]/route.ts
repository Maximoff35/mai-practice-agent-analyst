// Фиксированный API backend; браузер не задаёт серверный адрес и не получает ключи.
async function proxy(request: Request, context: { params: Promise<{ segments?: string[] }> }) {
  const { segments = [] } = await context.params;
  if (segments.length > 2 || segments.some((part) => !/^[A-Za-z0-9_-]+$/.test(part)) ||
      (segments.length === 2 && !["accept", "generate", "download"].includes(segments[1]))) {
    return Response.json({ detail: "Неизвестный маршрут кейса." }, { status: 404 });
  }
  const suffix = segments.map(encodeURIComponent).join("/");
  const backend = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  try {
    const response = await fetch(`${backend}/api/v2/cases${suffix ? "/" + suffix : ""}`, {
      method: request.method,
      headers: { "Content-Type": "application/json" },
      body: request.method === "POST" ? await request.text() : undefined,
      cache: "no-store", signal: AbortSignal.timeout(470_000),
    });
    const headers = new Headers();
    for (const name of ["content-type", "content-disposition"]) {
      const value = response.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new Response(response.status === 204 ? null : response.body, { status: response.status, headers });
  } catch {
    return Response.json({ detail: "Backend недоступен или этап превысил время ожидания. Успех Java не подтверждён." }, { status: 502 });
  }
}

export { proxy as GET, proxy as POST, proxy as DELETE };
