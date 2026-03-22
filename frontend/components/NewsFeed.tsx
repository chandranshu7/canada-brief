"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Article } from "@/lib/types";
import { DEFAULT_PAGE_SIZE, fetchNewsPage } from "@/lib/api";
import { filterArticles, uniqueCategories } from "@/lib/filterArticles";
import { rebuildStoryQueue } from "@/lib/storyQueue";
import {
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

/** Next unseen story in pool after filters (used when advancing without history). */
function findNextUnseen(
  pool: Article[],
  category: string,
  search: string,
  nextSeen: Set<string>,
): Article | null {
  const rows = filterArticles(pool, category, search, "All");
  return (
    rows.find((a) => !nextSeen.has(normalizeArticleLink(a.link || ""))) ?? null
  );
}

function mergePoolWithAdded(base: Article[], added: Article[]): Article[] {
  const keys = new Set(base.map((a) => normalizeArticleLink(a.link || "")));
  const out = [...base];
  for (const a of added) {
    const k = normalizeArticleLink(a.link || "");
    if (!keys.has(k)) {
      out.push(a);
      keys.add(k);
    }
  }
  return out;
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

  /**
   * Ordered list of stories visited in this session (normal mode).
   * Not the unseen queue — we keep full Article snapshots so Previous can revisit
   * after items leave the unseen list (marked seen).
   */
  const [viewHistory, setViewHistory] = useState<Article[]>([]);
  /** Index into viewHistory for the story currently shown. */
  const [sessionIndex, setSessionIndex] = useState(0);

  const [reloadNonce, setReloadNonce] = useState(0);

  const [nextBusy, setNextBusy] = useState(false);
  const nextBusyRef = useRef(false);

  const pageSize = DEFAULT_PAGE_SIZE;
  const nextPageRef = useRef(2);
  /** Latest filters for buffer seeding after fetch (avoid loadInitial deps that retrigger mount effect). */
  const categoryRef = useRef(category);
  const searchRef = useRef(search);
  /** Link to preserve when filters change (set before category/search updates). */
  const pendingPreserveLinkRef = useRef<string | null>(null);
  /** Skip first filter effect runs (initial load already seeded via loadInitial). */
  const filterCategoryPrimedRef = useRef(false);
  const filterSearchPrimedRef = useRef(false);

  const poolRef = useRef(pool);
  const seenRef = useRef(seen);
  /** Coalesce concurrent loadMore (effect + Next button) onto one fetch. */
  const loadMoreInFlightRef = useRef<Promise<Article[]> | null>(null);
  useEffect(() => {
    poolRef.current = pool;
    seenRef.current = seen;
  }, [pool, seen]);

  useEffect(() => {
    categoryRef.current = category;
    searchRef.current = search;
  }, [category, search]);

  const lastPage = Math.max(1, Math.ceil(totalRows / pageSize) || 1);

  const canFetchMore =
    totalRows > 0 &&
    nextPageRef.current <= lastPage &&
    pool.length < totalRows;

  const loadInitial = useCallback(async () => {
    setInitialLoading(true);
    setError(null);
    try {
      const result = await fetchNewsPage({
        page: 1,
        pageSize,
        refresh: false,
      });
      setPool(result.articles);
      setTotalRows(result.totalCount);
      nextPageRef.current = 2;

      const seenSet = loadSeenLinks();
      setSeen(seenSet);

      const queue = rebuildStoryQueue({
        pool: result.articles,
        category: categoryRef.current,
        search: searchRef.current,
        seen: seenSet,
        showSeen: false,
        currentLinkKey: null,
      });
      setViewHistory(queue.viewHistory);
      setSessionIndex(queue.sessionIndex);
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
      setViewHistory([]);
      setSessionIndex(0);
      debugFeedState("initial fetch error", {
        message: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setInitialLoading(false);
      debugFeedState("initial loading cleared", {});
    }
  }, [pageSize, reloadNonce]);

  const loadMore = useCallback(async (): Promise<Article[]> => {
    if (initialLoading) return [];
    const existing = loadMoreInFlightRef.current;
    if (existing) return existing;

    const lp = Math.max(1, Math.ceil(totalRows / pageSize) || 1);
    if (nextPageRef.current > lp) return [];

    const promise = (async (): Promise<Article[]> => {
      setLoadingMore(true);
      try {
        const page = nextPageRef.current;
        const result = await fetchNewsPage({
          page,
          pageSize,
          refresh: false,
        });
        const prevPool = poolRef.current;
        const have = new Set(
          prevPool.map((a) => normalizeArticleLink(a.link || "")),
        );
        const add = result.articles.filter(
          (a) => !have.has(normalizeArticleLink(a.link || "")),
        );
        setPool((prev) => {
          const have2 = new Set(
            prev.map((a) => normalizeArticleLink(a.link || "")),
          );
          const add2 = result.articles.filter(
            (a) => !have2.has(normalizeArticleLink(a.link || "")),
          );
          return [...prev, ...add2];
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
        return add;
      } catch (e) {
        console.error("[NewsFeed] loadMore failed", e);
        debugFeedState("loadMore error", { error: String(e) });
        return [];
      } finally {
        setLoadingMore(false);
        loadMoreInFlightRef.current = null;
      }
    })();

    loadMoreInFlightRef.current = promise;
    return promise;
  }, [initialLoading, totalRows, pageSize]);

  useEffect(() => {
    setSeen(loadSeenLinks());
    setSeenReady(true);
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

  const current: Article | null = useMemo(() => {
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
  }, [filtered, viewHistory, sessionIndex, unseenQueue]);

  useEffect(() => {
    if (!seenReady || initialLoading) return;
    if (loadingMore) return;
    if (totalRows === 0) return;
    if (pool.length === 0) return;
    if (unseenQueue.length >= QUEUE_LOW_WATER) return;
    if (!canFetchMore) return;
    void loadMore();
  }, [
    seenReady,
    initialLoading,
    loadingMore,
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
    pool.length,
    totalRows,
    filtered.length,
    unseenQueue.length,
    canFetchMore,
    current,
    viewHistory.length,
    sessionIndex,
  ]);

  const canFetchMorePages = useCallback(() => {
    const lp = Math.max(1, Math.ceil(totalRows / pageSize) || 1);
    return (
      totalRows > 0 &&
      nextPageRef.current <= lp &&
      poolRef.current.length < totalRows
    );
  }, [totalRows, pageSize]);

  const handleNext = useCallback(async () => {
    if (!current) return;
    if (nextBusyRef.current) return;
    nextBusyRef.current = true;
    setNextBusy(true);

    const beforeLink = current.link ?? "";
    const beforeId = current.id;
    let poolSnap = [...poolRef.current];
    const queueLenBefore = poolSnap.length;

    const logNext = (
      after: Article | null,
      poolLenAfter: number,
      extra?: Record<string, unknown>,
    ) => {
      console.log("[NewsFeed] Next story", {
        before: { id: beforeId, link: beforeLink },
        after: after
          ? { id: after.id, link: after.link ?? "" }
          : null,
        queueLenBefore,
        queueLenAfter: poolLenAfter,
        viewHistoryLen: viewHistory.length,
        sessionIndexBefore: sessionIndex,
        ...extra,
      });
    };

    try {
      if (viewHistory.length > 0 && sessionIndex >= viewHistory.length) {
        return;
      }

      const nextSeenBase = new Set(seenRef.current);
      nextSeenBase.add(normalizeArticleLink(current.link || ""));

      const advanceWithFetch = async (): Promise<Article | null> => {
        let nextArticle = findNextUnseen(
          poolSnap,
          category,
          search,
          nextSeenBase,
        );
        let guard = 0;
        while (!nextArticle && guard < 12 && canFetchMorePages()) {
          guard += 1;
          const added = await loadMore();
          poolSnap = mergePoolWithAdded(poolSnap, added);
          nextArticle = findNextUnseen(
            poolSnap,
            category,
            search,
            nextSeenBase,
          );
          if (added.length === 0 && !nextArticle) break;
        }
        return nextArticle;
      };

      // No session history yet: current comes from unseenQueue[0]; Next must advance.
      if (viewHistory.length === 0) {
        markSeen(current.link || "");
        const nextArticle = await advanceWithFetch();
        logNext(nextArticle, poolSnap.length, { mode: "empty_history" });
        if (nextArticle) {
          setViewHistory([nextArticle]);
          setSessionIndex(0);
        }
        return;
      }

      const atEnd = sessionIndex === viewHistory.length - 1;
      if (!atEnd) {
        const nextStory = viewHistory[sessionIndex + 1];
        markSeen(current.link || "");
        setSessionIndex((i) => i + 1);
        logNext(nextStory, poolRef.current.length, { mode: "within_history" });
        return;
      }

      markSeen(current.link || "");
      const nextArticle = await advanceWithFetch();
      logNext(nextArticle, poolSnap.length, { mode: "append_after_history" });
      if (nextArticle) {
        setViewHistory((prev) => [...prev, nextArticle]);
        setSessionIndex((c) => c + 1);
      }
    } finally {
      nextBusyRef.current = false;
      setNextBusy(false);
    }
  }, [
    current,
    viewHistory,
    sessionIndex,
    category,
    search,
    markSeen,
    loadMore,
    canFetchMorePages,
  ]);

  const handlePrevious = useCallback(() => {
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
  }, [sessionIndex, viewHistory]);

  const handleCategoryChange = useCallback(
    (cat: string) => {
      pendingPreserveLinkRef.current = current?.link ?? null;
      setCategory(cat);
    },
    [current],
  );

  const handleSearchChange = useCallback(
    (q: string) => {
      pendingPreserveLinkRef.current = current?.link ?? null;
      setSearch(q);
    },
    [current],
  );

  const handleTryAgain = () => {
    setReloadNonce((n) => n + 1);
  };

  const feedReady = seenReady && !initialLoading;

  /** Topic change: rebuild immediately (preserve current story when still in list). */
  useEffect(() => {
    if (!feedReady) return;
    if (!filterCategoryPrimedRef.current) {
      filterCategoryPrimedRef.current = true;
      return;
    }
    const raw = pendingPreserveLinkRef.current;
    pendingPreserveLinkRef.current = null;
    const key = raw ? normalizeArticleLink(raw) : null;
    const out = rebuildStoryQueue({
      pool: poolRef.current,
      category,
      search: searchRef.current,
      seen: seenRef.current,
      showSeen: false,
      currentLinkKey: key,
    });
    console.log("[NewsFeed] queue rebuilt", {
      trigger: "category",
      reason: out.reason,
      currentLinkKey: key,
    });
    setViewHistory(out.viewHistory);
    setSessionIndex(out.sessionIndex);
  }, [category, feedReady]);

  /** Search typing: debounced rebuild so we don’t reset the queue on every keystroke. */
  useEffect(() => {
    if (!feedReady) return;
    const id = window.setTimeout(() => {
      if (!filterSearchPrimedRef.current) {
        filterSearchPrimedRef.current = true;
        return;
      }
      const raw = pendingPreserveLinkRef.current;
      pendingPreserveLinkRef.current = null;
      const key = raw ? normalizeArticleLink(raw) : null;
      const out = rebuildStoryQueue({
        pool: poolRef.current,
        category: categoryRef.current,
        search: searchRef.current,
        seen: seenRef.current,
        showSeen: false,
        currentLinkKey: key,
      });
      console.log("[NewsFeed] queue rebuilt", {
        trigger: "search",
        reason: out.reason,
        currentLinkKey: key,
      });
      setViewHistory(out.viewHistory);
      setSessionIndex(out.sessionIndex);
    }, 320);
    return () => window.clearTimeout(id);
  }, [search, feedReady]);

  /** No matching rows after filters (distinct from “all seen”). */
  const noMatches =
    feedReady && !error && pool.length > 0 && filtered.length === 0;

  /** Pool empty from API (no rows at all). */
  const emptyPool = feedReady && !error && pool.length === 0;

  /** All items in the current filter are already seen; no unseen left in loaded data. */
  const noUnseenInPool =
    feedReady && !error && filtered.length > 0 && unseenQueue.length === 0;

  /** Server has no more pages we haven’t requested (or nothing to paginate). */
  const exhaustedRemote = !canFetchMore || totalRows === 0;

  const showCaughtUp =
    noUnseenInPool && exhaustedRemote && !loadingMore;

  /** Still pulling pages hoping to find an unseen story. */
  const fetchingMoreForUnseen =
    noUnseenInPool && !exhaustedRemote && (loadingMore || canFetchMore);

  const previousDisabled = sessionIndex <= 0;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50/70 via-white to-slate-50/30">
      <Header />

      <main
        className="mx-auto max-w-5xl px-4 pb-16 pt-4 sm:px-6 lg:px-8"
        aria-busy={initialLoading || loadingMore}
      >
        <div className="mb-6 border-b border-slate-200/50 pb-6">
          <Filters
            categories={categories}
            activeCategory={category}
            onCategoryChange={handleCategoryChange}
            search={search}
            onSearchChange={handleSearchChange}
          />
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
            No stories yet. Check back later.
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
          <div className="space-y-6">
            <SingleStoryHero article={current} />

            <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 pt-1">
              <div className="flex flex-wrap items-center justify-center gap-3 sm:gap-4">
                <button
                  type="button"
                  onClick={handlePrevious}
                  disabled={previousDisabled}
                  className="min-h-[3rem] min-w-[9.5rem] flex-1 rounded-xl border border-slate-200/90 bg-white px-5 py-3 text-sm font-semibold text-slate-800 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:border-slate-100 disabled:text-slate-300 disabled:shadow-none sm:max-w-[11rem] sm:flex-none sm:min-w-[10.5rem]"
                >
                  Previous
                </button>
                <button
                  type="button"
                  onClick={() => void handleNext()}
                  disabled={!current || nextBusy}
                  className="min-h-[3rem] min-w-[9.5rem] flex-1 rounded-xl bg-slate-900 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-900/20 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 disabled:shadow-none sm:max-w-[12rem] sm:flex-none sm:min-w-[11rem]"
                >
                  Next story
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 6) All caught up (every loaded story seen, no more pages) */}
        {feedReady && !error && showCaughtUp && !current && (
          <div className="mx-auto max-w-lg rounded-2xl border border-emerald-200/80 bg-emerald-50/90 px-8 py-10 text-center shadow-sm">
            <p className="text-xl font-semibold text-emerald-950">
              You&apos;re all caught up 🎉
            </p>
            <p className="mt-3 text-sm leading-relaxed text-emerald-900/85">
              You&apos;ve seen every story loaded in your feed. New headlines will
              appear when the feed updates.
            </p>
          </div>
        )}

        {/* 7) Fetching more pages — not initial skeleton */}
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

        {/* 8) Fallback: feed ready, no card, not covered above */}
        {feedReady &&
          !error &&
          !current &&
          !emptyPool &&
          !noMatches &&
          !showCaughtUp &&
          !fetchingMoreForUnseen && (
            <p className="text-center text-sm text-slate-500">
              No story to show right now.
            </p>
          )}
      </main>

      <footer className="border-t border-slate-200/60 bg-white/40 py-8 text-center">
        <p className="text-xs text-slate-500">© 2026 Canada Brief</p>
      </footer>
    </div>
  );
}
