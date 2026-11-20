import type { Property, PropertyType } from "@/lib/types";
import { formatExpression } from "@/lib/format";
import SourceReferences from "@/components/SourceReferences";

const TYPE_INFO: Record<
  PropertyType,
  { badge: string; description: string }
> = {
  invariant: {
    badge: "border-accent/40 text-accent",
    description: "Утверждение истинно во всех достижимых состояниях модели.",
  },
  forbidden_state: {
    badge: "border-red-400/40 text-red-400/90",
    description: "Состояние, описанное выражением, не должно быть достижимо.",
  },
  reachable: {
    badge: "border-accent/40 text-accent",
    description: "Существует хотя бы один допустимый путь к указанному состоянию.",
  },
  deadlock_free: {
    badge: "border-amber-400/40 text-amber-400/90",
    description: "Нет достижимых состояний без разрешённых бизнес-переходов, кроме явно допустимого завершения.",
  },
};

export default function PropertyCard({ properties }: { properties: Property[] }) {
  const title =
    properties.length === 1 ? "Проверяемое свойство" : "Проверяемые свойства";

  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-accent/15 bg-panel p-4 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="text-lg font-semibold text-foreground/90">{title}</h2>
        <span className="text-xs text-foreground/50">
          {properties.length} шт.
        </span>
      </div>

      <p className="text-sm leading-relaxed text-foreground/70">
        Свойства формализуют требования к системе: агент выводит их из
        текстового описания вместе с моделью, а model checker проверяет
        инварианты, запреты и отсутствие блокировок, а для reachable ищет путь к цели.
      </p>

      <div className="flex flex-col gap-2">
        {properties.map((property) => {
          const info = TYPE_INFO[property.type];
          return (
            <div
              key={property.name}
              className="flex flex-col gap-2 rounded-lg border border-foreground/10 px-4 py-3"
            >
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-sm font-semibold text-foreground/90">
                  {property.name}
                </span>
                <span
                  className={`rounded-full border px-2.5 py-0.5 text-xs ${info.badge}`}
                >
                  {property.type}
                </span>
              </div>
              <code className="break-words whitespace-pre-wrap text-sm leading-relaxed text-foreground/85">
                {property.type === "deadlock_free"
                  ? property.terminal_states === undefined
                    ? "Допустимое завершение не задано"
                    : `Допустимое завершение: ${formatExpression(property.terminal_states)}`
                  : formatExpression(property.expression)}
              </code>
              <p className="text-xs leading-relaxed text-foreground/60">
                {info.description}
              </p>
              <SourceReferences
                references={
                  property.source_reference
                    ? [property.source_reference]
                    : undefined
                }
                label="Фрагмент требований"
              />
            </div>
          );
        })}
      </div>
    </section>
  );
}
