"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Article } from "@/lib/types";
import { fetchNewsPage } from "@/lib/api";
import { dedupeFeedArticlesStable } from "@/lib/feedDedupe";
import { filterArticles, uniqueCategories, uniqueSources } from "@/lib/filterArticles";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import { buildStoryLocationContext } from "@/lib/locationContext";
import type { FeedMode, LocationPreference } from "@/lib/locationPreference";
import {
  buildPreferenceKey,
  DEFAULT_APP_PREFERENCES,
  EMPTY_LOCATION,
  loadAppPreferences,
  resetFeedPreferencesToDefaults,
  saveAppPreferences,
} from "@/lib/locationPreference";
import {
  clearAllSavedStories,
  getSavedStories,
  SAVED_STORIES_STORAGE_KEY,
  toggleSavedStory,
} from "@/lib/savedStories";
import {
  FOLLOWED_TOPICS_STORAGE_KEY,
  loadFollowedTopics,
  matchArticleToFollowedTopics,
  saveFollowedTopics,
  toggleFollowTopic,
  type FollowTopicId,
} from "@/lib/followedTopics";
import {
  PERSONALIZATION_STORAGE_KEY,
  categoryKeyForArticle,
  hasPersonalizationSignal,
  loadPersonalization,
  recordArticleOpen,
  recordArticleSaved,
  recordSearchInterest,
  savePersonalization,
  sortByPersonalizedAffinity,
} from "@/lib/personalization";
import {
  loadSeenLinks,
  normalizeArticleLink,
  saveSeenLinks,
} from "@/lib/seenArticles";
import { ArticleDetailModal } from "./ArticleDetailModal";
import { DailyBriefCard } from "./DailyBriefCard";
import type { BottomNavTab } from "./BottomNav";
import { BottomNav } from "./BottomNav";
import { CategoryStrip } from "./CategoryStrip";
import { FeedCard } from "./FeedCard";
import { ForYouSection } from "./ForYouSection";
import { FeedTopBar } from "./FeedTopBar";
import { LocalSetupCard } from "./LocalSetupCard";
import { FeedCardSkeleton } from "./FeedCardSkeleton";
import { FeedEmptyState } from "./FeedEmptyState";
import { LoadingSkeleton } from "./LoadingSkeleton";
import { ProfileScreen } from "./ProfileScreen";
import { SourceChips } from "./SourceChips";

const API_HINT =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Slightly larger pages for scroll feed (backend max applies). */
const FEED_PAGE_SIZE = 15;

const DEBUG = process.env.NODE_ENV === "development";

function debugFeedState(label: string, payload: Record<string, unknown>) {
  if (!DEBUG) return;
  console.log(`[NewsFeed] ${label}`, payload);
}

