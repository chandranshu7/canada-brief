import type { Article } from "@/lib/types";
import { filterArticles } from "@/lib/filterArticles";
import { normalizeArticleLink } from "@/lib/seenArticles";

export type RebuildStoryQueueParams = {
  pool: Article[];
  category: string;
  search: string;
  seen: Set<string>;
  /**
   * When true: browse full filtered list (including seen) via `seenBrowseIndex`.
   * When false: one-story flow over unseen items via `viewHistory` + `sessionIndex`.
   */
  showSeen: boolean;
  /** Normalized link key to keep on screen when still valid after rebuild. */
  currentLinkKey: string | null;
};

export type RebuildStoryQueueResult = {
  viewHistory: Article[];
  sessionIndex: number;
  seenBrowseIndex: number;
  /** For debug logs */
  reason: string;
};

/**
 * Rebuilds session buffers after pool/seen/filter/toggle changes.
 * - showSeen: positions `seenBrowseIndex` on the current story when possible.
 * - !showSeen: builds `viewHistory` as a prefix of the unseen queue so Next/Previous work.
 */
export function rebuildStoryQueue(
  p: RebuildStoryQueueParams,
): RebuildStoryQueueResult {
  const filtered = filterArticles(p.pool, p.category, p.search, "All");
  const isSeen = (a: Article) =>
    p.seen.has(normalizeArticleLink(a.link || ""));

  if (p.showSeen) {
    let idx = 0;
    if (p.currentLinkKey && filtered.length > 0) {
      const i = filtered.findIndex(
        (a) => normalizeArticleLink(a.link || "") === p.currentLinkKey,
      );
      if (i >= 0) idx = i;
    }
    if (filtered.length === 0) {
      return {
        viewHistory: [],
        sessionIndex: 0,
        seenBrowseIndex: 0,
        reason: "show_seen_empty_filtered",
      };
    }
    return {
      viewHistory: [],
      sessionIndex: 0,
      seenBrowseIndex: Math.min(idx, filtered.length - 1),
      reason: "show_seen_browse",
    };
  }

  const unseen = filtered.filter((a) => !isSeen(a));

  if (unseen.length === 0) {
    return {
      viewHistory: [],
      sessionIndex: 0,
      seenBrowseIndex: 0,
      reason: "no_unseen",
    };
  }

  if (p.currentLinkKey) {
    const pos = unseen.findIndex(
      (a) => normalizeArticleLink(a.link || "") === p.currentLinkKey,
    );
    if (pos >= 0) {
      const slice = unseen.slice(0, pos + 1);
      return {
        viewHistory: slice,
        sessionIndex: slice.length - 1,
        seenBrowseIndex: 0,
        reason: "preserve_unseen_path",
      };
    }
  }

  return {
    viewHistory: [unseen[0]],
    sessionIndex: 0,
    seenBrowseIndex: 0,
    reason: "seed_first_unseen",
  };
}
