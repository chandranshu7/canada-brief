"use client";

import { useCallback, useEffect, useState } from "react";
import type { Article } from "@/lib/types";
import { fetchDailyBrief, type DailyBriefStory } from "@/lib/api";
import { formatPublishedDisplay } from "@/lib/formatPublished";
import { getHeroImageDisplay } from "@/lib/heroImage";
import { DailyBriefSkeleton } from "./DailyBriefSkeleton";
import { categoryBadgeClass } from "./categoryStyles";

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

function BriefStoryImage({
  imageUrl,
  source,
  title,
  storyNumber,
}: {
  imageUrl?: string;
  source?: string;
  title?: string;
  storyNumber: string;
}) {
  const [broken, setBroken] = useState(false);
  const raw = (imageUrl ?? "").trim();
  const { src } = getHeroImageDisplay(raw);
  const show = Boolean(src) && !broken;
  const sourceLabel = (source ?? "").trim() || "Canada Brief";
  const seed = `${title || ""}|${sourceLabel}|${storyNumber}`;
  const hue = hashString(seed) % 360;
  const placeholderLetter = firstDisplayChar(title || sourceLabel);
  const placeholderBg = `linear-gradient(135deg, hsl(${hue} 45% 34%), hsl(${(hue + 48) % 360} 52% 18%))`;

  return (
    <div className="relative h-72 w-full overflow-hidden sm:h-96">
      {show ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt=""
          className="h-full w-full object-cover transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:scale-105"
          onError={() => setBroken(true)}
        />
      ) : (
        <div
          className="flex h-full w-full items-center justify-center"
          style={{ backgroundImage: placeholderBg }}
        >
          <span className="text-6xl font-display font-semibold uppercase tracking-wide text-white opacity-30">
            {placeholderLetter}
          </span>
        </div>
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black via-black/20 to-transparent opacity-80" />
      
      <span className="absolute left-4 top-4 flex h-8 w-8 items-center justify-center rounded-full bg-black/40 text-[12px] font-bold text-white shadow-sm ring-1 ring-white/30 backdrop-blur-md">
        {storyNumber}
      </span>
      <span className="absolute right-4 top-4 rounded-full bg-black/40 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-[#38bdf8] shadow-sm ring-1 ring-white/30 backdrop-blur-md">
        {sourceLabel}
      </span>
    </div>
  );
}

type DailyBriefCardProps = {
  apiBaseUrl: string;
  reloadNonce: number;
  onArticleOpen: (article: Article) => void;
};

function storyToArticle(s: DailyBriefStory): Article {
  const cat = (s.category ?? "").trim();
  return {
    id: s.id,
    title: s.title,
    summary: s.summary,
    source: s.source,
    link: s.link,
    published: s.published,
    category: cat || undefined,
    topic_category: cat || undefined,
    region: s.region,
    image_url: s.image_url,
  };
}

function formatBriefTitleLine(isoDate: string): string {
  const d = new Date(`${isoDate}T12:00:00.000Z`);
  const formatted = new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(d);
  return `The Brief — ${formatted}`;
}

export function DailyBriefCard({
  apiBaseUrl,
  reloadNonce,
  onArticleOpen,
}: DailyBriefCardProps) {
  const [stories, setStories] = useState<DailyBriefStory[]>([]);
  const [headerLine, setHeaderLine] = useState<string | null>(null);
  const [readLabel, setReadLabel] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchDailyBrief(apiBaseUrl);
      setStories(data.stories ?? []);
      setHeaderLine(formatBriefTitleLine(data.brief_date));
      setReadLabel(data.estimated_read_time_label || "");
    } catch {
      setStories([]);
      setHeaderLine(null);
      setReadLabel("");
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl]);

  useEffect(() => {
    void load();
  }, [load, reloadNonce]);

  if (loading) return <DailyBriefSkeleton />;
  if (!headerLine || stories.length === 0) return null;

  return (
    <section className="animate-fade-in-up mb-12 flex flex-col pt-4">
      <div className="mb-6 flex flex-col gap-2 px-2 sm:px-0">
        <h2 className="font-display text-4xl font-extrabold tracking-tight text-[var(--cb-title)] sm:text-5xl">
          <span className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
            Top Headlines
          </span>
        </h2>
        <div className="mt-1 flex items-center gap-3">
          <p className="text-lg font-medium text-[var(--cb-text-secondary)]">
            {headerLine}
          </p>
          <span className="rounded-full bg-cyan-500/20 px-3 py-1 text-xs font-bold uppercase tracking-widest text-cyan-400 shadow-[0_0_15px_rgba(34,211,238,0.2)] ring-1 ring-cyan-500/40">
            {readLabel || "Quick Read"}
          </span>
        </div>
      </div>

      <div className="relative -mx-5 sm:mx-0">
        <ol className="flex snap-x snap-mandatory gap-6 overflow-x-auto px-5 pb-8 pt-4 [scrollbar-width:none] [-ms-overflow-style:none] sm:px-0 [&::-webkit-scrollbar]:hidden">
          {stories.map((s, i) => {
            const article = storyToArticle(s);
            const published = formatPublishedDisplay(s.published);
            const displayNumber = String(i + 1).padStart(2, "0");
            const source = (s.source ?? "").trim();
            const cat = article.category ?? article.topic_category;
            return (
              <li
                key={s.id ?? `${s.link}-${i}`}
                className="w-[85vw] max-w-[420px] shrink-0 snap-center sm:snap-start animate-fade-in-up"
                style={{ animationDelay: `${i * 100}ms` }}
              >
                <button
                  type="button"
                  onClick={() => onArticleOpen(article)}
                  className="group relative block w-full overflow-hidden rounded-[32px] border border-[var(--cb-article-card-border)] bg-black text-left shadow-[0_20px_40px_-15px_rgba(0,0,0,0.8)] transition-all duration-400 ease-[cubic-bezier(0.16,1,0.3,1)] hover:-translate-y-2 hover:border-cyan-500/50 hover:shadow-[0_25px_60px_-15px_rgba(34,211,238,0.4)]"
                >
                  <BriefStoryImage
                    imageUrl={s.image_url}
                    source={source}
                    title={s.title}
                    storyNumber={displayNumber}
                  />

                  {/* Absolute positioned content overlaid on bottom of image */}
                  <div className="absolute inset-x-0 bottom-0 p-6">
                    {cat && (
                      <span className={`mb-3 inline-block rounded-full px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-white shadow-md ring-1 ring-white/20 backdrop-blur-md ${categoryBadgeClass(cat)}`}>
                        {cat}
                      </span>
                    )}
                    <h3 className="font-display text-2xl font-bold leading-tight tracking-tight text-white transition-colors duration-200 group-hover:text-cyan-300">
                      {s.title}
                    </h3>

                    <div className="mt-4 rounded-xl border border-white/10 bg-black/40 p-3 shadow-[inset_0_1px_1px_rgba(255,255,255,0.1)] backdrop-blur-xl">
                      <div className="flex items-center gap-2">
                         <span className="relative flex h-2 w-2">
                           <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-75"></span>
                           <span className="relative inline-flex h-2 w-2 rounded-full bg-cyan-400"></span>
                         </span>
                         <span className="text-[9px] font-bold uppercase tracking-[0.15em] text-cyan-300">
                           AI Summary
                         </span>
                      </div>
                      <p className="mt-2 line-clamp-2 text-sm text-gray-200">
                        {(s.summary ?? "").trim() || "Summary unavailable for this story right now."}
                      </p>
                    </div>

                    <div className="mt-3 flex items-center gap-2 text-xs font-medium text-gray-400">
                      {published ? <time>{published}</time> : null}
                      {published && (s.region ?? "").trim() ? <span>·</span> : null}
                      {(s.region ?? "").trim() ? <span className="truncate">{(s.region ?? "").trim()}</span> : null}
                    </div>
                  </div>
                </button>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
