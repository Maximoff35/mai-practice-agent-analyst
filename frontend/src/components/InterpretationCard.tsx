import type { BehavioralModel } from "@/lib/types";
import { formatExpression } from "@/lib/format";

export default function InterpretationCard({ model }: { model: BehavioralModel }) {
  const interpretation = model.interpretation;
  return (
    <section aria-label="Интерпретация требований" className="flex flex-col gap-3 rounded-2xl border border-amber-400/30 bg-panel p-4 sm:p-6">
      <h2 className="text-lg font-semibold">Что именно проверено</h2>
      <p className="text-sm text-foreground/70">
        TLC проверяет только перечисленные свойства построенной модели. Успех не подтверждает
        все возможные требования или правильность понимания текста агентом.
      </p>
      <ul className="list-disc space-y-2 pl-5 text-sm">
        {model.properties.map((property) => (
          <li key={property.name}>
            <strong>{property.name}</strong> ({property.type}): {property.type === "deadlock_free"
              ? `Нет блокировок; допустимое завершение: ${property.terminal_states === undefined ? "не задано" : formatExpression(property.terminal_states)}`
              : formatExpression(property.expression)}
            {interpretation?.property_rationale[property.name] && (
              <p className="text-foreground/70">Выбор агента: {interpretation.property_rationale[property.name]}</p>
            )}
          </li>
        ))}
      </ul>
      {!interpretation ? (
        <p className="text-sm text-amber-400/90">Провайдер не передал предположения и вопросы. Это не означает, что требования полны: сверяйте initial, guards, effects и свойства с текстом.</p>
      ) : <>
        <h3 className="font-medium">Предположения агента</h3>
        {interpretation.assumptions.length ? <ul className="list-disc space-y-1 pl-5 text-sm">
          {interpretation.assumptions.map((item, index) => <li key={index}>{item}</li>)}
        </ul> : <p className="text-sm text-foreground/70">Агент не отметил предположений. Проверьте модель вручную.</p>}
        <h3 className="font-medium">Вопросы для уточнения</h3>
        {interpretation.questions.length ? <ul className="list-disc space-y-1 pl-5 text-sm">
          {interpretation.questions.map((item, index) => <li key={index}>{item}</li>)}
        </ul> : <p className="text-sm text-foreground/70">Агент не задал вопросов.</p>}
      </>}
      <p className="text-sm text-foreground/70">Если правило неверно или не задано, используйте «Уточнить требования и проверить снова». Изменения выполняются только по вашему тексту.</p>
    </section>
  );
}
