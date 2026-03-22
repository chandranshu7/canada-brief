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
  const cat = article.category;
  const src = (article.source || "").trim();
  const sources = articleSourceList(article);
  const multi = isMultiSourceCluster(article);
  const nSources = articleSourceCount(article);
  const published = formatPublishedDisplay(article.published);
  const delayMs = Math.min(index * 45, 320);

  const cardRing = multi
    ? "ring-2 ring-amber-400/45 border-amber-200/80 bg-gradient-to-br from-amber-50/50 to-white/95"
    : "ring-1 ring-slate-900/[0.02] border-slate-200/80 bg-white/90";

  return (
    <article
      className="animate-fade-in-up opacity-0"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      <Link
        href={article.link}
        target="_blank"
        rel="noopener noreferrer"
        className={`group flex gap-4 overflow-hidden rounded-[1.15rem] border p-4 shadow-[0_4px_24px_-8px_rgba(15,23,42,0.08)] transition-all duration-300 ease-out hover:-translate-y-0.5 hover:border-slate-300/90 hover:bg-white hover:shadow-[0_16px_40px_-12px_rgba(15,23,42,0.12)] sm:gap-5 sm:p-5 ${cardRing}`}
      >
        <div className="relative aspect-[4/3] w-[6.75rem] shrink-0 overflow-hidden rounded-xl bg-slate-100 sm:w-[7.75rem]">
          {img ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={img}
              alt=""
              className="h-full w-full object-cover transition-[transform] duration-500 ease-out group-hover:scale-[1.06]"
            />
          ) : (
            <div className="h-full w-full bg-gradient-to-br from-slate-100 via-slate-50 to-indigo-50/50" />
          )}
        </div>

        <div className="min-w-0 flex-1 py-0.5">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            {multi && (
              <span className="inline-flex items-center gap-1 rounded-full bg-gradient-to-r from-amber-500/15 to-orange-500/10 px-2.5 py-0.5 text-[10px] font-bold tracking-wide text-amber-900 ring-1 ring-amber-400/40">
                <span aria-hidden>🔥</span>
                Covered by {nSources} sources
              </span>
            )}
            {!multi && src && (
              <span
                className={`inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em] ring-1 ${sourceBadgeClass(src)}`}
              >
                {src}
              </span>
            )}
            {multi &&
              sources.map((s) => (
                <span
                  key={s}
                  className={`inline-flex max-w-[10rem] truncate rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em] ring-1 ${sourceBadgeClass(s)}`}
                >
                  {s}
                </span>
              ))}
            {cat && (
              <span
                className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.1em] ring-1 ${categoryBadgeClass(cat)}`}
              >
                {cat}
              </span>
            )}
          </div>
          <h3 className="text-[1.05rem] font-semibold leading-snug tracking-tight text-slate-900 transition-colors duration-200 group-hover:text-slate-800 line-clamp-2 sm:text-lg sm:leading-tight">
            {article.title}
          </h3>
          {article.summary && (
            <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-slate-600">
              {article.summary}
            </p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-slate-400">
            {published && (
              <>
                <time className="font-medium text-slate-400/95">{published}</time>
                {article.region && (
                  <span className="text-slate-300" aria-hidden>
                    ·
                  </span>
                )}
              </>
            )}
            {article.region && (
              <span className="font-medium text-slate-500">{article.region}</span>
            )}
          </div>
        </div>
      </Link>
    </article>
  );
}
