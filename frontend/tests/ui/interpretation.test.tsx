import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import InterpretationCard from "@/components/InterpretationCard";
import Home from "@/app/page";
import { makeResult } from "./fixtures";

it("показывает выбранное свойство, предположения и вопросы без переключения вкладки", () => {
  const model = makeResult().behavioral_model;
  model.interpretation = {
    assumptions: ["Начальное состояние Created предположено."],
    questions: ["Каково начальное состояние?"],
    property_rationale: { NoExecuteAfterCancel: "Проверяется только запрет после отмены." },
  };
  render(<InterpretationCard model={model} />);
  expect(screen.getByText("NoExecuteAfterCancel")).toBeInTheDocument();
  expect(screen.getByText(/Начальное состояние Created предположено/)).toBeInTheDocument();
  expect(screen.getByText("Каково начальное состояние?")).toBeInTheDocument();
  expect(screen.getByText(/Выбор агента: Проверяется только/)).toBeInTheDocument();
  expect(screen.getByText(/Успех не подтверждает/)).toBeInTheDocument();
});

it("старый ответ не выдаёт отсутствие метаданных за полноту требований", () => {
  render(<InterpretationCard model={makeResult().behavioral_model} />);
  expect(screen.getByText(/Провайдер не передал предположения/)).toBeInTheDocument();
});

it("уточнение и повторная проверка заменяют предыдущие предположения", async () => {
  const first = makeResult();
  first.behavioral_model.interpretation = {
    assumptions: ["Initial предположен."], questions: ["Уточните initial?"], property_rationale: {},
  };
  const second = makeResult({ requirements: "Изначально Created." });
  second.behavioral_model.interpretation = { assumptions: [], questions: [], property_rationale: {} };
  vi.stubGlobal("fetch", vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => first })
    .mockResolvedValueOnce({ ok: true, json: async () => second }));
  render(<Home />);
  await userEvent.type(screen.getByLabelText("Описание поведения системы"), "Заявка и отмена");
  await userEvent.click(screen.getByRole("button", { name: "Проанализировать" }));
  expect(await screen.findByText("Уточните initial?")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Уточнить требования и проверить снова/ }));
  await userEvent.clear(screen.getByLabelText("Описание поведения системы"));
  await userEvent.type(screen.getByLabelText("Описание поведения системы"), second.requirements);
  await userEvent.click(screen.getByRole("button", { name: "Проанализировать" }));
  await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Проанализировать" }));
  expect(await screen.findByText(/Агент не отметил предположений/)).toBeInTheDocument();
  expect(screen.queryByText("Уточните initial?")).not.toBeInTheDocument();
});
