"use client";

type CategoryStripProps = {
  categories: string[];
  active: string;
  onChange: (c: string) => void;
};

const pill =
  "shrink-0 whitespace-nowrap rounded-full px-3.5 py-2 text-[13px] font-medium transition-[transform,background-color,color,box-shadow] duration-200 ease-out active:scale-[0.98] motion-reduce:transition-none motion-reduce:active:scale-100";

export function CategoryStrip({
  categories,
  active,
  onChange,
}: CategoryStripProps) {
  const pills = ["All", ...categories];

  return (
    <div
      className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 scrollbar-none"
      role="tablist"
      aria-label="Categories"
    >
      {pills.map((cat) => {
        const isOn = active === cat;
        return (
          <button
            key={cat}
            type="button"
            role="tab"
            aria-selected={isOn}
            onClick={() => onChange(cat)}
            className={`${pill} ${
              isOn
                ? "bg-[var(--cb-chip-cat-active-bg)] text-[var(--cb-chip-cat-active-text)] shadow-sm"
                : "bg-[var(--cb-chip-cat-inactive-bg)] text-[var(--cb-chip-cat-inactive-text)] hover:opacity-90"
            }`}
          >
            {cat}
          </button>
        );
      })}
    </div>
  );
}
