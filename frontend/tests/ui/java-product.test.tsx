import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import JavaProduct from "@/components/JavaProduct";
import Home from "@/app/page";
import AnalysisTabs from "@/components/AnalysisTabs";
import type { CaseAnalysis, JavaReport } from "@/lib/types";
import { makeResult } from "./fixtures";

function saved(): CaseAnalysis {
  const analysis = makeResult();
  analysis.verification_result.status = "PROPERTY_HOLDS";
  analysis.verification_result.counterexample = [];
  analysis.counterexample = null;
  return { case_id: "case1", model_fingerprint: "model1", accepted: false, analysis };
}

function ready(): JavaReport {
  return { case_id: "case1", model_fingerprint: "model1", artifact_fingerprint: "source1", status: "READY", message: null,
    artifact: { main_class: "Machine", generator_model: "qwen-generator", files: [{ path: "Machine.java", content: "class Machine { // <img src=x onerror=alert(1)>\n}" }] },
    review: { approved: true, reviewer_model: "deepseek-reviewer", findings: [] },
    compile_and_check: { status: "PASSED", compilation: "PASSED", coverage: "COMPLETE_STATE_EVENT", checks_run: 12, stdout: "", stderr: "" } };
}

const ok = (body: unknown) => ({ ok: true, json: async () => body });
beforeEach(() => { vi.stubGlobal("fetch", vi.fn()); });

async function acceptAndGenerate() {
  const tab = screen.queryByRole("tab", { name: "Проверки Java" });
  if (tab) await userEvent.click(tab);
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(screen.getByRole("button", { name: "Принять эту модель" }));
  await screen.findByRole("button", { name: "Модель принята" });
  await userEvent.click(screen.getByRole("button", { name: "Сгенерировать и проверить Java" }));
}

it("требует явный просмотр и серверное принятие перед генерацией", async () => {
  const state = saved();
  const fetchMock = vi.mocked(fetch).mockResolvedValueOnce(ok({ ...state, accepted: true }) as Response)
    .mockResolvedValueOnce(ok(ready()) as Response);
  const { container } = render(<JavaProduct saved={state} />);
  expect(screen.getByRole("button", { name: "Принять эту модель" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Сгенерировать и проверить Java" })).toBeDisabled();
  await acceptAndGenerate();
  expect(await screen.findByText("Модуль прошёл обязательные проверки")).toBeInTheDocument();
  expect(fetchMock.mock.calls[0][1]?.body).toContain('"accepted":true');
  expect(screen.getByText("qwen-generator")).toBeInTheDocument();
  expect(screen.getByText("deepseek-reviewer")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Скачать исходники/ })).toHaveAttribute("href", "/api/v2/cases/case1/download");
  expect(container.querySelector("img")).toBeNull();
});

it("Java-панели открываются вкладками и сохраняют принятие, отчёт и исходники", async () => {
  const state = saved();
  vi.mocked(fetch).mockResolvedValueOnce(ok({ ...state, accepted: true }) as Response).mockResolvedValueOnce(ok(ready()) as Response);
  const { container } = render(<AnalysisTabs result={state.analysis} savedCase={state} />);
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  await acceptAndGenerate();
  expect(await screen.findByText("Модуль прошёл обязательные проверки")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: "Java-код" }));
  expect(screen.getByLabelText("Файл исходников")).toHaveValue("Machine.java");
  expect(screen.getByLabelText("Исходник Machine.java")).toHaveTextContent("<img src=x onerror=alert(1)>");
  expect(container.querySelector("img")).toBeNull();
  await userEvent.click(screen.getByRole("tab", { name: "Построенная модель" }));
  expect(screen.queryByLabelText("Исходник Machine.java")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: "Проверки Java" }));
  expect(screen.getByRole("button", { name: "Модель принята" })).toBeDisabled();
  expect(screen.getByText("Модуль прошёл обязательные проверки")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("режим записи явно подписан на всех вкладках", async () => {
  const state = saved();
  state.mode = "recorded";
  render(<AnalysisTabs result={state.analysis} savedCase={state} />);
  expect(screen.getByText(/РЕЖИМ ЗАПИСИ/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: "Java-код" }));
  expect(screen.getByText(/РЕЖИМ ЗАПИСИ/)).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it("запрещает Java для нарушенной или незавершённой модели", () => {
  const state = saved();
  state.analysis.verification_result.status = "TIMEOUT";
  render(<JavaProduct saved={state} />);
  expect(screen.getByText(/Генерация недоступна/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Принять эту модель" })).not.toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it.each(["ENVIRONMENT_UNAVAILABLE", "TIMEOUT", "COMPILE_ERROR", "BEHAVIOR_VIOLATED"])("%s не превращает модуль в готовый", async (status) => {
  const report = ready();
  report.status = "JAVA_CHECK_FAILED";
  report.compile_and_check!.status = status;
  report.compile_and_check!.coverage = "NOT_COMPLETED";
  vi.mocked(fetch).mockResolvedValueOnce(ok({ ...saved(), accepted: true }) as Response).mockResolvedValueOnce(ok(report) as Response);
  render(<JavaProduct saved={saved()} />);
  await acceptAndGenerate();
  expect(await screen.findByText("Java-проверки не пройдены")).toBeInTheDocument();
  expect(screen.queryByText("Модуль прошёл обязательные проверки")).not.toBeInTheDocument();
});

it("показывает отказ reviewer и не подменяет его готовностью", async () => {
  const report = ready();
  report.status = "REVIEW_REJECTED";
  report.review!.approved = false;
  report.review!.findings = [{ severity: "ERROR", message: "Пропущен guard Execute", file: "Machine.java", line: 1 }];
  report.compile_and_check = null;
  vi.mocked(fetch).mockResolvedValueOnce(ok({ ...saved(), accepted: true }) as Response).mockResolvedValueOnce(ok(report) as Response);
  render(<JavaProduct saved={saved()} />);
  await acceptAndGenerate();
  expect(await screen.findByText("Ревьюер запросил изменения")).toBeInTheDocument();
  expect(screen.getByText(/Пропущен guard/)).toBeInTheDocument();
});

it("ошибка генерации сохраняет TLC, а уточнение удаляет старый кейс и принятие", async () => {
  vi.mocked(fetch).mockResolvedValueOnce(ok(saved()) as Response)
    .mockResolvedValueOnce(ok({ ...saved(), accepted: true }) as Response)
    .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: "MAI недоступна" }) } as Response)
    .mockResolvedValueOnce({ ok: true, status: 204 } as Response);
  render(<Home />);
  await userEvent.type(screen.getByLabelText("Описание поведения системы"), "Заявка и отмена");
  await userEvent.click(screen.getByRole("button", { name: "Проанализировать" }));
  await screen.findByRole("tablist");
  await acceptAndGenerate();
  expect(await screen.findByRole("alert")).toHaveTextContent("Анализ TLC сохранён");
  expect(screen.getByRole("tablist")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Уточнить требования и проверить снова/ }));
  expect(vi.mocked(fetch).mock.calls[3][1]?.method).toBe("DELETE");
  expect(screen.queryByRole("button", { name: "Модель принята" })).not.toBeInTheDocument();
});
