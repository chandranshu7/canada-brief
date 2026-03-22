"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Article } from "@/lib/types";
import { DEFAULT_PAGE_SIZE, fetchNewsPage } from "@/lib/api";
import {
  filterArticles,
  uniqueCategories,
  uniqueSources,
} from "@/lib/filterArticles";
import { pickMixedTopStories } from "@/lib/pickMixedTopStories";
import { ArticleCard } from "./ArticleCard";
import { Filters } from "./Filters";
import { Header } from "./Header";
import { IconAlert } from "./icons";
import { LoadingSkeleton } from "./LoadingSkeleton";
import { SectionHeader } from "./SectionHeader";
import { StatsStrip } from "./StatsStrip";
import { TopStories } from "./TopStories";

const API_HINT =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function NewsFeed() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [page, setPage] = useState(1);
  const [totalRows, setTotalRows] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState("All");
  const [source, setSource] = useState("All");
  const [search, setSearch] = useState("");

  /** First successful load of page 1 uses refresh=true (RSS ingest). */
  const firstPageRefreshRef = useRef(true);
  /** Bumps to force refetch when e.g. Try again on the same page. */
  const [reloadNonce, setReloadNonce] = useState(0);

  const pageSize = DEFAULT_PAGE_SIZE;

  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));

  const loadCurrentPage = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const useRefresh = page === 1 && firstPageRefreshRef.current;
      const result = await fetchNewsPage({
        page,
        pageSize,
        refresh: useRefresh,
      });
      if (page === 1 && useRefresh) {
        firstPageRefreshRef.current = false;
      }
      setArticles(result.articles);
      setTotalRows(result.totalCount);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Something went wrong loading the feed.",
      );
      setArticles([]);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, reloadNonce]);

  useEffect(() => {
    void loadCurrentPage();
  }, [loadCurrentPage]);

  const categories = useMemo(() => uniqueCategories(articles), [articles]);
  const sources = useMemo(() => uniqueSources(articles), [articles]);

  const filtered = useMemo(
    () => filterArticles(articles, category, search, source),
    [articles, category, search, source],
  );

  const topStories = useMemo(
    () => pickMixedTopStories(filtered, 3),
    [filtered],
  );

  /** Page 1: exclude spotlight picks from the list below. Page 2+: show every story (no spotlight). */
  const feedKeys = useMemo(() => {
    if (page !== 1) {
      return filtered;
    }
    const keys = new Set(topStories.map((a) => a.link));
    return filtered.filter((a) => !keys.has(a.link));
  }, [filtered, topStories, page]);

  const canPrev = page > 1;
  const canNext = page < totalPages;

  const handlePrev = () => {
    if (canPrev) setPage((p) => p - 1);
  };

  const handleNext = () => {
    if (canNext) setPage((p) => p + 1);
  };

  const handleTryAgain = () => {
    firstPageRefreshRef.current = true;
    setReloadNonce((n) => n + 1);
  };

  return (
    <div className="min-h-screen">
      <Header />

      <main className="mx-auto max-w-5xl px-4 pb-20 pt-4 sm:px-6 lg:px-8">
        {/* Filters scroll with the page (no sticky — avoids janky overlap while reading) */}
        <div className="mb-8">
          <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white/80 shadow-premium ring-1 ring-slate-900/[0.03] backdrop-blur-sm">
            <div className="px-4 py-5 sm:px-6 sm:py-6">
              <Filters
                categories={categories}
                activeCategory={category}
                onCategoryChange={setCategory}
                sources={sources}
                activeSource={source}
                onSourceChange={setSource}
                search={search}
                onSearchChange={setSearch}
              />
            </div>
          </div>
        </div>

        {loading && <LoadingSkeleton />}

        {!loading && error && (
          <div
            role="alert"
            className="animate-fade-in-up overflow-hidden rounded-[1.35rem] border border-red-200/90 bg-gradient-to-b from-red-50/95 to-white px-6 py-10 text-center opacity-0 shadow-premium"
          >
            <div className="mx-auto flex max-w-md flex-col items-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-red-100 text-red-700">
                <IconAlert className="h-6 w-6" />
              </span>
              <p className="mt-5 text-lg font-semibold tracking-tight text-red-950">
                We couldn&apos;t load the feed
              </p>
              <p className="mt-2 text-sm leading-relaxed text-red-900/80">{error}</p>
              <p className="mt-4 text-xs text-red-800/70">
                Confirm your API is reachable at{" "}
                <code className="rounded-md bg-red-100/90 px-2 py-0.5 font-mono text-[11px] text-red-900">
                  {API_HINT}
                </code>
              </p>
              <button
                type="button"
                onClick={handleTryAgain}
                className="mt-8 rounded-xl bg-slate-900 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-900/15 transition hover:bg-slate-800 active:scale-[0.98]"
              >
                Try again
              </button>
            </div>
          </div>
        )}

        {!loading && !error && articles.length === 0 && (
          <div className="animate-fade-in-up rounded-[1.35rem] border border-slate-200/90 bg-white/80 px-8 py-16 text-center opacity-0 shadow-premium backdrop-blur-sm">
            <p className="text-lg font-semibold text-slate-900">No stories yet</p>
            <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-slate-500">
              The feed came back empty. Refresh from the API or check your backend
              connection.
            </p>
          </div>
        )}

        {!loading && !error && articles.length > 0 && filtered.length === 0 && (
          <div className="animate-fade-in-up rounded-[1.35rem] border border-slate-200/90 bg-white/80 px-8 py-14 text-center opacity-0 shadow-premium backdrop-blur-sm">
            <p className="text-lg font-semibold text-slate-900">No matches</p>
            <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-slate-500">
              Nothing matches your filters. Try another category, source, or search
              term.
            </p>
          </div>
        )}

        {!loading && !error && filtered.length > 0 && (
          <div className="animate-fade-in space-y-12 opacity-0 sm:space-y-16">
            <StatsStrip
              totalArticles={totalRows > 0 ? totalRows : articles.length}
              topicCount={categories.length}
              visibleCount={filtered.length}
            />

            <div className="h-px w-full bg-gradient-to-r from-transparent via-slate-200 to-transparent" />

            {page === 1 && <TopStories articles={topStories} />}

            {feedKeys.length > 0 && (
              <section>
                <SectionHeader
                  eyebrow="Continue reading"
                  title="More stories"
                  subtitle="Deeper coverage and context from your filtered feed."
                />
                <ul className="space-y-3 sm:space-y-4">
                  {feedKeys.map((a, i) => (
                    <li key={`${a.link}-${i}`}>
                      <ArticleCard article={a} index={i} />
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        )}

        {!loading && !error && articles.length > 0 && totalRows > 0 && (
          <nav
            aria-label="News pagination"
            className="mt-10 flex flex-col items-center gap-4 rounded-2xl border border-slate-200/80 bg-white/60 px-4 py-6 shadow-sm backdrop-blur-sm sm:flex-row sm:justify-between sm:px-8"
          >
            <p className="text-sm font-medium tabular-nums text-slate-600">
              Page {page} of {totalPages}
            </p>
            <div className="flex w-full max-w-sm items-center justify-center gap-3 sm:w-auto sm:max-w-none sm:justify-end">
              <button
                type="button"
                onClick={handlePrev}
                disabled={!canPrev}
                className="min-w-[7.5rem] rounded-xl border border-slate-200/90 bg-white px-4 py-2.5 text-sm font-semibold text-slate-800 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-white"
              >
                Previous
              </button>
              <button
                type="button"
                onClick={handleNext}
                disabled={!canNext}
                className="min-w-[7.5rem] rounded-xl border border-slate-200/90 bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white shadow-md shadow-slate-900/10 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none"
              >
                Next
              </button>
            </div>
          </nav>
        )}
      </main>

      <footer className="border-t border-slate-200/70 bg-white/40 py-10 text-center backdrop-blur-sm">
        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-slate-400">
          Canada Brief
        </p>
        <p className="mt-1.5 text-xs text-slate-500">
          Powered by your FastAPI backend · Built with Next.js
        </p>
      </footer>
    </div>
  );
}
