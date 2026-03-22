import type { Article } from "./types";

/** Unique outlets for a clustered row (falls back to single `source`). */
export function articleSourceList(a: Article): string[] {
  if (a.sources && a.sources.length > 0) {
    return a.sources;
  }
  const s = (a.source || "").trim();
  return s ? [s] : [];
}

export function articleSourceCount(a: Article): number {
  return articleSourceList(a).length;
}

export function isMultiSourceCluster(a: Article): boolean {
  return articleSourceCount(a) > 1;
}
