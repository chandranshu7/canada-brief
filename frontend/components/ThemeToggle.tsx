"use client";

import type { ThemePreference } from "@/lib/theme";
import { useTheme } from "./ThemeProvider";

const OPTIONS: { id: ThemePreference; label: string }[] = [
  { id: "dark", label: "Dark" },
  { id: "light", label: "Light" },
  { id: "system", label: "System" },
];

export function ThemeToggle() {
  const { preference, setPreference } = useTheme();

  return (
    <div
      className="flex shrink-0 rounded-full border border-[var(--cb-border)] bg-[var(--cb-surface)] p-0.5 shadow-sm ring-1 ring-[var(--cb-card-ring)]"
      role="group"
      aria-label="Color theme"
    >
      {OPTIONS.map((o) => {
        const on = preference === o.id;
        return (
          <button
            key={o.id}
            type="button"
            onClick={() => setPreference(o.id)}
            aria-pressed={on}
            className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] transition-[background,color,box-shadow] duration-200 ease-out sm:px-2.5 ${
              on
                ? "bg-[var(--cb-chip-cat-active-bg)] text-[var(--cb-chip-cat-active-text)] shadow-sm"
                : "text-[var(--cb-text-tertiary)] hover:text-[var(--cb-text-secondary)]"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
