import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import SourceReferences from "@/components/SourceReferences";
import { makeReference } from "./fixtures";

describe("SourceReferences", () => {
  it("показывает подтверждённый фрагмент и его маркер", () => {
    render(
      <SourceReferences
        references={[makeReference("R1", "Отменённую заявку нельзя исполнить")]}
        label="Фрагмент требований"
      />,
    );

    expect(screen.getByText("Фрагмент требований")).toBeInTheDocument();
    expect(screen.getByText("[R1]")).toBeInTheDocument();
    expect(
      screen.getByText(/Отменённую заявку нельзя исполнить/),
    ).toBeInTheDocument();
  });

  it("ничего не выводит для ответа без ссылок", () => {
    const { container } = render(<SourceReferences references={undefined} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("не дублирует одинаковые ссылки", () => {
    const reference = makeReference("R1", "Отмена до исполнения");

    render(<SourceReferences references={[reference, reference]} />);

    expect(screen.getByText("[R1]")).toBeInTheDocument();
    expect(
      screen.getAllByText(/Отмена до исполнения/),
    ).toHaveLength(1);
  });
});
