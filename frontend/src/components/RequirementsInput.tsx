"use client";

import type { ReactNode } from "react";

type RequirementsInputProps = {
  value: string;
  onChange: (value: string) => void;
  action?: ReactNode;
};

const MAX_LENGTH = 4000;

export default function RequirementsInput({
  value,
  onChange,
  action,
}: RequirementsInputProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-4">
        <label
          htmlFor="requirements"
          className="text-sm font-medium text-foreground/80"
        >
          Описание поведения системы
        </label>
        {action}
      </div>

      <textarea
        id="requirements"
        value={value}
        maxLength={MAX_LENGTH}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Например: заявку согласовывают, затем отменяют, но система всё равно позволяет её исполнить. Опишите участников, состояния, события и правила переходов обычным текстом."
        className="console-scrollbar min-h-[230px] w-full resize-none rounded-xl border border-neutral-600/60 bg-neutral-900/50 px-4 py-3 pr-6 text-sm leading-relaxed text-foreground/75 shadow-sm outline-none transition-colors duration-300 placeholder:text-foreground/35 focus:border-accent/70 focus:bg-input focus:ring-2 focus:ring-accent/15"
      />

      <div className="flex justify-between text-xs text-foreground/50">
        <span>Текст будет передан агенту для построения модели.</span>
        <span>
          {value.length} / {MAX_LENGTH}
        </span>
      </div>
    </div>
  );
}
