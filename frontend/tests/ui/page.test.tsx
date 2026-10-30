import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { makeResult } from "./fixtures";

type MockedFetch = ReturnType<typeof vi.fn>;

function okResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

function errorResponse(status: number, detail: unknown) {
  return { ok: false, status, json: async () => ({ detail }) };
}

describe("страница анализа", () => {
  let fetchMock: MockedFetch;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("на пустом вводе показывает ошибку и не обращается к серверу", async () => {
    const { container } = render(<Home />);
    const form = container.querySelector("form");
    if (!form) throw new Error("форма не найдена");

    fireEvent.submit(form);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "поле не должно быть пустым",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("блокирует поле ввода и кнопку, пока идёт анализ", async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    fetchMock.mockImplementation(
      () => new Promise((resolve) => (resolveFetch = resolve)),
    );

    render(<Home />);
    const textarea = screen.getByLabelText("Описание поведения системы");
    await userEvent.type(textarea, "Заявка и отмена");
    await userEvent.click(
      screen.getByRole("button", { name: "Проанализировать" }),
    );

    expect(textarea).toBeDisabled();
    expect(screen.getByRole("button", { name: /Анализируем/ })).toBeDisabled();

    resolveFetch(okResponse(makeResult()));
    expect(await screen.findByRole("tablist")).toBeInTheDocument();
  });

  it("показывает сообщение backend при HTTP-ошибке и не рисует результат", async () => {
    fetchMock.mockResolvedValue(errorResponse(503, "LLM недоступна"));

    render(<Home />);
    await userEvent.type(
      screen.getByLabelText("Описание поведения системы"),
      "Заявка и отмена",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Проанализировать" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("LLM недоступна");
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("запрашивает подтверждение перед повторным анализом", async () => {
    fetchMock.mockResolvedValue(okResponse(makeResult()));

    render(<Home />);
    await userEvent.type(
      screen.getByLabelText("Описание поведения системы"),
      "Заявка и отмена",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Проанализировать" }),
    );
    await screen.findByRole("tablist");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: /Новая модель/ }));
    await userEvent.click(
      screen.getByRole("button", { name: "Проанализировать" }),
    );

    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Запустить новый анализ?")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await userEvent.click(
      within(dialog).getByRole("button", { name: "Проанализировать" }),
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it("«Уточнить требования» подставляет текст текущего анализа и сохраняет результат", async () => {
    fetchMock.mockResolvedValue(
      okResponse(makeResult({ requirements: "Текст из ответа backend" })),
    );

    render(<Home />);
    await userEvent.type(
      screen.getByLabelText("Описание поведения системы"),
      "Черновик пользователя",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Проанализировать" }),
    );
    await screen.findByRole("tablist");

    await userEvent.click(
      screen.getByRole("button", {
        name: "Уточнить требования и проверить снова",
      }),
    );

    expect(
      screen.getByLabelText("Описание поведения системы"),
    ).toHaveValue("Текст из ответа backend");
    expect(
      screen.getByText(/результат предыдущего анализа/),
    ).toBeInTheDocument();
    expect(screen.getByRole("tablist")).toBeInTheDocument();
  });

  it("при повторной проверке не показывает старую трассу как результат нового текста", async () => {
    let resolveSecondFetch: (value: unknown) => void = () => {};
    fetchMock
      .mockResolvedValueOnce(
        okResponse(makeResult({ requirements: "Первый текст" })),
      )
      .mockImplementationOnce(
        () => new Promise((resolve) => (resolveSecondFetch = resolve)),
      );

    render(<Home />);
    await userEvent.type(
      screen.getByLabelText("Описание поведения системы"),
      "Первый текст",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Проанализировать" }),
    );
    await screen.findByRole("tablist");

    await userEvent.click(
      screen.getByRole("button", {
        name: "Уточнить требования и проверить снова",
      }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Проанализировать" }),
    );

    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Проанализировать" }),
    );

    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();

    resolveSecondFetch(
      okResponse(makeResult({ requirements: "Первый текст" })),
    );
    expect(await screen.findByRole("tablist")).toBeInTheDocument();
  });

  it("после ошибки при уточнении не оставляет старый результат", async () => {
    fetchMock
      .mockResolvedValueOnce(okResponse(makeResult()))
      .mockResolvedValueOnce(errorResponse(500, "Сбой проверки"));

    render(<Home />);
    await userEvent.type(
      screen.getByLabelText("Описание поведения системы"),
      "Заявка и отмена",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Проанализировать" }),
    );
    await screen.findByRole("tablist");

    await userEvent.click(
      screen.getByRole("button", {
        name: "Уточнить требования и проверить снова",
      }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Проанализировать" }),
    );
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Проанализировать" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Сбой проверки");
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });
});
