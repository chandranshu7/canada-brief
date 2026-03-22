"use client";

import { IconSearch } from "./icons";

type FiltersProps = {
  categories: string[];
  activeCategory: string;
  onCategoryChange: (c: string) => void;
  sources: string[];
  activeSource: string;
  onSourceChange: (s: string) => void;
  search: string;
  onSearchChange: (q: string) => void;
};

const pillBase =
  "rounded-full px-3.5 py-1.5 text-[12px] font-semibold transition-all duration-200 active:scale-[0.98] sm:px-4 sm:py-2 sm:text-[13px]";
const pillInactive =
  "bg-white/90 text-slate-600 ring-1 ring-slate-200/90 hover:bg-slate-50 hover:text-slate-900 hover:ring-slate-300/90";
const pillActive =
  "bg-slate-900 text-white shadow-md shadow-slate-900/20 ring-1 ring-slate-900/10";

export function Filters({
  categories,
  activeCategory,
  onCategoryChange,
  sources,
  activeSource,
  onSourceChange,
  search,
  onSearchChange,
}: FiltersProps) {
  const catPills = ["All", ...categories];
  const srcPills = ["All", ...sources];

  return (
    <div className="flex flex-col gap-6">
      {/* Full-width search first — reads clearly and doesn’t fight the pill columns */}
      <div>
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
          Search
        </p>
        <div className="relative">
          <label htmlFor="news-search" className="sr-only">
            Search articles
          </label>
          <span
            className="pointer-events-none absolute inset-y-0 left-0 flex w-12 items-center justify-center rounded-l-xl text-slate-400"
            aria-hidden
          >
            <IconSearch className="h-[18px] w-[18px] opacity-80" />
          </span>
          <input
            id="news-search"
            type="search"
            autoComplete="off"
            placeholder="Headlines, topics, keywords…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="news-search-input h-12 w-full rounded-xl border border-slate-200/80 bg-slate-50/90 py-3 pl-12 pr-4 text-[15px] text-slate-900 shadow-[inset_0_1px_2px_rgba(15,23,42,0.04)] placeholder:text-slate-400 transition-[border-color,box-shadow,background-color] focus:border-slate-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900/10"
          />
        </div>
      </div>

      <div className="space-y-4 border-t border-slate-100 pt-5">
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
            Topic
          </p>
          <div className="flex flex-wrap gap-2 sm:gap-2.5">
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

        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
            Source
          </p>
          <div className="flex flex-wrap gap-2 sm:gap-2.5">
            {srcPills.map((src) => {
              const active = activeSource === src;
              return (
                <button
                  key={`src-${src}`}
                  type="button"
                  onClick={() => onSourceChange(src)}
                  className={`${pillBase} ${active ? pillActive : pillInactive}`}
                >
                  {src}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
