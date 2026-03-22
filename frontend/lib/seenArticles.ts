/**
 * Persist which article URLs the user has already read (main feed).
 * Key: article.link, normalized for stable matching.
 */

export const SEEN_ARTICLES_KEY = "seen_articles";

export function normalizeArticleLink(link: string): string {
  let s = (link || "").trim().toLowerCase();
  while (s.endsWith("/") && s.length > 1) {
    s = s.slice(0, -1);
  }
  return s;
}

export function loadSeenLinks(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(SEEN_ARTICLES_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as unknown;
    if (!Array.isArray(arr)) return new Set();
    return new Set(arr.filter((x): x is string => typeof x === "string").map(normalizeArticleLink));
  } catch {
    return new Set();
  }
}

export function saveSeenLinks(seen: Set<string>): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SEEN_ARTICLES_KEY, JSON.stringify([...seen]));
  } catch {
    /* ignore quota */
  }
}

export function clearSeenLinks(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(SEEN_ARTICLES_KEY);
  } catch {
    /* ignore */
  }
}
