import type { Article } from "./types";
import { normalizeArticleLink } from "./seenArticles";

/**
 * Match backend `normalize_title_for_dedup` (fetch_news.py) for stable fallback keys.
 */
export function normalizeTitleForDedup(title: string): string {
  let t = (title || "").trim().toLowerCase();
  t = t.replace(/[\u2013\u2014]/g, " ").replace(/-/g, " ");
  t = t.replace(/[^a-z0-9\s]/gi, "");
  t = t.replace(/\s+/g, " ").trim();
  return t;
}

export function feedArticleDedupeKey(a: Article): string {
  const link = (a.link || "").trim();
  if (link) {
    return `l:${normalizeArticleLink(link)}`;
  }
  const src = (a.source || "").trim().toLowerCase();
  const title = normalizeTitleForDedup(a.title || "");
  const pub = (a.published || "").trim().toLowerCase();
  return `s:${src}|${title}|${pub}`;
}

export function dedupeFeedArticlesStable<T extends Article>(items: T[]): {
  items: T[];
  removed: number;
  removedKeys: string[];
} {
  const seen = new Set<string>();
  const out: T[] = [];
  const removedKeys: string[] = [];
  for (const item of items) {
    const k = feedArticleDedupeKey(item);
    if (seen.has(k)) {
      if (removedKeys.length < 24) removedKeys.push(k);
      continue;
    }
    seen.add(k);
    out.push(item);
  }
  return {
    items: out,
    removed: items.length - out.length,
    removedKeys,
  };
}
