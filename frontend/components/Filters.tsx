"use client";

import { IconSearch } from "./icons";

type FiltersProps = {
  categories: string[];
  activeCategory: string;
  onCategoryChange: (c: string) => void;
  search: string;
  onSearchChange: (q: string) => void;
};

const pillBase =
  "rounded-full px-3 py-1 text-[11px] font-medium transition-colors duration-150 active:scale-[0.99] sm:px-3.5 sm:py-1.5 sm:text-xs";
const pillInactive =
  "bg-white text-slate-600 ring-1 ring-slate-200/80 hover:bg-slate-50 hover:text-slate-900";
const pillActive =
  "bg-slate-900 text-white ring-1 ring-slate-900/10 shadow-sm";

export function Filters({
  categories,
  activeCategory,
  onCategoryChange,
  search,
  onSearchChange,
}: FiltersProps) {
  const catPills = ["All", ...categories];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <label
          htmlFor="news-search"
          className="mb-1.5 block text-[10px] font-medium uppercase tracking-[0.12em] text-slate-400"
        >
          Search
        </label>
        <div className="relative">
          <span
            className="pointer-events-none absolute inset-y-0 left-0 flex w-11 items-center justify-center text-slate-400"
            aria-hidden
          >
            <IconSearch className="h-[17px] w-[17px] opacity-75" />
          </span>
          <input
            id="news-search"
            type="search"
            autoComplete="off"
            placeholder="Keywords or topics…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="news-search-input h-11 w-full rounded-lg border border-slate-200/90 bg-white py-2.5 pl-11 pr-3.5 text-[15px] text-slate-900 shadow-sm placeholder:text-slate-400 transition-[border-color,box-shadow] focus:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-900/[0.06]"
          />
        </div>
      </div>

      <div>
        <p className="mb-2 text-[10px] font-medium uppercase tracking-[0.12em] text-slate-400">
          Topic
        </p>
        <div className="flex flex-wrap gap-1.5 sm:gap-2">
          {catPills.map((cat) => {
            const active = activeCategory === cat;
            return (
              <button
                key={`cat-${cat}`}
                type="button"
                onClick={() => onCategoryChange(cat)}
                className={`${pillBase} ${active ? pillActive : pillInactive}`}
              >
                {cat}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
