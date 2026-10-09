import type { TraceState, TraceValue } from "@/lib/types";

function displayValue(value: TraceValue): string {
  return String(value);
}

type CounterexampleStepsProps = {
  states: TraceState[];
  markLast?: boolean;
};

export default function CounterexampleSteps({
  states,
  markLast = false,
}: CounterexampleStepsProps) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h3 className="text-sm font-semibold text-accent">Контрпример</h3>
        <p className="text-xs leading-relaxed text-foreground/50">
          Последовательность допустимых шагов, при которой нарушается
          проверяемое свойство.
        </p>
      </div>

      <ol className="flex flex-col gap-3">
        {states.map((state, index) => {
          const isLast = index === states.length - 1;
          const highlight = markLast && isLast;

          return (
            <li key={state.number} className="flex gap-3">
              <div className="flex flex-col items-center pt-2">
                <span
                  className={`h-3 w-3 shrink-0 rounded-full border ${
                    highlight
                      ? "border-red-400 bg-red-400/40"
                      : "border-accent/60 bg-accent/30"
                  }`}
                />
                {!isLast && (
                  <span className="mt-1 w-px flex-1 bg-foreground/15" />
                )}
              </div>

              <div
                className={`flex flex-1 flex-col gap-2 rounded-lg border px-4 py-3 ${
                  highlight
                    ? "border-red-400/50 bg-red-400/5"
                    : "border-foreground/10"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-semibold text-foreground/90">
                    {state.transition ?? "Начальное состояние"}
                  </span>
                  <span className="text-xs text-foreground/40">
                    шаг {state.number}
                  </span>
                </div>

                <div className="flex flex-wrap gap-2">
                  {Object.entries(state.values).map(([name, value]) => (
                    <code
                      key={name}
                      className="rounded border border-foreground/10 px-2 py-0.5 text-xs text-foreground/75"
                    >
                      {name} = {displayValue(value)}
                    </code>
                  ))}
                </div>

                {state.tlc_label && (
                  <span className="text-[10px] text-foreground/30">
                    {state.tlc_label}
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}