export function NewsFeed() {
  const [pool, setPool] = useState<Article[]>([]);
  const [totalRows, setTotalRows] = useState(0);
  const [initialLoading, setInitialLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [category, setCategory] = useState("All");
  const [search, setSearch] = useState("");
  /** Debounced for API `q` — backend search across full dataset (general or local). */
  const debouncedSearch = useDebouncedValue(search, 350);
  const [sourceFilter, setSourceFilter] = useState("All");

  const [seen, setSeen] = useState<Set<string>>(new Set());
  const [seenReady, setSeenReady] = useState(false);

  const [reloadNonce, setReloadNonce] = useState(0);

  const [feedMode, setFeedMode] = useState<FeedMode>(
    DEFAULT_APP_PREFERENCES.feedMode,
  );
  const [locationPref, setLocationPref] = useState<LocationPreference>(
    DEFAULT_APP_PREFERENCES.location,
  );
  const [prefsHydrated, setPrefsHydrated] = useState(false);

  const [navTab, setNavTab] = useState<BottomNavTab>("home");
  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null);
  /** Bumps when bookmarks change so lists re-render from localStorage. */
  const [savedRev, setSavedRev] = useState(0);
  const [savedBookmarks, setSavedBookmarks] = useState<Article[]>([]);

  const [followedTopics, setFollowedTopics] = useState<FollowTopicId[]>([]);
  const [topicsHydrated, setTopicsHydrated] = useState(false);

  /** Category affinity from opens / saves / search (localStorage). */
  const [categoryAffinity, setCategoryAffinity] = useState<
    Record<string, number>
  >({});
  const [affinityHydrated, setAffinityHydrated] = useState(false);

  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const loadSentinelRef = useRef<HTMLDivElement | null>(null);

  const pageSize = FEED_PAGE_SIZE;
  const nextPageRef = useRef(2);

  const poolRef = useRef(pool);
  const seenRef = useRef(seen);
  const locationPrefRef = useRef(locationPref);
  const feedModeRef = useRef(feedMode);
  const loadMoreInFlightRef = useRef<Promise<Article[]> | null>(null);

  useEffect(() => {
    poolRef.current = pool;
    seenRef.current = seen;
    locationPrefRef.current = locationPref;
    feedModeRef.current = feedMode;
  }, [pool, seen, locationPref, feedMode]);

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === SAVED_STORIES_STORAGE_KEY) setSavedRev((n) => n + 1);
      if (e.key === FOLLOWED_TOPICS_STORAGE_KEY) {
        setFollowedTopics(loadFollowedTopics());
      }
      if (e.key === PERSONALIZATION_STORAGE_KEY) {
        setCategoryAffinity(loadPersonalization());
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  useEffect(() => {
    setFollowedTopics(loadFollowedTopics());
    setTopicsHydrated(true);
  }, []);

  useEffect(() => {
    setCategoryAffinity(loadPersonalization());
    setAffinityHydrated(true);
  }, []);

  useEffect(() => {
    if (!topicsHydrated) return;
    saveFollowedTopics(followedTopics);
    if (DEBUG) {
      console.log("[topic_follow] followed_topics", followedTopics);
    }
  }, [followedTopics, topicsHydrated]);

  useEffect(() => {
    if (!affinityHydrated) return;
    savePersonalization(categoryAffinity);
    if (DEBUG && hasPersonalizationSignal(categoryAffinity)) {
      console.log("[personalize] category_weights", categoryAffinity);
    }
  }, [categoryAffinity, affinityHydrated]);

  useEffect(() => {
    const p = loadAppPreferences();
    setFeedMode(p.feedMode);
    setLocationPref(p.location);
    setNavTab(p.feedMode === "local" ? "local" : "home");
    setPrefsHydrated(true);
  }, []);

  useEffect(() => {
    if (!prefsHydrated) return;
    saveAppPreferences({ feedMode, location: locationPref });
  }, [feedMode, locationPref, prefsHydrated]);

  useEffect(() => {
    setSavedBookmarks(getSavedStories());
  }, [savedRev]);

  const prefKey = useMemo(
    () => buildPreferenceKey({ feedMode, location: locationPref }),
    [feedMode, locationPref],
  );

  const hasLocalLocation = Boolean(locationPref.city && locationPref.province);

  const lastPage = Math.max(1, Math.ceil(totalRows / pageSize) || 1);

  const canFetchMore =
    totalRows > 0 &&
    nextPageRef.current <= lastPage &&
    pool.length < totalRows;

  const loadInitial = useCallback(async () => {
    setInitialLoading(true);
    setError(null);
    try {
      const mode = feedModeRef.current;
      const loc = locationPrefRef.current;
      if (mode === "local" && (!loc.city || !loc.province)) {
        setPool([]);
        setTotalRows(0);
        debugFeedState("local mode — awaiting location", {});
        return;
      }

      const q = debouncedSearch.trim();
      const result = await fetchNewsPage({
        page: 1,
        pageSize,
        refresh: false,
        mode: mode === "local" ? "local" : "general",
        city: mode === "local" ? loc.city : null,
        province: mode === "local" ? loc.province : null,
        provinceCode: mode === "local" ? loc.province_code : null,
        locationSlug: mode === "local" ? loc.slug : null,
        search: q || null,
      });
      const initialDeduped = dedupeFeedArticlesStable(result.articles);
      if (initialDeduped.removed > 0) {
        console.warn(
          `[NewsFeed] feed_dedupe initial removed=${initialDeduped.removed} keys=${initialDeduped.removedKeys.slice(0, 8).join("; ")}`,
        );
      }
      setPool(initialDeduped.items);
      setTotalRows(result.totalCount);
      nextPageRef.current = 2;

      const seenSet = loadSeenLinks();
      setSeen(seenSet);

      debugFeedState("initial fetch ok", {
        articles: result.articles.length,
        totalCount: result.totalCount,
      });
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Something went wrong loading the feed.",
      );
      if (poolRef.current.length === 0) {
        setPool([]);
        setTotalRows(0);
      }
    } finally {
      setInitialLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reloadNonce/prefKey force new callback when retry/location changes
  }, [pageSize, reloadNonce, prefKey, debouncedSearch]);

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
        const mode = feedModeRef.current;
        const loc = locationPrefRef.current;
        if (mode === "local" && (!loc.city || !loc.province)) {
          return [];
        }
        const q = debouncedSearch.trim();
        const result = await fetchNewsPage({
          page,
          pageSize,
          refresh: false,
          mode: mode === "local" ? "local" : "general",
          city: mode === "local" ? loc.city : null,
          province: mode === "local" ? loc.province : null,
          provinceCode: mode === "local" ? loc.province_code : null,
          locationSlug: mode === "local" ? loc.slug : null,
          search: q || null,
        });
        const merged = dedupeFeedArticlesStable([
          ...poolRef.current,
          ...result.articles,
        ]);
        if (merged.removed > 0) {
          console.warn(
            `[NewsFeed] feed_dedupe append removed=${merged.removed} keys=${merged.removedKeys.slice(0, 8).join("; ")}`,
          );
        }
        setPool(merged.items);
        if (result.articles.length === 0) {
          nextPageRef.current = lp + 1;
        } else {
          nextPageRef.current = page + 1;
        }
        return merged.items;
      } catch (e) {
        console.error("[NewsFeed] loadMore failed", e);
        return [];
      } finally {
        setLoadingMore(false);
        loadMoreInFlightRef.current = null;
      }
    })();

    loadMoreInFlightRef.current = promise;
    return promise;
  }, [initialLoading, totalRows, pageSize, debouncedSearch]);

  useEffect(() => {
    setSeen(loadSeenLinks());
    setSeenReady(true);
  }, []);

  useEffect(() => {
    if (!prefsHydrated) return;
    void loadInitial();
  }, [loadInitial, prefsHydrated]);

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

  /** Second pass: stable dedupe before render (defensive if state ever contained dupes). */
  const displayPool = useMemo(() => {
    const { items, removed, removedKeys } = dedupeFeedArticlesStable(pool);
    if (removed > 0) {
      console.warn(
        `[NewsFeed] feed_dedupe pre-render removed=${removed} keys=${removedKeys.slice(0, 8).join("; ")}`,
      );
    }
    return items;
  }, [pool]);

  const categories = useMemo(
    () => uniqueCategories(displayPool),
    [displayPool],
  );
  const sources = useMemo(() => uniqueSources(displayPool), [displayPool]);

  /** When backend search is active, skip client substring filter (avoid double-filtering). */
  const clientTextQuery = debouncedSearch.trim() ? "" : search.trim();

  const filtered = useMemo(
    () =>
      filterArticles(displayPool, category, clientTextQuery, sourceFilter),
    [displayPool, category, clientTextQuery, sourceFilter],
  );

  /** Same rows as `filtered`, re-ordered by learned category affinity (on-device). */
  const personalizedFiltered = useMemo(() => {
    if (!affinityHydrated) return filtered;
    return sortByPersonalizedAffinity(filtered, categoryAffinity);
  }, [filtered, categoryAffinity, affinityHydrated]);

  /** Stories in the current filtered feed that match followed topics (deterministic). */
  const forYouArticles = useMemo(() => {
    if (followedTopics.length === 0) return [];
    const scored = personalizedFiltered
      .map((article, i) => ({
        article,
        i,
        matches: matchArticleToFollowedTopics(article, followedTopics),
      }))
      .filter((row) => row.matches.length > 0)
      .sort((a, b) => {
        if (b.matches.length !== a.matches.length) {
          return b.matches.length - a.matches.length;
        }
        return a.i - b.i;
      });
    return scored.slice(0, 8).map(({ article, matches }) => ({ article, matches }));
  }, [personalizedFiltered, followedTopics]);

  const categoriesRef = useRef(categories);
  categoriesRef.current = categories;

  /** Search terms → nudge categories that match label tokens (when query changes). */
  useEffect(() => {
    if (!affinityHydrated) return;
    const q = debouncedSearch.trim();
    if (q.length < 2) return;
    const cats = categoriesRef.current;
    if (cats.length === 0) return;
    setCategoryAffinity((prev) => recordSearchInterest(prev, q, cats));
  }, [debouncedSearch, affinityHydrated]);

  useEffect(() => {
    if (!DEBUG) return;
    if (forYouArticles.length === 0) return;
    console.log(
      "[topic_follow] for_you_matches",
      forYouArticles.map((x) => ({
        id: x.article.id,
        link: (x.article.link ?? "").slice(0, 96),
        topics: x.matches,
      })),
    );
  }, [forYouArticles]);

  const savedLinkSet = useMemo(() => {
    return new Set(
      savedBookmarks.map((a) => normalizeArticleLink(a.link || "")),
    );
  }, [savedBookmarks]);

  const isLinkSaved = useCallback(
    (link: string) => savedLinkSet.has(normalizeArticleLink(link || "")),
    [savedLinkSet],
  );

  const handleToggleSave = useCallback((article: Article) => {
    const nowSaved = toggleSavedStory(article);
    if (nowSaved) {
      setCategoryAffinity((prev) => recordArticleSaved(prev, article));
      if (DEBUG) {
        console.log("[personalize] save_boost", {
          key: categoryKeyForArticle(article),
          link: (article.link ?? "").slice(0, 96),
        });
      }
    }
    setSavedRev((n) => n + 1);
  }, []);

  const handleClearAllSaved = useCallback(() => {
    if (
      !window.confirm(
        "Remove all saved stories from this device? This cannot be undone.",
      )
    ) {
      return;
    }
    clearAllSavedStories();
    setSavedRev((n) => n + 1);
  }, []);

  const handleResetFeedPreferences = useCallback(() => {
    if (
      !window.confirm(
        "Reset default feed mode and location to Canada-wide defaults? Your saved bookmarks are kept.",
      )
    ) {
      return;
    }
    resetFeedPreferencesToDefaults();
    const p = loadAppPreferences();
    setFeedMode(p.feedMode);
    setLocationPref(p.location);
  }, []);

  const handleGoToLocalSettings = useCallback(() => {
    setNavTab("local");
    setFeedMode("local");
  }, []);

  const markCategoriesStale = useCallback(() => {
    setCategory("All");
    setSourceFilter("All");
  }, []);

  const handleNav = useCallback(
    (tab: BottomNavTab) => {
      setNavTab(tab);
      if (tab === "home") setFeedMode("general");
      if (tab === "local") setFeedMode("local");
      if (tab === "search") {
        window.setTimeout(() => searchInputRef.current?.focus(), 50);
      }
    },
    [],
  );

  useEffect(() => {
    if (navTab === "search") {
      searchInputRef.current?.focus();
    }
  }, [navTab]);

  const handleOpenArticle = useCallback(
    (article: Article) => {
      markSeen(article.link || "");
      setCategoryAffinity((prev) => recordArticleOpen(prev, article));
      if (DEBUG) {
        console.log("[personalize] open", {
          key: categoryKeyForArticle(article),
          link: (article.link ?? "").slice(0, 96),
        });
      }
      setSelectedArticle(article);
    },
    [markSeen],
  );

  const handleTryAgain = () => {
    setError(null);
    setReloadNonce((n) => n + 1);
  };

  const handleToggleFollowTopic = useCallback((id: FollowTopicId) => {
    setFollowedTopics((prev) => toggleFollowTopic(prev, id));
  }, []);

  const showFeedSurface =
    navTab === "home" || navTab === "local" || navTab === "search";

  const needsLocalSetup = feedMode === "local" && !hasLocalLocation;

  const showFeedList = showFeedSurface && !needsLocalSetup;

  /** Allow showing the previous feed while a refresh is in flight (no full-screen flash). */
  const feedReady =
    seenReady && (!initialLoading || displayPool.length > 0);

  const isFeedRefreshing = initialLoading && displayPool.length > 0;
  const showInitialSkeleton =
    initialLoading && displayPool.length === 0 && showFeedList;

  const noMatches =
    feedReady && !error && displayPool.length > 0 && filtered.length === 0;

  const emptyPool =
    feedReady &&
    !error &&
    !initialLoading &&
    displayPool.length === 0 &&
    !(feedMode === "local" && !hasLocalLocation);

  const exhaustedRemote = !canFetchMore || totalRows === 0;

  /* Infinite scroll */
  useEffect(() => {
    const el = loadSentinelRef.current;
    if (!el || !feedReady || !showFeedList) return;
    const obs = new IntersectionObserver(
      (entries) => {
        const hit = entries[0]?.isIntersecting;
        if (hit && canFetchMore && !loadingMore && !initialLoading) {
          void loadMore();
        }
      },
      { root: null, rootMargin: "240px 0px", threshold: 0 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [
    feedReady,
    showFeedList,
    canFetchMore,
    loadingMore,
    loadMore,
    initialLoading,
  ]);

  const locationLineForModal =
    selectedArticle && feedMode === "local" && hasLocalLocation
      ? buildStoryLocationContext(selectedArticle.region, locationPref)
      : null;

  const desktopTabs: Array<{ id: BottomNavTab; label: string }> = [
    { id: "home", label: "Home" },
    { id: "local", label: "Local" },
    { id: "search", label: "Search" },
    { id: "saved", label: "Saved" },
    { id: "profile", label: "Profile" },
  ];

  return (
    <div className="min-h-screen pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] md:pb-10">
      <FeedTopBar
        search={search}
        onSearchChange={setSearch}
        searchInputRef={searchInputRef}
        personalized={hasPersonalizationSignal(categoryAffinity)}
      />

      <div className="mx-auto hidden w-full max-w-6xl px-5 md:block lg:px-8">
        <nav
          className="mt-3 mb-2 flex items-center gap-2 rounded-2xl border border-[var(--cb-border)] bg-[var(--cb-surface)] p-1.5 shadow-sm"
          aria-label="Primary"
        >
          {desktopTabs.map((tab) => {
            const isActive = navTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => handleNav(tab.id)}
                aria-current={isActive ? "page" : undefined}
                className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${
                  isActive
                    ? "bg-[var(--cb-chip-cat-active-bg)] text-[var(--cb-chip-cat-active-text)]"
                    : "text-[var(--cb-nav-inactive)] hover:bg-[var(--cb-badge-muted-bg)] hover:text-[var(--cb-text)]"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      <main
        className="cb-shell mx-auto mt-2 w-full max-w-6xl rounded-3xl px-4 pt-4 transition-opacity duration-200 ease-out sm:mt-3 sm:px-5 lg:px-8"
        aria-busy={initialLoading || loadingMore}
      >
        {showFeedSurface && (
          <div className="mb-4 space-y-4">
            {feedMode === "local" && hasLocalLocation && (
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-sm font-medium text-[var(--cb-text-secondary)]">
                  Local ·{" "}
                  <span className="text-[var(--cb-text)]">
                    {locationPref.label || locationPref.city}
                  </span>
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setLocationPref(EMPTY_LOCATION);
                    markCategoriesStale();
                  }}
                  className="text-xs font-medium text-[var(--cb-text-tertiary)] underline decoration-[var(--cb-border)] underline-offset-2 hover:text-[var(--cb-text-secondary)]"
                >
                  Change area
                </button>
              </div>
            )}

            {needsLocalSetup && (
              <LocalSetupCard
                onSelectLocation={(loc) => {
                  setLocationPref(loc);
                  markCategoriesStale();
                }}
              />
            )}

            {showFeedList &&
              navTab === "home" &&
              feedMode === "general" &&
              !debouncedSearch.trim() && (
                <DailyBriefCard
                  apiBaseUrl={API_HINT.replace(/\/$/, "")}
                  reloadNonce={reloadNonce}
                  onArticleOpen={handleOpenArticle}
                />
              )}

            {showFeedList &&
              navTab === "home" &&
              !debouncedSearch.trim() &&
              topicsHydrated &&
              followedTopics.length === 0 && (
                <p className="rounded-xl border border-dashed border-[var(--cb-border-subtle)] bg-[var(--cb-surface)]/70 px-3 py-2.5 text-center text-xs leading-relaxed text-[var(--cb-text-tertiary)]">
                  Follow topics like AI, jobs, or housing in Profile to personalize
                  your feed.
                </p>
              )}

            {showFeedList &&
              navTab === "home" &&
              !debouncedSearch.trim() &&
              followedTopics.length > 0 &&
              forYouArticles.length > 0 && (
                <ForYouSection
                  items={forYouArticles}
                  onArticleOpen={handleOpenArticle}
                  isLinkSaved={isLinkSaved}
                  onToggleBookmark={handleToggleSave}
                />
              )}

            {showFeedList && (
              <>
                <CategoryStrip
                  categories={categories}
                  active={category}
                  onChange={setCategory}
                />
                <SourceChips
                  sources={sources}
                  active={sourceFilter}
                  onChange={setSourceFilter}
                />
              </>
            )}
          </div>
        )}

        {navTab === "saved" && (
          <div className="mb-4">
            <h2 className="text-lg font-semibold text-[var(--cb-text)]">Saved</h2>
            <p className="mt-1 text-sm text-[var(--cb-text-tertiary)]">
              Stories you bookmarked on this device.
            </p>
          </div>
        )}

        {navTab === "profile" && (
          <ProfileScreen
            feedMode={feedMode}
            onFeedModeChange={setFeedMode}
            location={locationPref}
            onGoToLocalSettings={handleGoToLocalSettings}
            savedCount={savedBookmarks.length}
            onClearSaved={handleClearAllSaved}
            onResetFeedPreferences={handleResetFeedPreferences}
            apiBaseUrl={API_HINT.replace(/\/$/, "")}
            followedTopics={followedTopics}
            onToggleFollowTopic={handleToggleFollowTopic}
          />
        )}

        {showFeedList && isFeedRefreshing && (
          <div
            className="mb-3 flex items-center justify-center gap-2 rounded-xl border border-[var(--cb-border-subtle)] bg-[var(--cb-surface)]/90 px-3 py-2.5 text-xs font-medium text-[var(--cb-text-secondary)] shadow-sm ring-1 ring-[var(--cb-card-ring)] backdrop-blur-sm"
            role="status"
            aria-live="polite"
          >
            <span
              className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--cb-text-tertiary)] motion-reduce:animate-none"
              aria-hidden
            />
            Updating feed…
          </div>
        )}

        {showInitialSkeleton && (
          <>
            <p className="sr-only" role="status">
              Loading feed
            </p>
            <LoadingSkeleton />
          </>
        )}

        {feedReady && error && displayPool.length === 0 && (
          <FeedEmptyState
            variant="error"
            title="Couldn’t load the feed"
            description={error}
            action={{ label: "Try again", onClick: handleTryAgain }}
          />
        )}

        {feedReady && error && displayPool.length > 0 && (
          <div
            role="alert"
            className="mb-3 rounded-xl border border-[var(--cb-error-border)] bg-[var(--cb-error-bg)] px-4 py-3 text-left"
          >
            <p className="text-sm font-semibold text-[var(--cb-error-title)]">
              Couldn&apos;t refresh
            </p>
            <p className="mt-1 text-sm text-[var(--cb-error-body)]">{error}</p>
            <button
              type="button"
              onClick={handleTryAgain}
              className="mt-3 text-sm font-semibold text-[var(--cb-error-title)] underline decoration-[var(--cb-error-border)] underline-offset-2 transition hover:opacity-90"
            >
              Try again
            </button>
          </div>
        )}

        {feedReady && !error && emptyPool && showFeedList && (
          <FeedEmptyState
            title="No stories yet"
            description="Check back soon — new headlines will appear when the feed updates."
            variant="muted"
          />
        )}

        {noMatches && showFeedList && (
          <FeedEmptyState
            title="No matches"
            description="Try another topic, source, or search."
            variant="muted"
          />
        )}

        {feedReady &&
          showFeedList &&
          personalizedFiltered.length > 0 &&
          (!error || displayPool.length > 0) && (
            <ul className="flex flex-col gap-8 sm:gap-12 pb-4">
              {personalizedFiltered.map((article, i) => (
                <li key={article.id ?? `${article.link}-${i}`}>
                  <FeedCard
                    article={article}
                    index={i}
                    onOpen={handleOpenArticle}
                    bookmarked={isLinkSaved(article.link ?? "")}
                    onToggleBookmark={handleToggleSave}
                  />
                </li>
              ))}
            </ul>
          )}

        {navTab === "saved" && seenReady && !error && (
          <ul className="flex flex-col gap-8 sm:gap-12 pb-4">
            {savedBookmarks.length === 0 ? (
              <FeedEmptyState
                title="Nothing saved yet"
                description="Tap the bookmark on any story to save it here."
                variant="muted"
              />
            ) : (
              savedBookmarks.map((article, i) => (
                <li
                  key={
                    normalizeArticleLink(article.link || "") ||
                    `saved-${article.saved_at}-${i}`
                  }
                >
                  <FeedCard
                    article={article}
                    index={i}
                    onOpen={handleOpenArticle}
                    bookmarked
                    onToggleBookmark={handleToggleSave}
                  />
                </li>
              ))
            )}
          </ul>
        )}

        {showFeedList &&
          feedReady &&
          personalizedFiltered.length > 0 &&
          (!error || displayPool.length > 0) && (
            <div ref={loadSentinelRef} className="h-8 w-full" aria-hidden />
          )}

        {showFeedList && loadingMore && personalizedFiltered.length > 0 && (
          <div className="flex flex-col gap-8 sm:gap-12 pb-6" aria-hidden>
            <FeedCardSkeleton index={0} />
            <FeedCardSkeleton index={1} />
          </div>
        )}

        {showFeedList &&
          feedReady &&
          !loadingMore &&
          !error &&
          exhaustedRemote &&
          personalizedFiltered.length > 0 && (
            <p className="pb-8 text-center text-xs text-[var(--cb-text-muted)]">
              You&apos;re up to date with loaded stories.
            </p>
          )}
      </main>

      <ArticleDetailModal
        article={selectedArticle}
        locationLine={locationLineForModal}
        onClose={() => setSelectedArticle(null)}
        bookmarked={
          selectedArticle
            ? isLinkSaved(selectedArticle.link ?? "")
            : false
        }
        onToggleBookmark={
          selectedArticle
            ? () => handleToggleSave(selectedArticle)
            : undefined
        }
      />

      <div className="md:hidden">
        <BottomNav active={navTab} onChange={handleNav} />
      </div>
    </div>
  );
}
