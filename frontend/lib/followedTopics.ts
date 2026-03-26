/**
 * Topic follow (V1): user-selected interests, stored locally — separate from backend category.
 */

import type { Article } from "./types";

export const FOLLOWED_TOPICS_STORAGE_KEY = "cb_followed_topics_v1";

/** Ordered topic ids supported in V1. */
export const FOLLOW_TOPIC_IDS = [
  "ai",
  "immigration",
  "jobs",
  "housing",
  "politics",
  "business",
  "technology",
] as const;

export type FollowTopicId = (typeof FOLLOW_TOPIC_IDS)[number];

export type TopicDefinition = {
  id: FollowTopicId;
  /** Short label for UI (e.g. "AI"). */
  label: string;
  /** Lowercase keywords / phrases; deterministic substring + word-boundary checks. */
  keywords: readonly string[];
};

/** Keyword sets per topic. */
export const TOPIC_DEFINITIONS: readonly TopicDefinition[] = [
  {
    id: "ai",
    label: "AI",
    keywords: [
      "ai",
      "artificial intelligence",
      "machine learning",
      "chatbot",
      "openai",
      "neural",
      "generative",
      "llm",
      "large language model",
    ],
  },
  {
    id: "immigration",
    label: "Immigration",
    keywords: [
      "immigration",
      "visa",
      "permanent resident",
      "pr card",
      "work permit",
      "study permit",
      "refugee",
      "asylum",
      "citizenship",
      "border",
      "international student",
    ],
  },
  {
    id: "jobs",
    label: "Jobs",
    keywords: [
      "jobs",
      "hiring",
      "layoffs",
      "employment",
      "labour",
      "labor",
      "unemployment",
      "workforce",
      "wages",
      "wage",
    ],
  },
  {
    id: "housing",
    label: "Housing",
    keywords: [
      "housing",
      "rent",
      "mortgage",
      "real estate",
      "tenant",
      "landlord",
      "affordability",
    ],
  },
  {
    id: "politics",
    label: "Politics",
    keywords: [
      "politics",
      "parliament",
      "election",
      "premier",
      "minister",
      "federal",
      "provincial",
      "party",
      "legislature",
      "mpp",
      "mlas",
      "member of parliament",
    ],
  },
  {
    id: "business",
    label: "Business",
    keywords: [
      "business",
      "economy",
      "stocks",
      "stock market",
      "earnings",
      "corporate",
      "ceo",
      "company",
    ],
  },
  {
    id: "technology",
    label: "Technology",
    keywords: [
      "technology",
      "tech",
      "software",
      "startup",
      "internet",
      "cyber",
      "digital",
    ],
  },
] as const;

const TOPIC_BY_ID: Record<FollowTopicId, TopicDefinition> = Object.fromEntries(
  TOPIC_DEFINITIONS.map((t) => [t.id, t]),
) as Record<FollowTopicId, TopicDefinition>;

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function articleHaystack(article: Article): string {
  const parts = [
    article.title,
    article.summary,
    article.topic_category ?? "",
    article.category ?? "",
  ];
  return parts.join(" \n ").toLowerCase();
}

/**
 * True if `keyword` appears in the haystack with word boundaries (avoid "ai" in "said").
 */
function keywordMatchesKeyword(haystack: string, keyword: string): boolean {
  const kw = keyword.trim().toLowerCase();
  if (!kw) return false;
  if (kw.includes(" ")) {
    const pattern = kw
      .split(/\s+/)
      .map((p) => escapeRegex(p))
      .join("\\s+");
    return new RegExp(`(?:^|[^a-z0-9])${pattern}(?:[^a-z0-9]|$)`, "i").test(
      haystack,
    );
  }
  return new RegExp(`(?:^|[^a-z0-9])${escapeRegex(kw)}(?:[^a-z0-9]|$)`, "i").test(
    haystack,
  );
}

/**
 * Returns topic ids that match this article (followed subset only).
 */
export function matchArticleToFollowedTopics(
  article: Article,
  followedIds: readonly FollowTopicId[],
): FollowTopicId[] {
  if (followedIds.length === 0) return [];
  const hay = articleHaystack(article);
  const out: FollowTopicId[] = [];
  for (const id of followedIds) {
    const def = TOPIC_BY_ID[id];
    if (!def) continue;
    let hit = false;
    for (const kw of def.keywords) {
      if (keywordMatchesKeyword(hay, kw)) {
        hit = true;
        break;
      }
    }
    if (hit) out.push(id);
  }
  return out;
}

export function topicLabel(id: FollowTopicId): string {
  return TOPIC_BY_ID[id]?.label ?? id;
}

export function loadFollowedTopics(): FollowTopicId[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(FOLLOWED_TOPICS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    const set = new Set(FOLLOW_TOPIC_IDS);
    const out: FollowTopicId[] = [];
    for (const x of parsed) {
      if (typeof x === "string" && set.has(x as FollowTopicId)) {
        out.push(x as FollowTopicId);
      }
    }
    return out;
  } catch {
    return [];
  }
}

export function saveFollowedTopics(ids: readonly FollowTopicId[]): void {
  if (typeof window === "undefined") return;
  const seen = new Set<FollowTopicId>();
  const ordered: FollowTopicId[] = [];
  for (const id of FOLLOW_TOPIC_IDS) {
    if (ids.includes(id) && !seen.has(id)) {
      seen.add(id);
      ordered.push(id);
    }
  }
  window.localStorage.setItem(
    FOLLOWED_TOPICS_STORAGE_KEY,
    JSON.stringify(ordered),
  );
}

export function toggleFollowTopic(
  current: readonly FollowTopicId[],
  id: FollowTopicId,
): FollowTopicId[] {
  if (current.includes(id)) {
    return current.filter((x) => x !== id);
  }
  return [...current, id];
}
