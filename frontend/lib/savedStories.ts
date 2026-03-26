/**
 * Bookmarked stories (v1) — persisted in localStorage only.
 * Primary key: normalized article link (see normalizeArticleLink).
 */

import type { Article } from "./types";
import { normalizeArticleLink } from "./seenArticles";

export const SAVED_STORIES_STORAGE_KEY = "cb_saved_stories_v1";

export type SavedArticle = Article & { saved_at: string };

type StoredRecord = {
  id?: number;
  title: string;
  summary: string;
  source: string;
  published?: string;
  region?: string;
  image_url?: string;
  link: string;
  category?: string;
  topic_category?: string;
  sources?: string[];
  related_links?: string[];
  cluster_id?: number;
  saved_at: string;
};

function keyForLink(link: string): string {
  return normalizeArticleLink(link || "");
}

function readRaw(): StoredRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(SAVED_STORIES_STORAGE_KEY);
    if (!raw) return [];
    const data = JSON.parse(raw) as unknown;
    if (!Array.isArray(data)) return [];
    return data.filter((x): x is StoredRecord => isRecord(x));
  } catch {
    return [];
  }
}

function isRecord(x: unknown): x is StoredRecord {
  if (x === null || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  return (
    typeof o.link === "string" &&
    typeof o.title === "string" &&
    typeof o.saved_at === "string"
  );
}

function writeRaw(records: StoredRecord[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SAVED_STORIES_STORAGE_KEY, JSON.stringify(records));
  } catch {
    /* quota / private mode */
  }
}

function toArticle(r: StoredRecord): SavedArticle {
  return {
    id: r.id,
    title: r.title,
    summary: r.summary ?? "",
    source: r.source ?? "",
    link: r.link,
    published: r.published,
    region: r.region,
    image_url: r.image_url,
    category: r.category,
    topic_category: r.topic_category,
    cluster_id: r.cluster_id,
    sources: r.sources,
    related_links: r.related_links,
    saved_at: r.saved_at,
  };
}

function fromArticle(a: Article, savedAt: string): StoredRecord {
  return {
    id: a.id,
    title: a.title ?? "",
    summary: a.summary ?? "",
    source: a.source ?? "",
    published: a.published,
    region: a.region,
    image_url: a.image_url,
    link: a.link ?? "",
    category: a.category,
    topic_category: a.topic_category,
    cluster_id: a.cluster_id,
    sources: a.sources,
    related_links: a.related_links,
    saved_at: savedAt,
  };
}

/** All saved stories, newest bookmark first. */
export function getSavedStories(): SavedArticle[] {
  const rows = readRaw();
  rows.sort(
    (a, b) =>
      new Date(b.saved_at).getTime() - new Date(a.saved_at).getTime(),
  );
  return rows.map(toArticle);
}

/** True if this link is already bookmarked (normalized). */
export function isStorySaved(link: string): boolean {
  const k = keyForLink(link);
  if (!k) return false;
  return readRaw().some((r) => keyForLink(r.link) === k);
}

/** Add or replace bookmark for this link (deduped by link). */
export function saveStory(article: Article): void {
  const link = (article.link || "").trim();
  if (!link) return;
  const k = keyForLink(link);
  const next = readRaw().filter((r) => keyForLink(r.link) !== k);
  next.push(fromArticle(article, new Date().toISOString()));
  writeRaw(next);
}

export function unsaveStory(link: string): void {
  const k = keyForLink(link);
  if (!k) return;
  writeRaw(readRaw().filter((r) => keyForLink(r.link) !== k));
}

/** Toggle save state; returns true if now saved. */
export function toggleSavedStory(article: Article): boolean {
  const link = article.link || "";
  if (isStorySaved(link)) {
    unsaveStory(link);
    return false;
  }
  saveStory(article);
  return true;
}

/** Remove every bookmark (localStorage). */
export function clearAllSavedStories(): void {
  writeRaw([]);
}

export function getSavedStoriesCount(): number {
  return readRaw().length;
}
