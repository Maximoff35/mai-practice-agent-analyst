"use client";

import { useState, type FormEvent } from "react";
import RequirementsInput from "@/components/RequirementsInput";
import ConfirmDialog from "@/components/ConfirmDialog";
import ModelCard, { ModelCardSkeleton } from "@/components/ModelCard";
import PropertyCard from "@/components/PropertyCard";
import VerificationResultCard from "@/components/VerificationResultCard";
import { analyzeRequirements } from "@/lib/api";
import type { AnalysisResult } from "@/lib/types";

const EXAMPLE_TEXT =
  "Заявка создаётся. Её можно согласовать или отменить в любой момент. " +
  "Согласованную заявку можно отменить, но препятствием остаётся то, что " +
  "отменённую заявку система по-прежнему может исполнить.";

type FormState = "idle" | "loading" | "error" | "success";

export default function Home() {
  const [requirements, setRequirements] = useState("");
  const [formState, setFormState] = useState<FormState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [confirmingExample, setConfirmingExample] = useState(false);
  const [editing, setEditing] = useState(true);

  function handleExampleClick() {
    if (requirements.trim()) {
      setConfirmingExample(true);
      return;
    }
    setRequirements(EXAMPLE_TEXT);
  }

  function confirmExample() {
    setRequirements(EXAMPLE_TEXT);
    setConfirmingExample(false);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmed = requirements.trim();
    if (!trimmed) {
      setFormState("error");
      setErrorMessage("Опишите поведение системы — поле не должно быть пустым.");
      return;
    }

    setFormState("loading");
    setErrorMessage(null);

    try {
      const analysis = await analyzeRequirements(trimmed);
      setResult(analysis);
      setFormState("success");
      setEditing(false);
    } catch {
      setFormState("error");
      setErrorMessage("Не удалось выполнить анализ. Попробуйте ещё раз.");
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-[62rem] flex-1 flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <span className="flex items-baseline leading-none text-accent">
            <span className="text-[1.75rem] font-extrabold">S</span>
            <span className="text-[0.875rem] font-bold">AI</span>
          </span>
          <span>Проверка поведения системы</span>
        </h1>
        <p className="text-sm leading-relaxed text-foreground/60">
          Опишите поведение системы обычным текстом. Агент переведёт описание в
          формальную модель состояний и переходов, а model checker проверит её
          свойства и найдёт последовательности, приводящие к ошибке.
        </p>
      </header>

{editing ? (
        <section className="flex flex-col gap-4 p-6">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <RequirementsInput
              value={requirements}
              onChange={setRequirements}
              action={
                <button
                  type="button"
                  onClick={handleExampleClick}
                  disabled={formState === "loading"}
                  className="rounded-xl border border-foreground/20 px-4 py-2.5 text-sm text-foreground/60 transition-colors duration-300 hover:border-accent/50 hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Подставить пример
                </button>
              }
            />

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="submit"
                disabled={formState === "loading" || !requirements.trim()}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-accent/60 bg-accent/10 px-6 py-2.5 text-sm font-medium text-accent transition-colors duration-300 hover:bg-accent/20 disabled:cursor-not-allowed disabled:border-accent/25 disabled:bg-transparent disabled:text-accent/30"
              >
                {formState === "loading" ? (
                  <>
                    <svg
                      viewBox="0 0 16 16"
                      fill="none"
                      aria-hidden="true"
                      className="h-4 w-4 animate-spin"
                    >
                      <circle
                        cx="8"
                        cy="8"
                        r="6"
                        stroke="currentColor"
                        strokeWidth="2"
                        className="opacity-25"
                      />
                      <path
                        d="M14 8a6 6 0 0 0-6-6"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                      />
                    </svg>
                    Анализируем…
                  </>
                ) : (
                  "Проанализировать"
                )}
              </button>
            </div>
          </form>

          {formState === "error" && errorMessage && (
            <p className="text-sm text-red-400/90" role="alert">
              {errorMessage}
            </p>
          )}
        </section>
      ) : (
        <section className="flex flex-col gap-4 p-6">
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="inline-flex w-fit items-center gap-2 rounded-xl border border-accent/60 bg-accent/10 px-6 py-2.5 text-sm font-medium text-accent transition-colors duration-300 hover:bg-accent/20"
          >
            <span aria-hidden="true" className="text-base leading-none">
              +
            </span>
            Новая модель
          </button>

          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium text-foreground/80">
              Описание поведения системы
            </span>
            <p className="console-scrollbar max-h-56 overflow-y-auto whitespace-pre-wrap rounded-xl border border-foreground/15 bg-transparent px-4 py-3 pr-6 text-sm leading-relaxed text-foreground/75">
              {result?.requirements ?? requirements}
            </p>
          </div>
        </section>
      )}

      {formState === "loading" ? (
        <ModelCardSkeleton />
      ) : (
        result && <ModelCard model={result.behavioral_model} />
      )}

      {result && formState !== "loading" && (
        <PropertyCard properties={result.behavioral_model.properties} />
      )}

      {result && formState !== "loading" && (
        <VerificationResultCard
          result={result.verification_result}
          explanation={result.explanation}
        />
      )}

      {confirmingExample && (
        <ConfirmDialog
          title="Заменить текст?"
          message="В поле описания уже есть текст. Он будет полностью заменён примером описания поведения системы."
          confirmLabel="Заменить"
          cancelLabel="Отмена"
          onConfirm={confirmExample}
          onCancel={() => setConfirmingExample(false)}
        />
      )}
    </main>
  );
}