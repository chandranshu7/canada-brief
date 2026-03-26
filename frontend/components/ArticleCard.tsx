"use client";

import { useState } from "react";
import Link from "next/link";
import type { Article } from "@/lib/types";
import {
  articleSourceCount,
  articleSourceList,
  isMultiSourceCluster,
} from "@/lib/clusterUi";
import { formatPublishedDisplay } from "@/lib/formatPublished";
import { categoryBadgeClass } from "./categoryStyles";
import { sourceBadgeClass } from "./sourceStyles";

type ArticleCardProps = {
  article: Article;
  index?: number;
};

export function ArticleCard({ article, index = 0 }: ArticleCardProps) {
  const img = (article.image_url ?? "").trim();
  const [imgBroken, setImgBroken] = useState(false);
  const cat = article.topic_category ?? article.category;
  const src = (article.source || "").trim();
  const sources = articleSourceList(article);
  const multi = isMultiSourceCluster(article);
  const nSources = articleSourceCount(article);
  const published = formatPublishedDisplay(article.published);
  
  // Stagger the animation slightly based on index
  const delayMs = Math.min(index * 50, 400);

  return (
    <article
      className="animate-fade-in-up opacity-0"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      <Link
        href={article.link}
        target="_blank"
        rel="noopener noreferrer"
        className="group relative flex flex-col overflow-hidden rounded-3xl bg-[var(--cb-article-card-bg)] border border-[var(--cb-article-card-border)] shadow-[var(--cb-article-card-shadow)] transition-all duration-400 ease-[cubic-bezier(0.16,1,0.3,1)] hover:border-[var(--cb-article-card-hover-border)] hover:shadow-[var(--cb-article-card-hover-shadow)] hover:-translate-y-1.5"
      >
        {/* Edge-to-edge Hero Image */}
        <div className="relative h-56 w-full shrink-0 overflow-hidden bg-[var(--cb-thumb-bg)] sm:h-72">
          {img && !imgBroken ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={img}
              alt=""
              className="h-full w-full object-cover transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:scale-105"
              onError={() => setImgBroken(true)}
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-[var(--cb-thumb-gradient-from)] to-[var(--cb-thumb-gradient-to)]">
              <span className="px-4 text-center text-xs font-bold uppercase tracking-widest text-[var(--cb-thumb-label)] opacity-60">
                {(article.topic_category ?? article.category ?? "News").toString()}
              </span>
            </div>
          )}
          
          {/* Subtle gradient overlay at bottom of image for blending */}
          <div className="absolute inset-0 bg-gradient-to-t from-[var(--cb-article-card-bg)] via-transparent to-transparent opacity-80" />
          
          {/* Index Marker (Top Right) */}
          <span className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-full bg-black/40 backdrop-blur-md text-xs font-bold text-white shadow-sm ring-1 ring-white/20">
            {index + 1}
          </span>
        </div>

        {/* Content Section */}
        <div className="relative flex min-w-0 flex-1 flex-col p-5 sm:p-7">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {multi ? (
              <span className="truncate text-[10px] font-bold uppercase tracking-wider text-[var(--cb-accent)]">
                {nSources} sources
              </span>
            ) : src ? (
              <span className="truncate text-[10px] font-bold uppercase tracking-wider text-[var(--cb-accent)]">
                {src}
              </span>
            ) : null}
            {cat && (
              <span
                className={`inline-flex rounded-full px-2.5 py-0.5 text-[9px] font-bold uppercase tracking-widest ring-1 ${categoryBadgeClass(cat)}`}
              >
                {cat}
              </span>
            )}
            {multi &&
              sources.slice(0, 3).map((s) => (
                <span
                  key={s}
                  className={`inline-flex max-w-[8rem] truncate rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest ring-1 ${sourceBadgeClass(s)}`}
                >
                  {s}
                </span>
              ))}
          </div>

          <h3 className="font-display line-clamp-3 text-xl font-bold leading-tight tracking-tight text-[var(--cb-title)] transition-colors duration-200 group-hover:text-[var(--cb-title-hover)] sm:text-[22px]">
            {article.title}
          </h3>

          <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] font-medium text-[var(--cb-meta)]">
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

          {/* AI Summary Section - Premium Glass Tray */}
          <div className="mt-5 overflow-hidden rounded-2xl border border-[var(--cb-ai-tray-border)] bg-[var(--cb-ai-tray-bg)] p-4 shadow-inner backdrop-blur-md transition-colors duration-300">
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
              <p className="mt-2 line-clamp-3 text-sm font-normal leading-relaxed text-[var(--cb-ai-summary)]">
                {article.summary}
              </p>
            ) : null}
          </div>
        </div>
      </Link>
    </article>
  );
}
