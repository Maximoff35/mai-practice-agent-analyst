import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import VerificationResultCard from "@/components/VerificationResultCard";
import type { VerificationStatus } from "@/lib/types";
import { makeVerification } from "./fixtures";
import PropertyCard from "@/components/PropertyCard";

const TITLES: Record<VerificationStatus, string> = {
  PROPERTY_HOLDS: "Свойство не нарушено",
  PROPERTY_VIOLATED: "Найден путь, нарушающий свойство",
  MODEL_INVALID: "Модель некорректна",
  TIMEOUT: "Проверка не завершена",
  STATE_LIMIT_REACHED: "Проверка не завершена",
  ENGINE_ERROR: "Ошибка движка проверки",
};

describe("VerificationResultCard", () => {
  it("показывает путь reachable как путь к цели, без контрпримера", () => {
    render(<VerificationResultCard result={makeVerification("PROPERTY_HOLDS", {
      property_results: [{ property_name: "Goal", property_type: "reachable", status: "PROPERTY_HOLDS",
        message: "Цель достижима", counterexample: [],
        witness: [{ number: 1, values: { ready: true }, transition: null, tlc_label: null }],
        related_requirements: [], statistics: {} }],
    })} explanation="" />);
    expect(screen.getByText("Путь к цели: Goal")).toBeInTheDocument();
    expect(screen.queryByText("Контрпример")).not.toBeInTheDocument();
    expect(screen.getByText("Все заданные свойства выполнены")).toBeInTheDocument();
  });

  it("недостижимая цель и timeout другого свойства не выглядят найденным контрпримером", () => {
    render(<VerificationResultCard result={makeVerification("PROPERTY_VIOLATED", {
      counterexample: [],
      property_results: [
        { property_name: "Impossible", property_type: "reachable", status: "PROPERTY_VIOLATED",
          message: "Цель недостижима", counterexample: [], witness: [], related_requirements: [], statistics: {} },
        { property_name: "Unknown", property_type: "reachable", status: "TIMEOUT",
          message: null, counterexample: [], witness: [], related_requirements: [], statistics: {} },
      ],
    })} explanation="" />);
    expect(screen.getByText("Цель недостижима")).toBeInTheDocument();
    expect(screen.getByText(/нельзя трактовать как успешный/)).toBeInTheDocument();
    expect(screen.queryByText("Контрпример")).not.toBeInTheDocument();
    expect(screen.queryByText("Найден путь, нарушающий свойство")).not.toBeInTheDocument();
  });

  it("показывает описание свойства reachable", () => {
    render(<PropertyCard properties={[{ name: "Goal", type: "reachable", expression: true }]} />);
    expect(screen.getByText("Существует хотя бы один допустимый путь к указанному состоянию.")).toBeInTheDocument();
  });

  it.each(Object.entries(TITLES))(
    "показывает корректный заголовок и код статуса %s",
    (status, title) => {
      render(
        <VerificationResultCard
          result={makeVerification(status as VerificationStatus)}
          explanation=""
        />,
      );

      expect(screen.getByText(title)).toBeInTheDocument();
      expect(screen.getByText(status)).toBeInTheDocument();
    },
  );

  it("не выдаёт незавершённую проверку за успех", () => {
    render(
      <VerificationResultCard
        result={makeVerification("TIMEOUT")}
        explanation=""
      />,
    );

    expect(screen.getByText(/нельзя трактовать как успешный/)).toBeInTheDocument();
    expect(screen.queryByText("Свойство не нарушено")).not.toBeInTheDocument();
  });

  it("предупреждает о достижении предела состояний", () => {
    render(
      <VerificationResultCard
        result={makeVerification("STATE_LIMIT_REACHED")}
        explanation=""
      />,
    );

    expect(screen.getByText(/предел числа состояний/)).toBeInTheDocument();
    expect(screen.queryByText("Свойство не нарушено")).not.toBeInTheDocument();
  });

  it("показывает шаги контрпримера при нарушении свойства", () => {
    render(
      <VerificationResultCard
        result={makeVerification("PROPERTY_VIOLATED")}
        explanation=""
      />,
    );

    expect(screen.getByText("Контрпример")).toBeInTheDocument();
    expect(screen.getByText("approve")).toBeInTheDocument();
    expect(screen.getByText("execute")).toBeInTheDocument();
  });

  it("не претендует на доказательство корректности, когда контрпример не найден", () => {
    render(
      <VerificationResultCard
        result={makeVerification("PROPERTY_HOLDS")}
        explanation=""
      />,
    );

    expect(
      screen.getByText(/не доказывает корректность реальной системы/),
    ).toBeInTheDocument();
  });
});
