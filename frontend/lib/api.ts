import type { Article } from "./types";

const DEFAULT_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Must match backend PAGE_SIZE (max rows per page). */
export const DEFAULT_PAGE_SIZE = 5;

export type FetchNewsPageResult = {
  articles: Article[];
  /** Present when backend sends ranked spotlight rows (same shape as feed items). */
  topStories?: Article[];
  /** From `X-Total-Count` when present; else articles.length. */
  totalCount: number;
  page: number;
  pageSize: number;
};

function parseNewsPayload(data: unknown): { articles: Article[]; topStories?: Article[] } {
  if (Array.isArray(data)) {
    return { articles: data as Article[] };
  }
  if (
    data !== null &&
    typeof data === "object" &&
    Array.isArray((data as { articles?: unknown }).articles)
  ) {
    const o = data as { articles: Article[]; top_stories?: unknown };
    const topStories = Array.isArray(o.top_stories)
      ? (o.top_stories as Article[])
      : undefined;
    return { articles: o.articles, topStories };
  }
  throw new Error("Invalid response: expected an array or { articles: [...] }");
}

/**
 * GET /news?page=&page_size=
 *
 * Normal navigation: omit `refresh` (default false). The backend returns one page of
 * stories and runs LLM summarization only for that page’s rows.
 *
 * `refresh: true` re-fetches RSS and re-ingests — use only for explicit “refresh feeds”.
 *
 * Response: legacy JSON array or `{ articles, top_stories? }`. Total rows: `X-Total-Count`.
 */
export async function fetchNewsPage(options: {
  page?: number;
  pageSize?: number;
  /**
   * 0-based global index of the current story in feed order (rank_score DESC).
   * Lets the backend prewarm the next stories for one-story-at-a-time UIs.
   * Omit to default to the first story on this page: (page-1)*page_size.
   */
  cursor?: number;
  /** When true, adds refresh=true (RSS ingest). Omit for normal pagination. */
  refresh?: boolean;
  /** general = Canada-wide; local = city-first + regional filtering */
  mode?: "general" | "local";
  city?: string | null;
  province?: string | null;
  /** From Canada locations dataset (e.g. ON). */
  provinceCode?: string | null;
  /** Stable slug (e.g. ottawa-on). */
  locationSlug?: string | null;
  /** Backend search across title, summary, region, source, categories (sent as `q`). */
  search?: string | null;
}): Promise<FetchNewsPageResult> {
  const page = options.page ?? 1;
  const pageSize = options.pageSize ?? DEFAULT_PAGE_SIZE;
  const refresh = options.refresh ?? false;
  const cursor = options.cursor;
  const city = options.city;
  const province = options.province;
  const provinceCode = options.provinceCode;
  const locationSlug = options.locationSlug;
  const mode = options.mode ?? "general";
  const search = (options.search ?? "").trim();

  const base = DEFAULT_BASE.replace(/\/$/, "");
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  params.set("mode", mode);
  if (search) params.set("q", search);
  if (cursor !== undefined && Number.isFinite(cursor)) {
    params.set("cursor", String(Math.max(0, Math.floor(cursor))));
  }
  if (mode === "local") {
    if (city) params.set("city", city);
    if (province) params.set("province", province);
    if (provinceCode) params.set("province_code", provinceCode);
    if (locationSlug) params.set("slug", locationSlug);
  }
  if (refresh) params.set("refresh", "true");
  // Ensure browsers/CDNs never reuse a cached ingest response for explicit refresh.
  if (refresh) params.set("_t", String(Date.now()));

  const url = `${base}/news?${params.toString()}`;
  const res = await fetch(url, {
    cache: "no-store",
    headers: refresh
      ? { "Cache-Control": "no-cache", Pragma: "no-cache" }
      : undefined,
  });

  if (!res.ok) {
    throw new Error(`Failed to load news (${res.status})`);
  }

  const data = await res.json();
  const { articles, topStories } = parseNewsPayload(data);

  const headerTotal =
    res.headers.get("X-Total-Count") ?? res.headers.get("x-total-count");
  const parsed = headerTotal != null ? parseInt(headerTotal, 10) : NaN;
  const totalCount = Number.isFinite(parsed) ? parsed : articles.length;

  return {
    articles,
    topStories,
    totalCount,
    page,
    pageSize,
  };
}

/** GET /daily-brief — top 5 general feed stories (deduped), cached per UTC day on server. */
export type DailyBriefStory = {
  id?: number;
  title: string;
  summary: string;
  source: string;
  published?: string;
  category?: string;
  region?: string;
  image_url?: string;
  /** Video URL if article has embedded video (YouTube, Vimeo, etc.) */
  video_url?: string;
  link: string;
};

export type DailyBriefResponse = {
  brief_date: string;
  /** ISO8601 when this payload was built (server UTC). */
  brief_generated_at?: string;
  /** Latest `last_updated_at` among selected rows, if any. */
  brief_source_timestamp?: string | null;
  brief_max_news_id?: number;
  estimated_read_time_seconds: number;
  estimated_read_time_label: string;
  generation_source: string;
  stories: DailyBriefStory[];
};

export async function fetchDailyBrief(
  apiBase?: string,
): Promise<DailyBriefResponse> {
  const base = (apiBase ?? DEFAULT_BASE).replace(/\/$/, "");
  const res = await fetch(`${base}/daily-brief`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to load Daily Brief (${res.status})`);
  }
  return res.json() as Promise<DailyBriefResponse>;
}
