import type { Article } from "./types";

const DEFAULT_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Must match backend PAGE_SIZE (max rows per page). */
export const DEFAULT_PAGE_SIZE = 10;

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
 * Load one page of news. Backend may return a JSON array (legacy) or
 * `{ articles, top_stories? }`. Total rows are in `X-Total-Count`.
 */
export async function fetchNewsPage(options: {
  page?: number;
  pageSize?: number;
  refresh?: boolean;
}): Promise<FetchNewsPageResult> {
  const page = options.page ?? 1;
  const pageSize = options.pageSize ?? DEFAULT_PAGE_SIZE;
  const refresh = options.refresh ?? false;

  const base = DEFAULT_BASE.replace(/\/$/, "");
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  if (refresh) params.set("refresh", "true");

  const url = `${base}/news?${params.toString()}`;
  const res = await fetch(url, {
    cache: "no-store",
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
