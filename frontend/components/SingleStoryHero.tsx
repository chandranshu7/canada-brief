import Image from "next/image";
import Link from "next/link";
import type { Article } from "@/lib/types";
import {
  articleSourceCount,
  articleSourceList,
  isMultiSourceCluster,
} from "@/lib/clusterUi";
import { formatPublishedDisplay } from "@/lib/formatPublished";
import { getHeroImageDisplay } from "@/lib/heroImage";

type SingleStoryHeroProps = {
  article: Article;
  /** First-paint LCP hint for the visible card */
  priority?: boolean;
  /** Subtle geo line vs your saved area, e.g. "Local to Toronto" or "Ontario" */
  locationContext?: string | null;
};

const chipBase =
  "inline-flex max-w-[12rem] items-center truncate rounded-md px-2 py-0.5 text-[10px] font-medium tracking-wide ring-1 sm:max-w-[14rem] sm:text-[10.5px]";

/**
 * One dominant story card — large hero image with title overlay (editorial / Apple News–style).
 */
export function SingleStoryHero({
  article,
  priority = true,
  locationContext = null,
}: SingleStoryHeroProps) {
  const img = (article.image_url ?? "").trim();
  const { src: imageSrc, viaProxy } = getHeroImageDisplay(img);
  const cat = article.topic_category ?? article.category;
  const region = (article.region ?? "").trim();
  const geoChip = (locationContext || region).trim();
  const sources = articleSourceList(article);
  const multi = isMultiSourceCluster(article);
  const nSources = articleSourceCount(article);
  const published = formatPublishedDisplay(article.published);
  const href = (article.link || "#").trim();

  return (
    <article className="mx-auto w-full max-w-4xl overflow-hidden rounded-2xl border border-slate-200/70 bg-white shadow-[0_20px_50px_-24px_rgba(15,23,42,0.2)] ring-1 ring-slate-900/[0.03]">
      {/* 60–70vh hero: fixed height reduces CLS; image uses fill + object-cover */}
      <div
        className="relative isolate w-full overflow-hidden rounded-t-2xl bg-slate-100"
        style={{
          minHeight: "clamp(18rem, 65vh, 70vh)",
          height: "min(70vh, 52rem)",
        }}
      >
        {imageSrc ? (
          <Image
            src={imageSrc}
            alt=""
            fill
            priority={priority}
            quality={100}
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 90vw, 896px"
            unoptimized={!viaProxy}
            className="hero-image-crisp object-cover object-center [image-rendering:auto]"
          />
        ) : (
          <div
            className="absolute inset-0 bg-gradient-to-br from-slate-100 via-indigo-50/35 to-slate-50"
            aria-hidden
          />
        )}

        {/* Bottom → transparent so title stays readable */}
        <div
          className="pointer-events-none absolute inset-0 z-[1] bg-gradient-to-t from-black/75 via-black/35 via-40% to-transparent"
          aria-hidden
        />

        {/* Meta chips — top */}
        <div className="absolute left-0 right-0 top-0 z-[2] flex flex-wrap items-center gap-1.5 p-4 sm:p-6">
          {multi && (
            <span
              className={`${chipBase} bg-black/35 text-white ring-white/25 backdrop-blur-sm`}
            >
              {nSources} sources
            </span>
          )}
          {!multi &&
            sources.map((s) => (
              <span
                key={s}
                className={`${chipBase} bg-black/35 text-white/95 ring-white/20 backdrop-blur-sm`}
              >
                {s}
              </span>
            ))}
          {cat && (
            <span
              className={`${chipBase} bg-black/35 text-white/95 ring-white/20 backdrop-blur-sm`}
            >
              {cat}
            </span>
          )}
          {geoChip && (
            <span
              className={`${chipBase} bg-black/35 text-white/90 ring-white/20 backdrop-blur-sm`}
            >
              {geoChip}
            </span>
          )}
        </div>

        {/* Title — bottom on image */}
        <div className="absolute bottom-0 left-0 right-0 z-[2] p-5 pb-6 sm:p-8 sm:pb-8">
          <h1 className="text-balance text-[1.5rem] font-bold leading-[1.15] tracking-[-0.02em] text-white drop-shadow-[0_2px_12px_rgba(0,0,0,0.45)] sm:text-[2rem] sm:leading-[1.12] md:text-[2.25rem]">
            {article.title}
          </h1>
        </div>
      </div>

      <div className="space-y-4 rounded-b-2xl px-6 py-7 sm:space-y-5 sm:px-9 sm:py-9">
        {article.summary ? (
          <p className="max-w-[46ch] text-pretty text-[1.0625rem] leading-[1.72] text-slate-600 sm:text-[1.085rem] sm:leading-[1.75]">
            {article.summary}
          </p>
        ) : null}

        {published ? (
          <p className="text-xs font-medium text-slate-400 sm:text-[13px]">
            <time>{published}</time>
          </p>
        ) : null}

        <div className="pt-1">
          <Link
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex w-full items-center justify-center rounded-lg bg-slate-900 px-5 py-3 text-sm font-semibold text-white shadow-md shadow-slate-900/12 transition hover:bg-slate-800 sm:w-auto sm:min-w-[13rem]"
          >
            Read full article
          </Link>
        </div>
      </div>
    </article>
  );
}
