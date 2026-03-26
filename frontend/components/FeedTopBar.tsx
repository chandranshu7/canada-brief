"use client";

import type { RefObject } from "react";
import { IconSearch } from "./icons";
import { ThemeToggle } from "./ThemeToggle";

type FeedTopBarProps = {
  search: string;
  onSearchChange: (q: string) => void;
  searchInputRef?: RefObject<HTMLInputElement | null>;
  /** When true, subtitle reflects personalized feed (learned on-device). */
  personalized?: boolean;
};

export function FeedTopBar({
  search,
  onSearchChange,
  searchInputRef,
  personalized = false,
}: FeedTopBarProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-[var(--cb-header-border)] bg-[var(--cb-header-bg)] backdrop-blur-xl">
      <div className="mx-auto w-full max-w-6xl px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:px-5 lg:px-8">
        <div className="cb-shell cb-glow mb-3 rounded-2xl px-3.5 py-3 sm:px-4">
          <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="mb-1 inline-flex items-center gap-1.5 rounded-full border border-[var(--cb-border-subtle)] bg-[var(--cb-badge-muted-bg)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--cb-text-tertiary)]">
              <span
                className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--cb-accent)]"
                aria-hidden
              />
              Daily Intelligence
            </p>
            <h1 className="font-display text-[1.45rem] font-semibold leading-none tracking-tight text-[var(--cb-text)] sm:text-[1.6rem]">
              Canada Brief
            </h1>
            <p className="mt-1.5 text-[11px] font-medium text-[var(--cb-text-tertiary)]">
              {personalized
                ? "Your news — tuned from what you read, save, and search"
                : "Canadian headlines, distilled"}
            </p>
          </div>
          <ThemeToggle />
        </div>
        <label htmlFor="feed-search" className="sr-only">
          Search stories
        </label>
        <div className="relative">
          <span
            className="pointer-events-none absolute inset-y-0 left-0 flex w-11 items-center justify-center text-[var(--cb-search-icon)]"
            aria-hidden
          >
            <IconSearch className="h-[18px] w-[18px] opacity-85" />
          </span>
          <input
            ref={searchInputRef}
            id="feed-search"
            type="search"
            autoComplete="off"
            placeholder="Search topics, places, outlets…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="news-search-input h-11 w-full rounded-full border border-[var(--cb-search-border)] bg-[var(--cb-search-bg)] py-2.5 pl-11 pr-4 text-[15px] text-[var(--cb-search-text)] shadow-inner shadow-black/5 placeholder:text-[var(--cb-search-placeholder)] focus:border-[var(--cb-search-border)] focus:outline-none focus:ring-2 focus:ring-[var(--cb-search-ring)]"
          />
        </div>
        </div>
      </div>
    </header>
  );
}
