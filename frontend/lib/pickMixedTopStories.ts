import type { Article } from "./types";

/**
 * Pick up to `n` stories, preferring distinct sources first (feed order preserved),
 * then filling from the remainder so Top Stories mixes outlets when possible.
 */
export function pickMixedTopStories(items: Article[], n: number): Article[] {
  if (items.length <= n) return [...items];

  const picked: Article[] = [];
  const seenLink = new Set<string>();
  const usedSource = new Set<string>();

  for (const a of items) {
    if (picked.length >= n) break;
    const link = (a.link || "").trim();
    const src = (a.source || "Unknown").trim();
    if (!link || seenLink.has(link)) continue;
    if (usedSource.has(src)) continue;
    usedSource.add(src);
    seenLink.add(link);
    picked.push(a);
  }

  for (const a of items) {
    if (picked.length >= n) break;
    const link = (a.link || "").trim();
    if (!link || seenLink.has(link)) continue;
    seenLink.add(link);
    picked.push(a);
  }

  return picked;
}
