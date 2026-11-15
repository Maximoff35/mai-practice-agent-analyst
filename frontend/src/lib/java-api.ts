import type { AnalysisResult, CaseAnalysis, JavaReport } from "./types";

async function request(path: string, method: string, body?: unknown) {
  let response: Response;
  try {
    response = await fetch(path, { method, headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(480_000) });
  } catch {
    throw new Error("Не удалось дождаться ответа сервера. Результат Java не подтверждён.");
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message = typeof data?.detail === "string" ? data.detail : "Сервер отклонил запрос. Повторите анализ.";
    throw new Error(message);
  }
  return data;
}

export async function analyzeCaseRequirements(requirements: string): Promise<{ analysis: AnalysisResult; saved: CaseAnalysis | null }> {
  const data = await request("/api/v2/cases", "POST", { requirements });
  const analysis = data?.analysis ?? data; // Старые сохранённые ответы можно просматривать без Java-допуска.
  if (!analysis?.behavioral_model || !analysis?.verification_result || typeof analysis?.explanation !== "string") {
    throw new Error("Сервер вернул ответ неизвестного формата. Анализ не выполнен.");
  }
  return { analysis, saved: data.case_id && data.model_fingerprint ? data as CaseAnalysis : null };
}

export async function acceptCase(saved: CaseAnalysis): Promise<CaseAnalysis> {
  return request(`/api/v2/cases/${encodeURIComponent(saved.case_id)}/accept`, "POST", {
    case_id: saved.case_id, model_fingerprint: saved.model_fingerprint, accepted: true,
  });
}

export async function generateJava(caseId: string): Promise<JavaReport> {
  const data = await request(`/api/v2/cases/${encodeURIComponent(caseId)}/generate`, "POST");
  if (!data?.status || !data?.model_fingerprint || data.case_id !== caseId) {
    throw new Error("Сервер вернул неподтверждённый результат Java.");
  }
  return data;
}

export async function deleteCase(caseId: string) {
  const response = await fetch(`/api/v2/cases/${encodeURIComponent(caseId)}`, { method: "DELETE" });
  if (!response.ok && response.status !== 404) throw new Error("Удаление не подтверждено сервером");
}
