import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import ConfirmDialog from "@/components/ConfirmDialog";

function renderDialog(overrides: Partial<ComponentProps<typeof ConfirmDialog>> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmDialog
      title="Запустить новый анализ?"
      message="Результат будет заменён."
      confirmLabel="Проанализировать"
      cancelLabel="Отмена"
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...overrides}
    />,
  );
  return { onConfirm, onCancel };
}

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Открыть
      </button>
      {open && (
        <ConfirmDialog
          title="Запустить новый анализ?"
          message="Результат будет заменён."
          confirmLabel="Проанализировать"
          cancelLabel="Отмена"
          onConfirm={() => setOpen(false)}
          onCancel={() => setOpen(false)}
        />
      )}
    </>
  );
}

describe("ConfirmDialog", () => {
  it("описывает себя ролью alertdialog и заголовком", () => {
    renderDialog();

    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveAccessibleName("Запустить новый анализ?");
    expect(screen.getByText("Результат будет заменён.")).toBeInTheDocument();
  });

  it("фокусирует кнопку подтверждения при открытии", () => {
    renderDialog();

    expect(
      screen.getByRole("button", { name: "Проанализировать" }),
    ).toHaveFocus();
  });

  it("закрывается по Escape", async () => {
    const { onCancel } = renderDialog();

    await userEvent.keyboard("{Escape}");

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("возвращает фокус на элемент, открывший диалог", async () => {
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Открыть" });

    await userEvent.click(opener);
    expect(
      screen.getByRole("button", { name: "Проанализировать" }),
    ).toHaveFocus();

    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));

    expect(opener).toHaveFocus();
  });
});
