"use client";

import { useMemo, useState } from "react";
import type { CanadianCityOption, LocationPreference } from "@/lib/locationPreference";
import {
  filterCitySuggestions,
  tryMatchPostalCode,
} from "@/lib/locationPreference";

type LocalSetupCardProps = {
  onSelectLocation: (loc: LocationPreference) => void;
};

export function LocalSetupCard({ onSelectLocation }: LocalSetupCardProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(true);

  const suggestions = useMemo(() => {
    const postal = tryMatchPostalCode(query);
    if (postal) return [postal];
    return filterCitySuggestions(query, 10);
  }, [query]);

  const pick = (opt: CanadianCityOption) => {
    onSelectLocation({
      city: opt.city,
      province: opt.province,
      province_code: opt.province_code,
      slug: opt.slug,
      label: opt.label,
    });
    setQuery("");
    setOpen(false);
  };

  return (
    <div className="mx-auto max-w-lg rounded-2xl border border-[var(--cb-card-border)] bg-[var(--cb-surface)] p-6 shadow-sm ring-1 ring-[var(--cb-card-ring)] sm:p-8">
      <h2 className="text-lg font-semibold tracking-tight text-[var(--cb-text)]">
        Choose your area
      </h2>
      <p className="mt-1 text-sm text-[var(--cb-text-tertiary)]">
        Enter a city or postal code. We&apos;ll prioritize nearby and regional
        stories.
      </p>

      <label htmlFor="local-area-input" className="sr-only">
        City or postal code
      </label>
      <input
        id="local-area-input"
        type="text"
        autoComplete="off"
        placeholder="e.g. Ottawa or M5H"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        className="mt-4 h-12 w-full rounded-xl border border-[var(--cb-search-border)] bg-[var(--cb-local-input-bg)] px-4 text-[15px] text-[var(--cb-search-text)] placeholder:text-[var(--cb-search-placeholder)] focus:border-[var(--cb-search-border)] focus:outline-none focus:ring-2 focus:ring-[var(--cb-search-ring)]"
      />

      {open && suggestions.length > 0 && (
        <ul
          className="mt-2 max-h-56 overflow-auto rounded-xl border border-[var(--cb-search-border)] bg-[var(--cb-local-list-bg)] py-1 shadow-lg"
          role="listbox"
        >
          {suggestions.map((opt) => (
            <li key={opt.slug}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                className="flex w-full items-start px-4 py-2.5 text-left text-sm transition hover:bg-[var(--cb-local-row-hover)]"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(opt)}
              >
                <span className="font-medium text-[var(--cb-text)]">
                  {opt.label}, {opt.province}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && query.trim().length > 0 && suggestions.length === 0 && (
        <p className="mt-3 text-xs text-[var(--cb-text-muted)]">
          No matches yet. Try another spelling — postal code lookup is coming
          soon.
        </p>
      )}
    </div>
  );
}
