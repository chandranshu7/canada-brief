/**
 * Client-side feed personalization (V1): learn from opens, saves, and search — no account.
 * Boosts stories whose `topic_category` / `category` matches weighted affinity keys.
 */

import type { Article } from "./types";

export const PERSONALIZATION_STORAGE_KEY = "cb_personalization_v1";

const VERSION = 1 as const;

/** Points added per signal (tuned so saves matter more than clicks). */
export const WEIGHT_OPEN = 2;
export const WEIGHT_SAVE = 8;
export const WEIGHT_SEARCH_HINT = 1.5;

const MAX_WEIGHT_PER_CATEGORY = 200;

export type PersonalizationState = {
  v: typeof VERSION;
  /** Normalized category label -> cumulative weight */
  categoryWeights: Record<string, number>;
};

export function normalizeCategoryKey(
  s: string | null | undefined,
): string | null {
  const t = (s || "").trim().toLowerCase().replace(/\s+/g, " ");
  return t || null;
}

export function categoryKeyForArticle(a: Article): string | null {
  return normalizeCategoryKey(a.topic_category ?? a.category);
}

export function loadPersonalization(): Record<string, number> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(PERSONALIZATION_STORAGE_KEY);
    if (!raw) return {};
    const data = JSON.parse(raw) as unknown;
    if (!data || typeof data !== "object") return {};
    const o = data as PersonalizationState;
    if (o.v !== VERSION || !o.categoryWeights || typeof o.categoryWeights !== "object") {
      return {};
    }
    return { ...o.categoryWeights };
  } catch {
    return {};
  }
}

export function savePersonalization(weights: Record<string, number>): void {
  if (typeof window === "undefined") return;
  try {
    const state: PersonalizationState = {
      v: VERSION,
      categoryWeights: { ...weights },
    };
    window.localStorage.setItem(
      PERSONALIZATION_STORAGE_KEY,
      JSON.stringify(state),
    );
  } catch {
    /* quota */
  }
}

function bump(
  weights: Record<string, number>,
  key: string | null,
  delta: number,
): Record<string, number> {
  if (!key) return weights;
  const next = { ...weights };
  const v = Math.min(
    MAX_WEIGHT_PER_CATEGORY,
    Math.max(0, (next[key] ?? 0) + delta),
  );
  next[key] = v;
  return next;
}

/** User opened a story (modal). */
export function recordArticleOpen(
  weights: Record<string, number>,
  article: Article,
): Record<string, number> {
  return bump(weights, categoryKeyForArticle(article), WEIGHT_OPEN);
}

/** User saved a story (not unsave). */
export function recordArticleSaved(
  weights: Record<string, number>,
  article: Article,
): Record<string, number> {
  return bump(weights, categoryKeyForArticle(article), WEIGHT_SAVE);
}

/**
 * User ran a search: lightly boost categories whose labels overlap query tokens
 * (e.g. search "housing" nudges Housing).
 */
export function recordSearchInterest(
  weights: Record<string, number>,
  query: string,
  categoryLabels: readonly string[],
): Record<string, number> {
  const ql = query.trim().toLowerCase();
  if (ql.length < 2 || categoryLabels.length === 0) return weights;
  const tokens = ql.split(/\s+/).filter((t) => t.length >= 2);
  if (tokens.length === 0) return weights;

  let next = weights;
  for (const cat of categoryLabels) {
    const k = normalizeCategoryKey(cat);
    if (!k) continue;
    const cl = k;
    for (const t of tokens) {
      if (t.length < 3) continue;
      if (cl.includes(t) || (cl.length >= 3 && t.includes(cl))) {
        next = bump(next, k, WEIGHT_SEARCH_HINT);
        break;
      }
    }
  }
  return next;
}

/** Affinity score used for ordering (0 if unknown category). */
export function affinityForArticle(
  article: Article,
  weights: Record<string, number>,
): number {
  const k = categoryKeyForArticle(article);
  if (!k) return 0;
  return weights[k] ?? 0;
}

/**
 * Stable re-rank: higher affinity first, then original feed order.
 */
export function sortByPersonalizedAffinity(
  articles: Article[],
  weights: Record<string, number>,
): Article[] {
  if (articles.length <= 1) return articles;
  const indexed = articles.map((article, i) => ({ article, i }));
  indexed.sort((a, b) => {
    const wa = affinityForArticle(a.article, weights);
    const wb = affinityForArticle(b.article, weights);
    if (wb !== wa) return wb - wa;
    return a.i - b.i;
  });
  return indexed.map((x) => x.article);
}

export function hasPersonalizationSignal(weights: Record<string, number>): boolean {
  return Object.values(weights).some((v) => v > 0);
}
