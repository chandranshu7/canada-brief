"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Article } from "@/lib/types";
import { DEFAULT_PAGE_SIZE, fetchNewsPage } from "@/lib/api";
import { filterArticles, uniqueCategories } from "@/lib/filterArticles";
import {
  isLinkSaved,
  loadSavedLinks,
  saveSavedLinks,
} from "@/lib/savedArticles";
import {
  clearSeenLinks,
  loadSeenLinks,
  normalizeArticleLink,
  saveSeenLinks,
} from "@/lib/seenArticles";
import { Filters } from "./Filters";
import { Header } from "./Header";
import { LoadingSkeleton } from "./LoadingSkeleton";
import { SingleStoryHero } from "./SingleStoryHero";

const API_HINT =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const QUEUE_LOW_WATER = 3;
const DEBUG = process.env.NODE_ENV === "development";

function debugFeedState(label: string, payload: Record<string, unknown>) {
  if (!DEBUG) return;
  console.log(`[NewsFeed] ${label}`, payload);
}

export function NewsFeed() {
  const [pool, setPool] = useState<Article[]>([]);
  const [totalRows, setTotalRows] = useState(0);
  /** True only while the initial GET /news (page 1) is in flight. */
  const [initialLoading, setInitialLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [category, setCategory] = useState("All");
  const [search, setSearch] = useState("");

  const [seen, setSeen] = useState<Set<string>>(new Set());
  const [seenReady, setSeenReady] = useState(false);
  const [showSeen, setShowSeen] = useState(false);

  /** Index into `filtered` when browsing with “show seen” on. */
  const [seenBrowseIndex, setSeenBrowseIndex] = useState(0);

  /**
   * Ordered list of stories visited in this session (normal mode).
   * Not the unseen queue — we keep full Article snapshots so Previous can revisit
   * after items leave the unseen list (marked seen).
   */
  const [viewHistory, setViewHistory] = useState<Article[]>([]);
  /** Index into viewHistory for the story currently shown. */
  const [sessionIndex, setSessionIndex] = useState(0);

  const [sessionCount, setSessionCount] = useState(0);
  const [reloadNonce, setReloadNonce] = useState(0);

  const [savedLinks, setSavedLinks] = useState<Set<string>>(new Set());

  const pageSize = DEFAULT_PAGE_SIZE;
  const nextPageRef = useRef(2);

  const lastPage = Math.max(1, Math.ceil(totalRows / pageSize) || 1);

  const canFetchMore =
    totalRows > 0 &&
    nextPageRef.current <= lastPage &&
    pool.length < totalRows;

  const loadInitial = useCallback(
    async (options?: { refresh?: boolean }) => {
      setInitialLoading(true);
      setError(null);
      try {
        const result = await fetchNewsPage({
          page: 1,
          pageSize,
          refresh: options?.refresh === true,
        });
        setPool(result.articles);
        setTotalRows(result.totalCount);
        nextPageRef.current = 2;
        setSessionCount(0);
        setSeenBrowseIndex(0);
        setViewHistory([]);
        setSessionIndex(0);
        debugFeedState("initial fetch ok", {
          articles: result.articles.length,
          totalCount: result.totalCount,
        });
      } catch (e) {
        setError(
          e instanceof Error ? e.message : "Something went wrong loading the feed.",
        );
        setPool([]);
        setTotalRows(0);
        debugFeedState("initial fetch error", {
          message: e instanceof Error ? e.message : String(e),
        });
      } finally {
        setInitialLoading(false);
        debugFeedState("initial loading cleared", {});
      }
    },
    [pageSize, reloadNonce],
  );

  const loadMore = useCallback(async () => {
    if (initialLoading || loadingMore) return;
    const lp = Math.max(1, Math.ceil(totalRows / pageSize) || 1);
    if (nextPageRef.current > lp) return;

    setLoadingMore(true);
    try {
      const page = nextPageRef.current;
      const result = await fetchNewsPage({
        page,
        pageSize,
        refresh: false,
      });
      setPool((prev) => {
        const have = new Set(prev.map((a) => normalizeArticleLink(a.link)));
        const add = result.articles.filter(
          (a) => !have.has(normalizeArticleLink(a.link)),
        );
        return [...prev, ...add];
      });
      if (result.articles.length === 0) {
        nextPageRef.current = lp + 1;
      } else {
        nextPageRef.current = page + 1;
      }
      debugFeedState("loadMore ok", {
        page,
        added: result.articles.length,
        nextPageRef: nextPageRef.current,
      });
    } catch (e) {
      console.error("[NewsFeed] loadMore failed", e);
      debugFeedState("loadMore error", { error: String(e) });
    } finally {
      setLoadingMore(false);
    }
  }, [initialLoading, loadingMore, totalRows, pageSize]);

  useEffect(() => {
    setSeen(loadSeenLinks());
    setSeenReady(true);
    setSavedLinks(loadSavedLinks());
  }, []);

  useEffect(() => {
    void loadInitial();
  }, [loadInitial]);

  const markSeen = useCallback((link: string) => {
    const key = normalizeArticleLink(link);
    setSeen((prev) => {
      if (prev.has(key)) return prev;
      const next = new Set(prev);
      next.add(key);
      saveSeenLinks(next);
      return next;
    });
  }, []);

  const categories = useMemo(() => uniqueCategories(pool), [pool]);

  const filtered = useMemo(
    () => filterArticles(pool, category, search, "All"),
    [pool, category, search],
  );

  const unseenQueue = useMemo(
    () =>
      filtered.filter((a) => !seen.has(normalizeArticleLink(a.link || ""))),
    [filtered, seen],
  );

  /** Stable head link for session-path seeding (avoid effect running every render). */
  const unseenHeadLink = unseenQueue[0]?.link ?? null;

  useEffect(() => {
    setSeenBrowseIndex(0);
    setViewHistory([]);
    setSessionIndex(0);
  }, [showSeen, category, search]);

  const current: Article | null = useMemo(() => {
    if (showSeen) {
      return seenBrowseIndex < filtered.length
        ? filtered[seenBrowseIndex] ?? null
        : null;
    }
    if (viewHistory.length === 0) {
      return unseenQueue[0] ?? null;
    }
    if (sessionIndex < 0 || sessionIndex >= viewHistory.length) {
      return null;
    }
    const atEnd = sessionIndex === viewHistory.length - 1;
    if (atEnd && unseenQueue.length === 0) {
      return null;
    }
    const snapshot = viewHistory[sessionIndex];
    const linkKey = normalizeArticleLink(snapshot.link || "");
    const fresh = filtered.find(
      (a) => normalizeArticleLink(a.link || "") === linkKey,
    );
    return fresh ?? snapshot;
  }, [
    showSeen,
    filtered,
    seenBrowseIndex,
    viewHistory,
    sessionIndex,
    unseenQueue,
  ]);

  /** Seed view history once we have an unseen head and history is empty. */
  useEffect(() => {
    if (showSeen) return;
    if (viewHistory.length !== 0) return;
    const head = unseenQueue[0];
    if (!head) return;
    setViewHistory([head]);
    setSessionIndex(0);
  }, [showSeen, unseenHeadLink, viewHistory.length]);

  const storyNumber = sessionCount + 1;
  const unseenAhead = Math.max(0, unseenQueue.length - 1);

  useEffect(() => {
    if (!seenReady || initialLoading) return;
    if (loadingMore) return;
    if (showSeen) return;
    if (totalRows === 0) return;
    if (pool.length === 0) return;
    if (unseenQueue.length >= QUEUE_LOW_WATER) return;
    if (!canFetchMore) return;
    void loadMore();
  }, [
    seenReady,
    initialLoading,
    loadingMore,
    showSeen,
    unseenQueue.length,
    totalRows,
    pool.length,
    canFetchMore,
    loadMore,
  ]);

  useEffect(() => {
    if (!DEBUG) return;
    debugFeedState("state snapshot", {
      initialLoading,
      loadingMore,
      seenReady,
      showSeen,
      poolLen: pool.length,
      totalRows,
      filteredLen: filtered.length,
      unseenLen: unseenQueue.length,
      canFetchMore,
      hasCurrent: Boolean(current),
      currentLink: current?.link ?? null,
      viewHistoryLen: viewHistory.length,
      sessionIndex,
    });
  }, [
    initialLoading,
    loadingMore,
    seenReady,
    showSeen,
    pool.length,
    totalRows,
    filtered.length,
    unseenQueue.length,
    canFetchMore,
    current,
    viewHistory.length,
    sessionIndex,
  ]);

  const handleNext = useCallback(() => {
    if (!current) return;
    if (showSeen) {
      markSeen(current.link || "");
      setSessionCount((c) => c + 1);
      setSeenBrowseIndex((i) => i + 1);
      return;
    }

    if (viewHistory.length === 0 || sessionIndex >= viewHistory.length) return;

    const atEnd = sessionIndex === viewHistory.length - 1;
    if (!atEnd) {
      const before = viewHistory.length;
      markSeen(current.link || "");
      setSessionCount((c) => c + 1);
      setSessionIndex((i) => i + 1);
      if (DEBUG) {
        console.log("[NewsFeed] Next (within history)", {
          link: current.link,
          historyLenBefore: before,
          historyLenAfter: before,
        });
      }
      return;
    }

    /* At end of history, `current` matches this slot (re-resolved from filtered). */
    markSeen(current.link || "");
    setSessionCount((c) => c + 1);

    const nextSeen = new Set(seen);
    nextSeen.add(normalizeArticleLink(current.link || ""));
    const nextArticle = filtered.find(
      (a) => !nextSeen.has(normalizeArticleLink(a.link || "")),
    );

    if (nextArticle) {
      const before = viewHistory.length;
      setViewHistory((prev) => [...prev, nextArticle]);
      setSessionIndex((c) => c + 1);
      if (DEBUG) {
        console.log("[NewsFeed] Next (append unseen)", {
          leftLink: current.link,
          nextLink: nextArticle.link,
          historyLenBefore: before,
          historyLenAfter: before + 1,
        });
      }
    }
  }, [current, showSeen, markSeen, viewHistory, sessionIndex, filtered, seen]);

  const handlePrevious = useCallback(() => {
    if (showSeen) {
      setSeenBrowseIndex((i) => Math.max(0, i - 1));
      return;
    }
    if (sessionIndex <= 0) return;
    const before = viewHistory.length;
    const nextIdx = sessionIndex - 1;
    const target = viewHistory[nextIdx];
    setSessionIndex(nextIdx);
    if (DEBUG) {
      console.log("[NewsFeed] Previous", {
        link: target?.link,
        historyLenBefore: before,
        historyLenAfter: before,
        newIndex: nextIdx,
      });
    }
  }, [showSeen, sessionIndex, viewHistory]);

  const handleToggleSave = useCallback(() => {
    if (!current?.link) return;
    const key = normalizeArticleLink(current.link);
    setSavedLinks((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      saveSavedLinks(next);
      return next;
    });
  }, [current]);

  const handleResetSeen = useCallback(() => {
    clearSeenLinks();
    setSeen(new Set());
    setSeenBrowseIndex(0);
    setViewHistory([]);
    setSessionIndex(0);
  }, []);

  const handleRefreshFeeds = useCallback(() => {
    void loadInitial({ refresh: true });
  }, [loadInitial]);

  const handleTryAgain = () => {
    setReloadNonce((n) => n + 1);
  };

  const feedReady = seenReady && !initialLoading;

  /** No matching rows after filters (distinct from “all seen”). */
  const noMatches =
    feedReady && !error && pool.length > 0 && filtered.length === 0;

  /** Pool empty from API (no rows at all). */
  const emptyPool = feedReady && !error && pool.length === 0;

  /** All items in the current filter are already seen; no unseen left in loaded data. */
  const noUnseenInPool =
    feedReady && !error && !showSeen && filtered.length > 0 && unseenQueue.length === 0;

  /** Server has no more pages we haven’t requested (or nothing to paginate). */
  const exhaustedRemote = !canFetchMore || totalRows === 0;

  const showCaughtUp =
    noUnseenInPool && exhaustedRemote && !loadingMore;

  /** Still pulling pages hoping to find an unseen story. */
  const fetchingMoreForUnseen =
    noUnseenInPool && !exhaustedRemote && (loadingMore || canFetchMore);

  const atEndOfSeenBrowse =
    showSeen && filtered.length > 0 && seenBrowseIndex >= filtered.length;

  const previousDisabled = showSeen
    ? seenBrowseIndex <= 0
    : sessionIndex <= 0;

  const savedNow = current ? isLinkSaved(current.link, savedLinks) : false;

  const utilBtn =
    "rounded-md px-2 py-1 text-[11px] font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 sm:text-xs";

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50/70 via-white to-slate-50/30">
      <Header />

      <main
        className="mx-auto max-w-5xl px-4 pb-16 pt-4 sm:px-6 lg:px-8"
        aria-busy={initialLoading || loadingMore}
      >
        <div className="mb-5 border-b border-slate-200/50 pb-5">
          <Filters
            categories={categories}
            activeCategory={category}
            onCategoryChange={setCategory}
            search={search}
            onSearchChange={setSearch}
          />
          <div
            className="mt-4 flex flex-wrap items-center justify-center gap-x-1 gap-y-1 border-t border-slate-100 pt-4 text-slate-500 sm:justify-between"
            role="toolbar"
            aria-label="Feed utilities"
          >
            <div className="flex flex-wrap items-center justify-center gap-x-0.5 sm:justify-start">
              <button
                type="button"
                onClick={() => setShowSeen((s) => !s)}
                className={utilBtn}
              >
                {showSeen ? "Hide seen stories" : "Show seen stories again"}
              </button>
              <span className="hidden text-slate-300 sm:inline" aria-hidden>
                ·
              </span>
              <button
                type="button"
                onClick={handleResetSeen}
                className={utilBtn}
              >
                Reset seen
              </button>
            </div>
            <button
              type="button"
              onClick={handleRefreshFeeds}
              disabled={initialLoading}
              className={`${utilBtn} disabled:opacity-40`}
            >
              Refresh feeds
            </button>
          </div>
        </div>

        {/* 1) Initial load — full-page skeleton only here */}
        {initialLoading && (
          <>
            <p className="sr-only" role="status">
              Loading story
            </p>
            <LoadingSkeleton />
          </>
        )}

        {/* 2) Error */}
        {feedReady && error && (
          <div
            role="alert"
            className="mx-auto max-w-lg rounded-2xl border border-red-200/90 bg-red-50/90 px-6 py-10 text-center shadow-sm"
          >
            <p className="text-lg font-semibold text-red-950">
              We couldn&apos;t load the feed
            </p>
            <p className="mt-2 text-sm text-red-900/80">{error}</p>
            <p className="mt-3 text-xs text-red-800/70">
              API:{" "}
              <code className="rounded bg-red-100 px-1.5 py-0.5 font-mono text-[11px]">
                {API_HINT}
              </code>
            </p>
            <button
              type="button"
              onClick={handleTryAgain}
              className="mt-6 rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white"
            >
              Try again
            </button>
          </div>
        )}

        {/* 3) Empty API result */}
        {feedReady && !error && emptyPool && (
          <p className="text-center text-slate-500">
            No stories yet. Try refreshing feeds.
          </p>
        )}

        {/* 4) Filters exclude everything */}
        {noMatches && (
          <p className="text-center text-slate-600">
            Nothing matches your filters. Adjust search or topic.
          </p>
        )}

        {/* 5) Story card — only when we have a concrete article */}
        {feedReady && !error && current && !emptyPool && (
          <div className="space-y-5">
            <div className="flex flex-col items-center justify-between gap-2 text-center sm:flex-row sm:text-left">
              <div className="space-y-0.5">
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Now reading
                </p>
                <p className="text-sm text-slate-600">
                  <span className="font-medium text-slate-800">
                    Story {Math.min(storyNumber, totalRows || storyNumber)} of{" "}
                    {totalRows || "—"}
                  </span>
                  {showSeen ? (
                    <span className="text-slate-400">
                      {" "}
                      · {seenBrowseIndex + 1} / {filtered.length} in view
                    </span>
                  ) : (
                    <span className="text-slate-400">
                      {" "}
                      · {unseenAhead} unseen ahead
                    </span>
                  )}
                </p>
              </div>
              {loadingMore && (
                <p className="text-[11px] font-medium text-slate-400">
                  Loading more…
                </p>
              )}
            </div>

            <SingleStoryHero article={current} />

            <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 pt-1">
              <div className="flex flex-wrap items-stretch justify-center gap-3 sm:justify-between">
                <div className="flex flex-1 flex-wrap items-center justify-center gap-3 sm:justify-start sm:gap-4">
                  <button
                    type="button"
                    onClick={handlePrevious}
                    disabled={previousDisabled}
                    className="min-h-[3rem] min-w-[9.5rem] flex-1 rounded-xl border border-slate-200/90 bg-white px-5 py-3 text-sm font-semibold text-slate-800 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:border-slate-100 disabled:text-slate-300 disabled:shadow-none sm:flex-none sm:min-w-[10.5rem]"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    onClick={handleNext}
                    disabled={!current}
                    className="min-h-[3rem] min-w-[9.5rem] flex-1 rounded-xl bg-slate-900 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-900/20 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none sm:flex-none sm:min-w-[11rem]"
                  >
                    Next story
                  </button>
                </div>
                <button
                  type="button"
                  onClick={handleToggleSave}
                  aria-pressed={savedNow}
                  className={`rounded-lg border px-4 py-2.5 text-xs font-medium transition sm:self-center ${
                    savedNow
                      ? "border-emerald-200/90 bg-emerald-50/90 text-emerald-900"
                      : "border-slate-200/80 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  {savedNow ? "Saved" : "Save for later"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 6) End of “show seen” list */}
        {feedReady && !error && atEndOfSeenBrowse && (
          <div className="mx-auto max-w-lg space-y-5 rounded-2xl border border-slate-200/90 bg-white/90 px-8 py-9 text-center shadow-sm">
            <p className="text-sm leading-relaxed text-slate-600">
              You&apos;ve reached the end of this list.
            </p>
            <button
              type="button"
              onClick={() => {
                setShowSeen(false);
                setSeenBrowseIndex(0);
              }}
              className="rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white shadow-md transition hover:bg-slate-800"
            >
              Back to new stories
            </button>
          </div>
        )}

        {/* 7) All caught up (every loaded story seen, no more pages) */}
        {feedReady && !error && showCaughtUp && !current && (
          <div className="mx-auto max-w-lg rounded-2xl border border-emerald-200/80 bg-emerald-50/90 px-8 py-10 text-center shadow-sm">
            <p className="text-xl font-semibold text-emerald-950">
              You&apos;re all caught up 🎉
            </p>
            <p className="mt-3 text-sm leading-relaxed text-emerald-900/85">
              You&apos;ve seen every story in your feed. Open older items with the
              button below, or refresh for new headlines.
            </p>
            <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-center">
              <button
                type="button"
                onClick={() => setShowSeen(true)}
                className="rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white shadow-md transition hover:bg-slate-800"
              >
                Show seen stories again
              </button>
              <button
                type="button"
                onClick={() => void loadInitial({ refresh: true })}
                disabled={initialLoading}
                className="rounded-xl border border-emerald-300/80 bg-white px-5 py-2.5 text-sm font-semibold text-emerald-950 shadow-sm transition hover:bg-emerald-50 disabled:opacity-50"
              >
                Refresh feeds
              </button>
            </div>
          </div>
        )}

        {/* 8) Fetching more pages — not initial skeleton */}
        {feedReady &&
          !error &&
          fetchingMoreForUnseen &&
          !current &&
          !noMatches && (
            <div className="mx-auto max-w-md rounded-2xl border border-slate-200/80 bg-white/90 px-6 py-8 text-center shadow-sm">
              <p className="text-sm font-medium text-slate-700">
                Loading more stories…
              </p>
              <p className="mt-2 text-xs text-slate-500">
                Looking for a story you haven&apos;t read yet.
              </p>
            </div>
          )}

        {/* 9) Fallback: feed ready, no card, not covered above */}
        {feedReady &&
          !error &&
          !current &&
          !emptyPool &&
          !noMatches &&
          !showCaughtUp &&
          !fetchingMoreForUnseen &&
          !atEndOfSeenBrowse && (
            <p className="text-center text-sm text-slate-500">
              No story to show. Try &quot;Show seen stories again&quot; or refresh
              feeds.
            </p>
          )}
      </main>

      <footer className="border-t border-slate-200/60 bg-white/40 py-8 text-center">
        <p className="text-[10px] font-medium uppercase tracking-[0.16em] text-slate-400">
          Canada Brief
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Powered by your FastAPI backend · Built with Next.js
        </p>
      </footer>
    </div>
  );
}
