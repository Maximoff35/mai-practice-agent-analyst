import type { VerificationResult, VerificationStatus } from "@/lib/types";
import CounterexampleSteps from "@/components/CounterexampleSteps";
import SourceReferences from "@/components/SourceReferences";

const STATUS_INFO: Record<
  VerificationStatus,
  { title: string; badge: string; warning?: string }
> = {
  PROPERTY_HOLDS: {
    title: "Свойство не нарушено",
    badge: "border-accent/50 bg-accent/10 text-accent",
  },
  PROPERTY_VIOLATED: {
    title: "Найден путь, нарушающий свойство",
    badge: "border-red-400/50 bg-red-400/10 text-red-400/90",
  },
  MODEL_INVALID: {
    title: "Модель некорректна",
    badge: "border-foreground/25 bg-foreground/5 text-foreground/60",
  },
  TIMEOUT: {
    title: "Проверка не завершена",
    badge: "border-amber-400/50 bg-amber-400/10 text-amber-400/90",
    warning:
      "Достигнут лимит времени: результат нельзя трактовать как успешный.",
  },
  STATE_LIMIT_REACHED: {
    title: "Проверка не завершена",
    badge: "border-amber-400/50 bg-amber-400/10 text-amber-400/90",
    warning:
      "Достигнут предел числа состояний: результат нельзя трактовать как успешный.",
  },
  ENGINE_ERROR: {
    title: "Ошибка движка проверки",
    badge: "border-red-400/50 bg-red-400/10 text-red-400/90",
  },
};

const STATISTICS_LABELS: Record<string, string> = {
  generated_states: "Сгенерировано состояний",
  distinct_states: "Различных состояний",
  queued_states: "В очереди",
  graph_depth: "Глубина графа",
};

type VerificationResultCardProps = {
  result: VerificationResult;
  explanation: string;
};

export default function VerificationResultCard({
  result,
  explanation,
}: VerificationResultCardProps) {
  const info = STATUS_INFO[result.status];
  const propertyResults = result.property_results ?? [];
  const hasIndividualResults = propertyResults.length > 0;
  const title = hasIndividualResults && result.status === "PROPERTY_HOLDS"
    ? "Все заданные свойства выполнены"
    : hasIndividualResults && result.status === "PROPERTY_VIOLATED"
      ? "Есть невыполненное свойство"
      : info.title;
  const hasCounterexample = result.counterexample.length > 0;
  const statistics = Object.entries(result.statistics).filter(
    ([, value]) => value !== null && value !== undefined,
  );

  return (
    <section className="flex flex-col gap-6 rounded-2xl border border-accent/15 bg-panel p-4 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
        <h2 className="text-lg font-semibold text-foreground/90">
          Результат проверки
        </h2>
        <span className={`rounded-full border px-3 py-1 text-xs ${info.badge}`}>
          {result.status}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        <p className="text-sm text-foreground/85">{title}</p>
        {result.message && (
          <p className="break-words text-sm leading-relaxed text-foreground/70">
            {result.message}
          </p>
        )}
        {result.violated_property && (
          <p className="break-words text-sm text-foreground/70">
            Нарушенное свойство:{" "}
            <code className="break-words text-foreground/85">
              {result.violated_property}
            </code>
          </p>
        )}
        {info.warning && (
          <p className="text-sm leading-relaxed text-amber-400/80">
            {info.warning}
          </p>
        )}
      </div>

      {!hasIndividualResults && (
        <SourceReferences references={result.related_requirements} />
      )}

      {statistics.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {statistics.map(([key, value]) => (
            <div
              key={key}
              className="flex flex-col gap-1 rounded-lg border border-foreground/10 px-3 py-2"
            >
              <span className="text-lg text-foreground/90">{value}</span>
              <span className="text-xs text-foreground/50">
                {STATISTICS_LABELS[key] ?? key}
              </span>
            </div>
          ))}
        </div>
      )}

      {hasIndividualResults ? propertyResults.map((item) => (
        <div key={item.property_name} className="flex flex-col gap-3 border-t border-foreground/10 pt-4">
          <h3 className="break-words text-sm font-semibold">
            {item.property_name} ({item.property_type}): {item.status}
          </h3>
          {item.message && <p className="text-sm text-foreground/70">{item.message}</p>}
          {STATUS_INFO[item.status].warning && (
            <p className="text-sm text-amber-400/80">{STATUS_INFO[item.status].warning}</p>
          )}
          <SourceReferences
            references={item.related_requirements}
            label="Требования свойства"
          />
          {item.witness.length > 0 && <CounterexampleSteps states={item.witness}
            title={`Путь к цели: ${item.property_name}`}
            description="Допустимая последовательность шагов до целевого состояния." />}
          {item.counterexample.length > 0 && <CounterexampleSteps states={item.counterexample} markLast />}
        </div>
      )) : hasCounterexample ? (
        <CounterexampleSteps
          states={result.counterexample}
          markLast={result.status === "PROPERTY_VIOLATED"}
        />
      ) : (result.witness?.length ?? 0) > 0 ? (
        <CounterexampleSteps
          states={result.witness ?? []}
          title={
            result.violated_property
              ? `Путь к цели: ${result.violated_property}`
              : "Путь к цели"
          }
          description="Допустимая последовательность шагов до целевого состояния."
        />
      ) : (
        result.status === "PROPERTY_HOLDS" && (
          <p className="text-sm text-foreground/60">
            Контрпример не найден в проверенной конечной модели. Это не
            доказывает корректность реальной системы или интерпретации требований.
          </p>
        )
      )}

      {explanation && (
        <div className="flex flex-col gap-2 border-t border-foreground/10 pt-4">
          <h3 className="text-sm font-semibold text-accent">Пояснение</h3>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/70">
            {explanation}
          </p>
        </div>
      )}
    </section>
  );
}
