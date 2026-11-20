import type { BehavioralModel, Variable } from "@/lib/types";
import { formatExpression } from "@/lib/format";

function variableDomain(variable: Variable): string {
  if (variable.type === "enum") {
    return variable.values.join(", ");
  }
  if (variable.type === "boolean") {
    return "true / false";
  }
  return `${variable.min} .. ${variable.max}`;
}

function formatValue(value: unknown): string {
  return formatExpression(value);
}

export default function ModelCard({ model }: { model: BehavioralModel }) {
  return (
    <section className="flex flex-col gap-6 rounded-2xl border border-accent/15 bg-panel p-4 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="text-lg font-semibold text-foreground/90">
          Построенная модель
        </h2>
        <span className="text-xs text-foreground/50">
          {model.transitions.length} переходов ·{" "}
          {model.properties.length} свойств
        </span>
      </div>

      <p className="text-sm leading-relaxed text-foreground/70">
        Модель описывает поведение системы как машину состояний: переменные
        состояния с конечными доменами, начальное состояние, переходы с
        условиями выполнения (guard) и эффектами, а также свойства, которые
        должна проверить система. Детерминированный model checker (TLC)
        перебирает достижимые состояния по этой модели и ищет
        последовательности событий, нарушающие свойства.
      </p>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-accent">Переменные</h3>
        <ul className="flex flex-col divide-y divide-foreground/10 overflow-hidden rounded-lg border border-foreground/10 text-sm">
          {model.variables.map((variable) => (
            <li
              key={variable.name}
              className="flex flex-col gap-0.5 px-4 py-2 sm:grid sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,2fr)] sm:items-center sm:gap-4"
            >
              <span className="break-words text-foreground/85">
                {variable.name}
              </span>
              <span className="text-xs text-foreground/50 sm:text-sm">
                {variable.type}
              </span>
              <span className="break-words text-xs text-foreground/60 sm:text-right sm:text-sm">
                {variableDomain(variable)}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-accent">Начальное состояние</h3>
        <div className="flex flex-wrap gap-2">
          {Object.entries(model.initial).map(([name, value]) => (
            <code
              key={name}
              className="max-w-full break-words rounded-lg border border-foreground/10 px-3 py-1.5 text-sm text-foreground/85"
            >
              {name} = {formatValue(value)}
            </code>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-accent">Переходы</h3>
        <div className="flex flex-col gap-2">
          {model.transitions.map((transition) => (
            <div
              key={transition.name}
              className="flex flex-col gap-1 rounded-lg border border-foreground/10 px-4 py-3 text-sm"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <span className="font-semibold text-foreground/90">
                  {transition.name}
                </span>
                <span className="break-words text-xs text-foreground/50">
                  allow {formatExpression(transition.guard)}
                </span>
              </div>
              <ul className="flex flex-col gap-0.5 text-foreground/70">
                {transition.effects.map((effect, index) => (
                  <li key={index} className="break-words">
                    <span className="text-foreground/40">→ </span>
                    {effect.set[0]} = {formatValue(effect.set[1])}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

    </section>
  );
}

export function ModelCardSkeleton() {
  return (
    <section className="flex animate-pulse flex-col gap-6 rounded-2xl border border-accent/15 bg-panel p-4 sm:p-6">
      <div className="flex items-baseline justify-between">
        <div className="h-5 w-40 rounded bg-foreground/10" />
        <div className="h-3 w-44 rounded bg-foreground/10" />
      </div>
      <div className="h-24 w-full rounded-lg bg-foreground/10" />
      <div className="h-12 w-full rounded-lg bg-foreground/10" />
      <div className="h-28 w-full rounded-lg bg-foreground/10" />
    </section>
  );
}