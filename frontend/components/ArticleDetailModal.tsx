"use client";

import Link from "next/link";
import { useCallback, useEffect } from "react";
import type { Article } from "@/lib/types";
import {
  articleSourceCount,
  articleSourceList,
  isMultiSourceCluster,
} from "@/lib/clusterUi";
import { formatPublishedDisplay } from "@/lib/formatPublished";
import { getHeroImageDisplay } from "@/lib/heroImage";
import { categoryBadgeClass } from "./categoryStyles";
import { IconBookmark, IconBookmarkFilled } from "./icons";

type ArticleDetailModalProps = {
  article: Article | null;
  locationLine?: string | null;
  onClose: () => void;
  bookmarked?: boolean;
  onToggleBookmark?: (article: Article) => void;
};

export function ArticleDetailModal({
  article,
  locationLine,
  onClose,
  bookmarked = false,
  onToggleBookmark,
}: ArticleDetailModalProps) {
  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (!article) return;
    document.addEventListener("keydown", handleKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.body.style.overflow = prev;
    };
  }, [article, handleKey]);

  if (!article) return null;

  const img = (article.image_url ?? "").trim();
  const { src: imageSrc } = getHeroImageDisplay(img);
  const sources = articleSourceList(article);
  const multi = isMultiSourceCluster(article);
  const nSources = articleSourceCount(article);
  const published = formatPublishedDisplay(article.published);
  const href = (article.link || "#").trim();
  const categoryLabel = (article.topic_category ?? article.category ?? "").trim();

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="article-detail-title"
    >
      <button
        type="button"
        className="absolute inset-0 bg-[var(--cb-modal-backdrop)] backdrop-blur-md transition-opacity duration-300"
        aria-label="Close"
        onClick={onClose}
      />

      <div className="animate-fade-in-up relative flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-[32px] border border-[var(--cb-modal-border)] bg-[var(--cb-modal-bg)] shadow-[0_24px_64px_-12px_rgba(0,0,0,0.8)] sm:rounded-[32px]">
        {/* Floating Header over image */}
        <div className="absolute left-0 right-0 top-0 z-10 flex items-center justify-between bg-gradient-to-b from-black/80 via-black/40 to-transparent px-4 py-4 sm:px-6">
          <span className="rounded-full bg-black/40 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-white backdrop-blur-md ring-1 ring-white/20">
            Canada Brief
          </span>
          <div className="flex items-center gap-2">
            {onToggleBookmark ? (
              <button
                type="button"
                onClick={() => onToggleBookmark(article)}
                className={`flex h-10 w-10 items-center justify-center rounded-full backdrop-blur-md transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cb-accent)] ${
                  bookmarked
                    ? "bg-black/60 text-[var(--cb-accent)] shadow-[0_0_15px_rgba(56,189,248,0.5)] ring-1 ring-[var(--cb-accent)]/50"
                    : "bg-black/40 text-white ring-1 ring-white/30 hover:bg-black/60 hover:ring-white/50"
                }`}
                aria-label={bookmarked ? "Remove from saved" : "Save story"}
                aria-pressed={bookmarked}
              >
                {bookmarked ? (
                  <IconBookmarkFilled className="h-5 w-5" />
                ) : (
                  <IconBookmark className="h-5 w-5" />
                )}
              </button>
            ) : null}
            <button
              type="button"
              onClick={onClose}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-black/40 text-white backdrop-blur-md transition hover:bg-black/60 ring-1 ring-white/30 hover:ring-white/50"
              aria-label="Close"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="overflow-y-auto overscroll-contain pb-safe">
          {/* Cinematic Edge-to-Edge Image */}
          <div className="relative h-72 w-full overflow-hidden bg-[var(--cb-modal-image-bg)] sm:h-96">
            {imageSrc ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={imageSrc}
                alt=""
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-[var(--cb-modal-image-bg)] to-[var(--cb-page)]">
                <span className="text-xl font-display font-semibold uppercase tracking-widest text-[var(--cb-text-muted)] opacity-50">
                  {categoryLabel || "News"}
                </span>
              </div>
            )}
            {/* Blend image into content */}
            <div className="absolute inset-0 bg-gradient-to-t from-[var(--cb-modal-bg)] via-[var(--cb-modal-bg)]/20 to-transparent" />
          </div>

          <div className="relative z-10 -mt-16 space-y-6 px-5 pb-8 sm:-mt-20 sm:px-8">
            <div className="flex flex-wrap gap-2">
              {multi && (
                <span className="rounded-full bg-[var(--cb-cluster-bg)] px-3 py-1 text-[11px] font-bold uppercase tracking-widest text-[var(--cb-cluster-text)] shadow-sm ring-1 ring-[var(--cb-cluster-ring)] backdrop-blur-md">
                  {nSources} sources
                </span>
              )}
              {!multi && sources.length > 0 &&
                sources.map((s) => (
                  <span
                    key={s}
                    className="max-w-[14rem] truncate rounded-full bg-[var(--cb-badge-bg)] px-3 py-1 text-[11px] font-bold uppercase tracking-widest text-[var(--cb-badge-text)] shadow-sm backdrop-blur-md"
                  >
                    {s}
                  </span>
                ))}
              {categoryLabel ? (
                <span
                  className={`rounded-full px-3 py-1 text-[11px] font-bold uppercase tracking-widest shadow-sm ring-1 backdrop-blur-md ${categoryBadgeClass(categoryLabel)}`}
                >
                  {categoryLabel}
                </span>
              ) : null}
              {locationLine && (
                <span className="rounded-full bg-[var(--cb-badge-muted-bg)] px-3 py-1 text-[11px] font-bold uppercase tracking-widest text-[var(--cb-badge-muted-text)] shadow-sm backdrop-blur-md">
                  {locationLine}
                </span>
              )}
            </div>

            <h2
              id="article-detail-title"
              className="text-balance font-display text-3xl font-bold leading-[1.15] tracking-tight text-[var(--cb-modal-body)] sm:text-4xl"
            >
              {article.title}
            </h2>

            <div className="flex flex-wrap gap-x-3 text-sm font-medium text-[var(--cb-meta)]">
              {published ? <time>{published}</time> : null}
              {published && article.region ? (
                <span className="text-[var(--cb-meta-dot)]">•</span>
              ) : null}
              {article.region ? (
                <span className="text-[var(--cb-text-tertiary)]">{article.region}</span>
              ) : null}
            </div>

            {/* AI Summary Block - Glowing Glass Panel */}
            <div className="relative overflow-hidden rounded-3xl border border-[var(--cb-ai-tray-border)] bg-[var(--cb-ai-tray-bg)] p-6 shadow-[inset_0_1px_1px_rgba(255,255,255,0.1)] backdrop-blur-xl">
              <div className="mb-4 flex items-center gap-2.5">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--cb-ai-label)] opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--cb-ai-label)]"></span>
                </span>
                <span className="text-[11px] font-bold uppercase tracking-[0.15em] text-[var(--cb-ai-label)]">
                  AI Summary
                </span>
              </div>
              {article.summary ? (
                <p className="text-pretty text-[16px] leading-[1.7] text-[var(--cb-modal-summary)] sm:text-[18px]">
                  {article.summary}
                </p>
              ) : (
                <div className="flex items-center gap-3">
                  <div className="flex h-4 w-4 shrink-0 animate-spin items-center justify-center rounded-full border-2 border-t-[var(--cb-accent)] border-r-transparent border-b-transparent border-l-transparent" />
                  <p className="text-[16px] leading-relaxed text-[var(--cb-text-muted)]">
                    Generating story summary...
                  </p>
                </div>
              )}
            </div>

            <div className="pt-2">
              <Link
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="group relative flex w-full items-center justify-center overflow-hidden rounded-2xl bg-[var(--cb-button-primary-bg)] py-4 text-[16px] font-bold tracking-wide text-[var(--cb-button-primary-text)] shadow-lg transition-all hover:scale-[1.02] hover:bg-[var(--cb-button-primary-hover)] hover:shadow-xl active:scale-95"
              >
                <span className="relative z-10 flex items-center gap-2">
                  Read Full Article
                  <svg className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                </span>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
