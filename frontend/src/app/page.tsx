"use client";

import { useState } from "react";
import RequirementsInput from "@/components/RequirementsInput";

export default function Home() {
  const [requirements, setRequirements] = useState("");

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
        <p className="text-sm leading-relaxed text-foreground/70">
          Опишите поведение системы. ИИ агент переведёт описание в
          формальную модель состояний и переходов, затем проверит её
          свойства и найдёт последовательности, приводящие к ошибке.
        </p>
      </header>

      <section className="flex flex-col gap-4 p-6">
        <RequirementsInput value={requirements} onChange={setRequirements} />
      </section>
    </main>
  );
}
