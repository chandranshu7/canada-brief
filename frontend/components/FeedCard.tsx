"use client";

import { useState } from "react";
import type { Article } from "@/lib/types";
import {
  articleSourceCount,
  articleSourceList,
  isMultiSourceCluster,
} from "@/lib/clusterUi";
import { formatPublishedDisplay } from "@/lib/formatPublished";
import { getHeroImageDisplay, getVideoThumbnailUrl } from "@/lib/heroImage";
import { IconBookmark, IconBookmarkFilled } from "./icons";
import { categoryBadgeClass } from "./categoryStyles";
import { sourceBadgeClass } from "./sourceStyles";

function hashString(input: string): number {
  let h = 0;
  for (let i = 0; i < input.length; i += 1) {
    h = (h * 31 + input.charCodeAt(i)) >>> 0;
  }
  return h;
}

function firstDisplayChar(text: string): string {
  const m = (text || "").match(/[A-Za-z0-9]/);
  return (m?.[0] || "N").toUpperCase();
}

type FeedCardProps = {
  article: Article;
  index?: number;
  onOpen?: (article: Article) => void;
  bookmarked?: boolean;
  onToggleBookmark?: (article: Article) => void;
  followTopicBadge?: string;
};

export function FeedCard({
  article,
  index = 0,
  onOpen,
  bookmarked = false,
  onToggleBookmark,
  followTopicBadge,
}: FeedCardProps) {
  const img = (article.image_url ?? "").trim();
  const [imgBroken, setImgBroken] = useState(false);
  const sources = articleSourceList(article);
  const multi = isMultiSourceCluster(article);
  const nSources = articleSourceCount(article);
  const published = formatPublishedDisplay(article.published);
  const delayMs = Math.min(index * 35, 280);
  const primarySource = sources[0] ?? (article.source || "").trim();
  const { src: imageSrc } = getHeroImageDisplay(img);
  
  // Fallback to video thumbnail if primary image is missing/broken
  const videoThumbnailUrl = (article.video_url ?? "").trim() ? getVideoThumbnailUrl(article.video_url ?? "") : "";
  const finalImageSrc = imageSrc || videoThumbnailUrl;
  
  const placeholderSeed = `${article.title || ""}|${article.link || ""}|${primarySource}`;
  const hue = hashString(placeholderSeed) % 360;
  const placeholderLetter = firstDisplayChar(article.title || primarySource || "News");
  const placeholderBg = `linear-gradient(135deg, hsl(${hue} 45% 34%), hsl(${(hue + 48) % 360} 52% 18%))`;
  const cat = article.topic_category ?? article.category;

  return (
    <article
      className="animate-fade-in-up opacity-0 motion-reduce:animate-none motion-reduce:opacity-100"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      <div className="relative cb-glow rounded-3xl">
        <button
          type="button"
          onClick={() => onOpen?.(article)}
          className="group block w-full overflow-hidden rounded-3xl border border-[var(--cb-article-card-border)] bg-[var(--cb-article-card-bg)] text-left shadow-[var(--cb-article-card-shadow)] transition-all duration-400 ease-[cubic-bezier(0.16,1,0.3,1)] hover:-translate-y-1.5 hover:border-[var(--cb-article-card-hover-border)] hover:shadow-[var(--cb-article-card-hover-shadow)]"
        >
          {/* Edge-to-edge Hero Image */}
          <div className="relative h-64 w-full overflow-hidden bg-[var(--cb-thumb-bg)] sm:h-80">
            {finalImageSrc && !imgBroken ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={finalImageSrc}
                alt=""
                className="h-full w-full object-cover transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:scale-105 motion-reduce:transition-none motion-reduce:group-hover:scale-100"
                onError={() => setImgBroken(true)}
              />
            ) : (
              <div
                className="flex h-full w-full items-center justify-center"
                style={{ backgroundImage: placeholderBg }}
              >
                <span className="select-none text-6xl font-display font-semibold uppercase tracking-wide text-[var(--cb-thumb-label)] opacity-40">
                  {placeholderLetter}
                </span>
              </div>
            )}
            
            {/* Subtle Gradient Overlay */}
            <div className="absolute inset-0 bg-gradient-to-t from-[var(--cb-article-card-bg)] via-transparent to-transparent opacity-90 transition-opacity duration-300 group-hover:opacity-100" />
            
            {/* Categories and Badges Inside Image */}
            <div className="absolute bottom-4 left-4 right-4 flex flex-wrap items-center gap-2">
              {multi ? (
                <span className="rounded-full bg-black/60 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[var(--cb-accent)] backdrop-blur-md">
                  {nSources} sources
                </span>
              ) : primarySource ? (
                <span className="rounded-full bg-black/60 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[var(--cb-accent)] backdrop-blur-md">
                  {primarySource}
                </span>
              ) : null}

              {cat && (
                <span className={`inline-flex rounded-full bg-black/60 px-3 py-1 text-[10px] font-bold uppercase tracking-widest backdrop-blur-md ring-1 ${categoryBadgeClass(cat)}`}>
                  {cat}
                </span>
              )}

              {followTopicBadge ? (
                <span className="rounded-full bg-[var(--cb-accent)]/20 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[var(--cb-accent)] backdrop-blur-md ring-1 ring-[var(--cb-accent)]/50">
                  {followTopicBadge}
                </span>
              ) : null}
            </div>
          </div>

          <div className="px-5 pb-6 pt-4 sm:px-7 sm:pb-8">
            <h3 className="font-display line-clamp-3 text-2xl font-bold leading-[1.15] tracking-tight text-[var(--cb-title)] transition-colors duration-200 ease-out group-hover:text-[var(--cb-title-hover)] sm:text-[28px]">
              {article.title}
            </h3>

            {/* AI Summary Section - Premium Glass Tray */}
            <div className="mt-5 rounded-2xl border border-[var(--cb-ai-tray-border)] bg-[var(--cb-ai-tray-bg)] p-4 shadow-inner backdrop-blur-xl transition-colors duration-300 group-hover:border-[var(--cb-accent-soft)]">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--cb-ai-label)] opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--cb-ai-label)]"></span>
                </span>
                <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--cb-ai-label)]">
                  AI Summary
                </p>
              </div>
              {article.summary ? (
                <p className="mt-2.5 line-clamp-3 text-[14px] font-normal leading-relaxed text-[var(--cb-ai-summary)] sm:text-[15px]">
                  {article.summary}
                </p>
              ) : (
                <p className="mt-2.5 text-[14px] font-normal leading-relaxed text-[var(--cb-ai-summary)] sm:text-[15px]">
                  <span className="mr-1 inline-block h-2 w-2 animate-pulse rounded-full bg-[var(--cb-accent)] align-middle motion-reduce:animate-none" aria-hidden />
                  Generating summary...
                </p>
              )}
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-x-2 text-[12px] font-medium text-[var(--cb-meta)]">
              {published ? <time>{published}</time> : null}
              {published && article.region ? (
                <span className="text-[var(--cb-meta-dot)]" aria-hidden>
                  ·
                </span>
              ) : null}
              {article.region ? (
                <span className="text-[var(--cb-text-tertiary)]">{article.region}</span>
              ) : null}
            </div>
          </div>
        </button>

        {/* Bookmark Button */}
        {onToggleBookmark ? (
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onToggleBookmark(article);
            }}
            className={`absolute right-4 top-4 z-10 flex h-10 w-10 items-center justify-center rounded-full backdrop-blur-md transition-all duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cb-accent)] hover:scale-110 active:scale-95 motion-reduce:hover:scale-100 ${
              bookmarked
                ? "bg-black/60 text-[var(--cb-accent)] shadow-[0_0_15px_rgba(56,189,248,0.4)] ring-1 ring-[var(--cb-accent)]/50"
                : "bg-black/40 text-white hover:bg-black/60 ring-1 ring-white/20 hover:ring-white/40"
            }`}
            aria-label={bookmarked ? "Remove from saved" : "Save story"}
            aria-pressed={bookmarked}
          >
            {bookmarked ? (
              <IconBookmarkFilled className="h-5 w-5 drop-shadow-md" />
            ) : (
              <IconBookmark className="h-5 w-5 drop-shadow-md" />
            )}
          </button>
        ) : null}
      </div>
    </article>
  );
}
