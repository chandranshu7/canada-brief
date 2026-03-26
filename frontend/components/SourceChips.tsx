"use client";

type SourceChipsProps = {
  sources: string[];
  active: string;
  onChange: (s: string) => void;
};

const chip =
  "shrink-0 whitespace-nowrap rounded-full border px-3 py-1.5 text-[11px] font-medium transition-[transform,background-color,border-color,color] duration-200 ease-out active:scale-[0.98] motion-reduce:transition-none motion-reduce:active:scale-100";

export function SourceChips({ sources, active, onChange }: SourceChipsProps) {
  if (sources.length === 0) return null;

  const pills = ["All", ...sources];

  return (
    <div className="border-t border-[var(--cb-border)] pt-3">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--cb-text-tertiary)]">
        Sources
      </p>
      <div
        className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 scrollbar-none"
        role="list"
        aria-label="Sources"
      >
        {pills.map((src) => {
          const isOn = active === src;
          return (
            <button
              key={src}
              type="button"
              onClick={() => onChange(src)}
              className={`${chip} ${
                isOn
                  ? "border-[var(--cb-chip-src-active-border)] bg-[var(--cb-chip-src-active-bg)] text-[var(--cb-chip-src-active-text)]"
                  : "border-[var(--cb-chip-src-inactive-border)] bg-transparent text-[var(--cb-chip-src-inactive-text)] hover:border-[var(--cb-text-tertiary)]"
              }`}
            >
              {src}
            </button>
          );
        })}
      </div>
    </div>
  );
}
