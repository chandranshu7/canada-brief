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

type SingleStoryHeroProps = {
  article: Article;
};

const chipBase =
  "inline-flex max-w-[12rem] items-center truncate rounded-md px-2 py-0.5 text-[10px] font-medium tracking-wide ring-1 sm:max-w-[14rem] sm:text-[10.5px]";

/**
 * One dominant story card — web-focused, no swipe UI.
 */
export function SingleStoryHero({ article }: SingleStoryHeroProps) {
  const img = (article.image_url ?? "").trim();
  const cat = article.category;
  const region = (article.region ?? "").trim();
  const sources = articleSourceList(article);
  const multi = isMultiSourceCluster(article);
  const nSources = articleSourceCount(article);
  const published = formatPublishedDisplay(article.published);
  const href = (article.link || "#").trim();

  return (
    <article className="mx-auto w-full max-w-4xl overflow-hidden rounded-2xl border border-slate-200/70 bg-white shadow-[0_20px_50px_-24px_rgba(15,23,42,0.2)] ring-1 ring-slate-900/[0.03]">
      {/* position:relative is required so the gradient overlay cannot anchor to the viewport */}
      <div
        className="relative isolate aspect-[21/10] w-full max-w-full overflow-hidden bg-slate-100 sm:aspect-[21/9]"
        style={{ position: "relative" }}
      >
        {img ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={img}
            alt=""
            className="h-full w-full object-cover"
            sizes="(max-width: 768px) 100vw, 56rem"
          />
        ) : (
          <div className="h-full min-h-0 w-full bg-gradient-to-br from-slate-100 via-indigo-50/35 to-slate-50" />
        )}
        <div
          className="pointer-events-none absolute inset-0 z-[1] bg-gradient-to-t from-black/50 via-black/8 to-transparent"
          aria-hidden
        />
      </div>

      <div className="space-y-4 px-6 py-7 sm:space-y-5 sm:px-9 sm:py-9">
        <div className="flex flex-wrap items-center gap-1.5">
          {multi && (
            <span
              className={`${chipBase} bg-amber-500/[0.12] text-amber-950/90 ring-amber-400/25`}
            >
              {nSources} sources
            </span>
          )}
          {!multi &&
            sources.map((s) => (
              <span
                key={s}
                className={`${chipBase} ${sourceBadgeClass(s)} opacity-[0.92]`}
              >
                {s}
              </span>
            ))}
          {cat && (
            <span
              className={`${chipBase} ${categoryBadgeClass(cat)} opacity-[0.95]`}
            >
              {cat}
            </span>
          )}
          {region && (
            <span
              className={`${chipBase} bg-slate-50 text-slate-600 ring-slate-200/70`}
            >
              {region}
            </span>
          )}
        </div>

        <h1 className="text-balance text-[1.75rem] font-bold leading-[1.18] tracking-[-0.02em] text-slate-950 sm:text-[2.125rem] sm:leading-[1.15]">
          {article.title}
        </h1>

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
