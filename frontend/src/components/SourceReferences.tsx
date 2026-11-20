import type { SourceReference } from "@/lib/types";

type SourceReferencesProps = {
  references?: SourceReference[];
  label?: string;
};

export default function SourceReferences({
  references = [],
  label = "Связанные требования",
}: SourceReferencesProps) {
  const unique = references.filter(
    (reference, index) =>
      references.findIndex(
        (item) =>
          item.id === reference.id && item.fragment === reference.fragment,
      ) === index,
  );

  if (unique.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-foreground/50">{label}</span>
      <ul className="flex flex-col gap-1.5">
        {unique.map((reference) => (
          <li
            key={`${reference.id}-${reference.fragment}`}
            className="rounded-lg border-l-2 border-accent/50 bg-accent/5 px-3 py-2"
          >
            <span className="mr-2 rounded bg-accent/10 px-1.5 py-0.5 align-middle text-[10px] font-semibold text-accent">
              [{reference.id}]
            </span>
            <span className="break-words text-xs leading-relaxed text-foreground/75">
              «{reference.fragment}»
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
