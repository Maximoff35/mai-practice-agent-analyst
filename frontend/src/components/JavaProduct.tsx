"use client";

import { useState } from "react";
import { acceptCase, generateJava } from "@/lib/java-api";
import type { CaseAnalysis, JavaReport } from "@/lib/types";

const STATUS: Record<string, string> = {
  ANALYZED: "Модель ещё не принята", ACCEPTED: "Модель принята", GENERATING: "Генерация Java",
  GENERATED: "Исходники получены", REVIEWED: "Ревью выполнено", READY: "Модуль прошёл обязательные проверки",
  REVIEW_REJECTED: "Ревьюер запросил изменения", JAVA_CHECK_FAILED: "Java-проверки не пройдены",
  PIPELINE_ERROR: "Этап Java не завершён",
};

export default function JavaProduct({ saved, view = "checks" }: { saved: CaseAnalysis | null; view?: "checks" | "code" }) {
  const [confirmed, setConfirmed] = useState(false);
  const [accepted, setAccepted] = useState(saved?.accepted ?? false);
  const [busy, setBusy] = useState<"accept" | "generate" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<JavaReport | null>(null);
  const [selectedFile, setSelectedFile] = useState("");
  const verification = saved?.analysis.verification_result;
  const eligible = verification?.status === "PROPERTY_HOLDS" &&
    (verification.property_results ?? []).every((item) => item.status === "PROPERTY_HOLDS");

  async function accept() {
    if (!saved) return;
    setBusy("accept"); setError(null);
    try {
      const result = await acceptCase(saved);
      if (!result.accepted || result.model_fingerprint !== saved.model_fingerprint) throw new Error("Принятие версии не подтверждено.");
      setAccepted(true);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Не удалось принять модель."); }
    finally { setBusy(null); }
  }

  async function generate() {
    if (!saved) return;
    setBusy("generate"); setError(null); setReport(null);
    try {
      const result = await generateJava(saved.case_id);
      if (result.model_fingerprint !== saved.model_fingerprint) throw new Error("Отчёт относится к другой версии модели.");
      setReport(result);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Не удалось выполнить этап Java."); }
    finally { setBusy(null); }
  }

  const ready = report?.status === "READY" && report.review?.approved &&
    report.compile_and_check?.status === "PASSED" && report.compile_and_check.compilation === "PASSED" &&
    report.compile_and_check.coverage === "COMPLETE_STATE_EVENT";
  const buttonClass = "rounded-xl border border-accent/50 px-4 py-2 text-sm text-accent disabled:opacity-40 disabled:cursor-not-allowed";
  const source = report?.artifact?.files.find((file) => file.path === selectedFile) ?? report?.artifact?.files[0];

  if (view === "code") return <section aria-label="Java-код" className="flex flex-col gap-4 rounded-2xl border border-accent/20 bg-panel p-4 sm:p-6">
    <h2 className="text-lg font-semibold">Java-код</h2>
    {report?.artifact && saved && source ? <>
      <p className="text-sm text-foreground/70">{ready ? "Исходники прошли обязательные проверки." : "Диагностический артефакт; готовность не подтверждена."} Отчёт находится во вкладке «Проверки Java».</p>
      <label className="flex items-center gap-3 text-sm">Файл исходников<select aria-label="Файл исходников" value={source.path} onChange={(event) => setSelectedFile(event.target.value)} className="min-w-0 rounded border border-foreground/20 bg-panel px-3 py-2">
        {report.artifact.files.map((file) => <option key={file.path} value={file.path}>{file.path}</option>)}
      </select></label>
      <pre aria-label={`Исходник ${source.path}`} tabIndex={0} className="max-h-[32rem] overflow-auto rounded-lg border border-foreground/15 p-4 text-xs leading-relaxed">{source.content}</pre>
      <a href={`/api/v2/cases/${encodeURIComponent(saved.case_id)}/download`} download className={buttonClass}>Скачать исходники и отчёт ZIP</a>
      {report.artifact.instruction && <details className="text-sm"><summary className="cursor-pointer">Инструкция модуля</summary><p className="whitespace-pre-wrap text-foreground/70">{report.artifact.instruction}</p></details>}
    </> : <p className="text-sm text-foreground/70">Примите модель и запустите генерацию во вкладке «Проверки Java». Здесь появятся её исходники.</p>}
  </section>;

  return <section aria-label="Java-модуль" className="flex flex-col gap-4 rounded-2xl border border-accent/20 bg-panel p-4 sm:p-6">
    <h2 className="text-lg font-semibold">Java по принятой модели</h2>
    <p className="text-sm text-foreground/70">TLC проверяет выбранные свойства модели. Другая LLM рецензирует исходники, а javac и поведенческие тесты проверяют реализацию. Это отдельные свидетельства, а не формальное доказательство Java-кода.</p>
    {!saved ? <p className="text-sm text-amber-400">Для генерации нужен новый сохранённый анализ на сервере.</p> : !eligible ?
      <p className="text-sm text-amber-400">Генерация недоступна: все выбранные свойства должны успешно пройти TLC. Нарушение или незавершённая проверка требуют уточнения требований и нового анализа.</p> : <>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={confirmed} disabled={accepted || !!busy} onChange={(event) => setConfirmed(event.target.checked)} className="mt-1" />Я просмотрел требования, модель, предположения и выбранные свойства</label>
      <div className="flex flex-wrap gap-3">
        <button type="button" className={buttonClass} disabled={!confirmed || accepted || !!busy} onClick={() => void accept()}>{busy === "accept" ? "Принимаем модель…" : accepted ? "Модель принята" : "Принять эту модель"}</button>
        <button type="button" className={buttonClass} disabled={!accepted || !!busy} onClick={() => void generate()}>{busy === "generate" ? "Генерация, ревью и Java-проверки…" : "Сгенерировать и проверить Java"}</button>
      </div>
      {busy === "generate" && <p role="status" className="text-sm text-foreground/70">Генератор → независимое LLM-ревью → компиляция → поведенческие проверки. Это может занять несколько минут.</p>}
    </>}
    {error && <p role="alert" className="text-sm text-red-400">{error} Анализ TLC сохранён.</p>}
    {saved && <details className="text-xs text-foreground/60"><summary className="cursor-pointer">Версия принятия</summary><p className="break-all">Модель: {saved.model_fingerprint}</p>{report?.artifact_fingerprint && <p className="break-all">Исходники: {report.artifact_fingerprint}</p>}</details>}
    {report && <div className="flex flex-col gap-4">
      <p role="status" className={ready ? "text-accent" : "text-amber-400"}>{ready ? STATUS.READY : report.status === "READY" ? "Недостаточно подтверждений готовности" : STATUS[report.status] ?? "Неизвестный статус; готовность не подтверждена"}</p>
      {report.message && <p className="text-sm">{report.message}</p>}
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <div><dt className="text-foreground/60">Генератор</dt><dd>{report.artifact?.generator_model ?? "Не подтверждён"}</dd></div>
        <div><dt className="text-foreground/60">Независимый reviewer</dt><dd>{report.review?.reviewer_model ?? "Не выполнен"}</dd></div>
        <div><dt className="text-foreground/60">Компиляция</dt><dd>{report.compile_and_check?.compilation ?? "Не выполнялась"}</dd></div>
        <div><dt className="text-foreground/60">Поведенческие тесты</dt><dd>{report.compile_and_check ? `${report.compile_and_check.status} · ${report.compile_and_check.checks_run} проверок · ${report.compile_and_check.coverage}` : "Не выполнялись"}</dd></div>
      </dl>
      {report.review && <div className="text-sm"><h3 className="font-medium">LLM-ревью</h3><p>{report.review.message ?? (report.review.approved ? "Ревьюер не нашёл замечаний. Это не доказательство корректности." : "Ревьюер не одобрил код.")}</p><ul className="list-disc pl-5">{report.review.findings.map((finding, index) => <li key={index}>{finding.severity}: {finding.message}{finding.file ? ` (${finding.file}${finding.line ? `:${finding.line}` : ""})` : ""}{finding.transition ? ` · ${finding.transition}` : ""}</li>)}</ul></div>}
      {report.compile_and_check && <details className="text-sm"><summary className="cursor-pointer">Диагностика Java</summary><p>{report.compile_and_check.message}</p><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">{report.compile_and_check.stderr || report.compile_and_check.stdout || "Диагностика отсутствует"}</pre></details>}
      {report.artifact && saved && <a href={`/api/v2/cases/${encodeURIComponent(saved.case_id)}/download`} download className={buttonClass}>Скачать исходники и отчёт ZIP</a>}
    </div>}
  </section>;
}
