/**
 * Persist "saved for later" article links (normalized).
 */

import { normalizeArticleLink } from "./seenArticles";

export const SAVED_ARTICLES_KEY = "saved_articles";

export function loadSavedLinks(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(SAVED_ARTICLES_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as unknown;
    if (!Array.isArray(arr)) return new Set();
    return new Set(
      arr.filter((x): x is string => typeof x === "string").map(normalizeArticleLink),
    );
  } catch {
    return new Set();
  }
}

export function saveSavedLinks(saved: Set<string>): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SAVED_ARTICLES_KEY, JSON.stringify([...saved]));
  } catch {
    /* ignore quota */
  }
}

/** Toggle save by link; returns true if now saved, false if removed. */
export function toggleSavedLink(link: string): boolean {
  const key = normalizeArticleLink(link);
  const prev = loadSavedLinks();
  const next = new Set(prev);
  if (next.has(key)) {
    next.delete(key);
    saveSavedLinks(next);
    return false;
  }
  next.add(key);
  saveSavedLinks(next);
  return true;
}

export function isLinkSaved(link: string, saved: Set<string>): boolean {
  return saved.has(normalizeArticleLink(link));
}
