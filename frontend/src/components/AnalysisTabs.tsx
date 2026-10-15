"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import ModelCard from "@/components/ModelCard";
import PropertyCard from "@/components/PropertyCard";
import VerificationResultCard from "@/components/VerificationResultCard";
import type { AnalysisResult } from "@/lib/types";

type TabId = "model" | "property" | "result";

const TABS: { id: TabId; label: string }[] = [
  { id: "model", label: "Построенная модель" },
  { id: "property", label: "Проверяемое свойство" },
  { id: "result", label: "Результат проверки" },
];

export default function AnalysisTabs({ result }: { result: AnalysisResult }) {
  const [activeTab, setActiveTab] = useState<TabId>("model");
  const tabRefs = useRef<Partial<Record<TabId, HTMLButtonElement | null>>>({});

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") {
      return;
    }
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const nextIndex = (index + direction + TABS.length) % TABS.length;
    const nextTab = TABS[nextIndex];
    setActiveTab(nextTab.id);
    tabRefs.current[nextTab.id]?.focus();
  }

  return (
    <div className="flex flex-col gap-4">
      <div
        role="tablist"
        aria-label="Результаты анализа"
        className="flex flex-wrap gap-2"
      >
        {TABS.map((tab, index) => {
          const selected = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              ref={(node) => {
                tabRefs.current[tab.id] = node;
              }}
              type="button"
              role="tab"
              id={`analysis-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`analysis-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActiveTab(tab.id)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className={`rounded-xl border px-4 py-2 text-sm transition-colors duration-300 ${
                selected
                  ? "border-accent/60 bg-accent/10 text-accent"
                  : "border-foreground/15 text-foreground/60 hover:border-accent/40 hover:text-accent"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={`analysis-panel-${activeTab}`}
        aria-labelledby={`analysis-tab-${activeTab}`}
      >
        {activeTab === "model" && (
          <ModelCard model={result.behavioral_model} />
        )}
        {activeTab === "property" && (
          <PropertyCard properties={result.behavioral_model.properties} />
        )}
        {activeTab === "result" && (
          <VerificationResultCard
            result={result.verification_result}
            explanation={result.explanation}
          />
        )}
      </div>
    </div>
  );
}