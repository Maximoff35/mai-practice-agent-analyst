"use client";

import { useRef, useState, type KeyboardEvent } from "react";
import ModelCard from "@/components/ModelCard";
import PropertyCard from "@/components/PropertyCard";
import VerificationResultCard from "@/components/VerificationResultCard";
import JavaProduct from "@/components/JavaProduct";
import type { AnalysisResult, CaseAnalysis } from "@/lib/types";

type TabId = "model" | "property" | "result" | "java" | "code";

const TABS: { id: TabId; label: string }[] = [
  { id: "model", label: "Построенная модель" },
  { id: "property", label: "Проверяемое свойство" },
  { id: "result", label: "Результат проверки" },
  { id: "java", label: "Проверки Java" },
  { id: "code", label: "Java-код" },
];

export default function AnalysisTabs({ result, savedCase = null }: { result: AnalysisResult; savedCase?: CaseAnalysis | null }) {
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

      {savedCase?.mode === "recorded" && <p role="status" className="text-sm text-amber-400">РЕЖИМ ЗАПИСИ: ответы LLM сохранены ранее. TLC и проверки Java выполняются заново; новых запросов МАИ нет.</p>}

      <div
        hidden={activeTab === "java" || activeTab === "code"}
        role="tabpanel"
        id={activeTab === "java" || activeTab === "code" ? undefined : `analysis-panel-${activeTab}`}
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
      <div hidden={activeTab !== "java" && activeTab !== "code"}
        role="tabpanel" id={`analysis-panel-${activeTab === "code" ? "code" : "java"}`}
        aria-labelledby={`analysis-tab-${activeTab === "code" ? "code" : "java"}`}>
        <JavaProduct key={savedCase?.case_id ?? "legacy"} saved={savedCase} view={activeTab === "code" ? "code" : "checks"} />
      </div>
    </div>
  );
}
