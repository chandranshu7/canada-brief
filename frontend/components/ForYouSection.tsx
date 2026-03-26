"use client";

import type { Article } from "@/lib/types";
import type { FollowTopicId } from "@/lib/followedTopics";
import { topicLabel } from "@/lib/followedTopics";
import { FeedCard } from "./FeedCard";

export type ForYouArticle = {
  article: Article;
  /** Matched followed topic ids (subset). */
  matches: FollowTopicId[];
};

type ForYouSectionProps = {
  items: ForYouArticle[];
  onArticleOpen: (article: Article) => void;
  isLinkSaved: (link: string) => boolean;
  onToggleBookmark: (article: Article) => void;
};

function matchBadgeLabel(matches: FollowTopicId[]): string {
  if (matches.length === 0) return "";
  const labels = matches.map((id) => topicLabel(id));
  if (labels.length <= 2) return `Matches ${labels.join(" · ")}`;
  return `Matches ${labels.slice(0, 2).join(" · ")} +${labels.length - 2}`;
}

/**
 * Home-only strip: stories from the current filtered feed that match followed topics.
 */
export function ForYouSection({
  items,
  onArticleOpen,
  isLinkSaved,
  onToggleBookmark,
}: ForYouSectionProps) {
  if (items.length === 0) return null;

  return (
    <section
      className="rounded-2xl border border-[var(--cb-border-subtle)] bg-[var(--cb-surface)]/90 p-3 shadow-sm ring-1 ring-[var(--cb-card-ring)] backdrop-blur-sm"
      aria-labelledby="for-you-heading"
    >
      <div className="mb-3 flex flex-col gap-0.5 px-0.5">
        <h2
          id="for-you-heading"
          className="text-sm font-semibold tracking-tight text-[var(--cb-text)]"
        >
          For you
        </h2>
        <p className="text-[11px] text-[var(--cb-text-tertiary)]">
          Based on topics you follow
        </p>
      </div>
      <ul className="flex flex-col gap-8 sm:gap-12">
        {items.map(({ article, matches }, i) => (
          <li key={article.id ?? `${article.link}-for-you-${i}`}>
            <FeedCard
              article={article}
              index={i}
              onOpen={onArticleOpen}
              bookmarked={isLinkSaved(article.link ?? "")}
              onToggleBookmark={onToggleBookmark}
              followTopicBadge={matchBadgeLabel(matches)}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
