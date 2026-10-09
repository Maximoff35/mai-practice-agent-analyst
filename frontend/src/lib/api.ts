import type { AnalysisResult } from "./types";

export async function analyzeRequirements(
  requirements: string,
): Promise<AnalysisResult> {
  let response: Response;
  try {
    response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ requirements }),
      signal: AbortSignal.timeout(310_000),
    });
  } catch {
    throw new Error("Не удалось дождаться ответа сервера. Проверьте соединение и повторите анализ.");
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === "string"
      ? detail
      : Array.isArray(detail)
        ? detail.map((error: { msg?: string }) => error.msg).filter(Boolean).join("; ")
        : null;
    throw new Error(message || `Ошибка анализа (HTTP ${response.status}). Попробуйте ещё раз.`);
  }
  if (!data?.behavioral_model || !data?.verification_result || typeof data.explanation !== "string") {
    throw new Error("Сервер вернул ответ неизвестного формата. Анализ не выполнен.");
  }
  return data as AnalysisResult;
}
