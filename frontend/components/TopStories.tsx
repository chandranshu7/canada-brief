import Link from "next/link";
import type { Article } from "@/lib/types";
import {
  articleSourceCount,
  articleSourceList,
  isMultiSourceCluster,
} from "@/lib/clusterUi";
import {
  formatPublishedDisplay,
  parsePublishedDate,
} from "@/lib/formatPublished";
import { categoryBadgeClass } from "./categoryStyles";
import { sourceOverlayBadgeClass } from "./sourceStyles";
import { SectionHeader } from "./SectionHeader";
import { IconSparkle } from "./icons";

type TopStoriesProps = {
  articles: Article[];
};

type SpotlightVariant = "lead" | "compact";

/** Backend `summary` when present; otherwise a short fallback. */
function blurbForTopStory(article: Article): string {
  const fromApi = (article.summary ?? "").trim();
  if (fromApi) return fromApi;

  const title = (article.title ?? "").trim();
  if (title.length > 100) {
    return `${title.slice(0, 97)}…`;
  }
  if (title) {
    return "Open the source for reporting, context, and updates.";
  }
  return "Open the article for the full story.";
}

/** Single-line teaser for overlay (ellipsis via CSS). */
function oneLineBlurb(article: Article): string {
  const s = blurbForTopStory(article);
  if (s.length <= 120) return s;
  return `${s.slice(0, 117)}…`;
}

export function TopStories({ articles }: TopStoriesProps) {
  if (articles.length === 0) return null;

  const [lead, ...rest] = articles;
  const single = articles.length === 1;

  return (
    <section className="relative">
      <SectionHeader
        eyebrow="Spotlight"
        title="Top stories"
        subtitle="Mixed sources from your filters — tap to open in a new tab."
        right={
          <span className="inline-flex items-center gap-1.5 text-slate-400">
            <IconSparkle className="h-3.5 w-3.5 text-amber-400/90" />
            Editorial picks
          </span>
        }
      />

      <div
        className={
          single
            ? "grid gap-5"
            : "grid gap-5 lg:grid-cols-3 lg:items-stretch lg:gap-6"
        }
      >
        {lead && (
          <div
            className={`animate-fade-in-up flex min-h-0 opacity-0 ${single ? "" : "lg:col-span-2 lg:min-h-[min(480px,68vh)]"}`}
          >
            <SpotlightCard article={lead} variant="lead" />
          </div>
        )}

        {rest.length > 0 && (
          <div className="flex min-h-0 flex-col gap-5 lg:col-span-1 lg:min-h-[min(480px,68vh)]">
            {rest.map((article, i) => (
              <div
                key={`${article.link}-${i}`}
                className="animate-fade-in-up min-h-0 flex-1 opacity-0"
                style={{ animationDelay: `${(i + 1) * 80}ms` }}
              >
                <SpotlightCard article={article} variant="compact" />
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

const pillClass =
  "inline-flex max-w-full shrink-0 truncate rounded-full bg-white/14 px-2.5 py-0.5 text-[11px] font-semibold tracking-wide text-white/95 ring-1 ring-white/30 backdrop-blur-md";

/** Desktop: summary softer until hover; mobile: always full strength. */
const summaryHoverClasses =
  "transition-[opacity,transform] duration-300 ease-out motion-reduce:transition-none " +
  "translate-y-0 opacity-100 " +
  "md:translate-y-1.5 md:opacity-50 " +
  "md:group-hover:translate-y-0 md:group-hover:opacity-100";

/**
 * One family of image-first spotlight cards: chips on top, title + one summary line + pills
 * in a strong bottom gradient. No separate footer — full card is the image.
 */
function SpotlightCard({
  article,
  variant,
}: {
  article: Article;
  variant: SpotlightVariant;
}) {
  const isLead = variant === "lead";
  const img = (article.image_url ?? "").trim();
  const cat = article.category;
  const src = (article.source || "").trim();
  const sources = articleSourceList(article);
  const multi = isMultiSourceCluster(article);
  const nSources = articleSourceCount(article);
  const line = oneLineBlurb(article);
  const when = formatPublishedDisplay(article.published);

  const ring = multi
    ? isLead
      ? "ring-2 ring-amber-400/50 shadow-[0_12px_44px_-12px_rgba(245,158,11,0.26)]"
      : "ring-2 ring-amber-400/45 shadow-[0_10px_32px_-12px_rgba(245,158,11,0.2)]"
    : isLead
      ? "ring-1 ring-slate-900/[0.07] shadow-[0_12px_40px_-14px_rgba(15,23,42,0.18)]"
      : "ring-1 ring-slate-900/[0.07] shadow-[0_10px_28px_-12px_rgba(15,23,42,0.14)]";

  const minH = isLead
    ? "min-h-[280px] sm:min-h-[340px] lg:min-h-[380px]"
    : "min-h-[210px] sm:min-h-[232px]";

  return (
    <Link
      href={article.link}
      target="_blank"
      rel="noopener noreferrer"
      className={`group relative flex h-full w-full flex-col overflow-hidden rounded-[1.35rem] bg-slate-900 transition-all duration-300 ease-out hover:shadow-[0_20px_44px_-14px_rgba(15,23,42,0.26)] md:hover:-translate-y-1 md:hover:shadow-[0_28px_52px_-16px_rgba(15,23,42,0.32)] ${ring}`}
    >
      <div className={`relative flex-1 overflow-hidden ${minH}`}>
        {img ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={img}
            alt=""
            className="absolute inset-0 z-0 h-full w-full object-cover transition-[transform,filter] duration-300 ease-out will-change-transform group-hover:scale-[1.03] group-hover:brightness-[0.97] md:group-hover:scale-[1.045]"
          />
        ) : (
          <div className="absolute inset-0 z-0 bg-gradient-to-br from-slate-600 via-slate-700 to-slate-900" />
        )}

        <div
          className="pointer-events-none absolute inset-x-0 top-0 z-10 h-[38%] bg-gradient-to-b from-black/72 via-black/20 to-transparent transition-opacity duration-300 md:group-hover:opacity-95"
          aria-hidden
        />
        <div
          className={`pointer-events-none absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-black/[0.96] via-black/78 to-transparent transition-opacity duration-300 md:group-hover:from-black/[0.98] md:group-hover:via-black/85 ${isLead ? "h-[58%] sm:h-[54%]" : "h-[62%]"}`}
          aria-hidden
        />
        <div
          className="pointer-events-none absolute inset-x-0 bottom-0 z-[11] h-[35%] bg-gradient-to-t from-black/90 to-transparent transition-opacity duration-300 md:group-hover:from-black/95"
          aria-hidden
        />

        {/* Desktop hover: darken image (below text) */}
        <div
          className="pointer-events-none absolute inset-0 z-[12] bg-black/0 transition-colors duration-300 ease-out md:group-hover:bg-black/30"
          aria-hidden
        />

        {/* Top chips */}
        <div
          className={`absolute left-0 right-0 top-0 z-30 flex flex-wrap items-start gap-1.5 sm:gap-2 ${isLead ? "p-4 sm:p-5" : "p-3 sm:p-4"}`}
        >
          {isLead ? (
            <>
              {multi && (
                <span className="inline-flex items-center gap-1 rounded-full bg-black/60 px-2.5 py-1 text-[10px] font-bold tracking-wide text-amber-100 ring-1 ring-amber-300/45 backdrop-blur-md">
                  <span aria-hidden>🔥</span>
                  {nSources} sources
                </span>
              )}
              {!multi && src && (
                <span
                  className={`inline-flex max-w-[13rem] truncate rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.1em] shadow-md ring-1 backdrop-blur-md ${sourceOverlayBadgeClass(src)}`}
                >
                  {src}
                </span>
              )}
              {multi &&
                sources.slice(0, 2).map((s) => (
                  <span
                    key={s}
                    className={`inline-flex max-w-[8rem] truncate rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.08em] shadow-md ring-1 backdrop-blur-md sm:px-2.5 sm:text-[10px] ${sourceOverlayBadgeClass(s)}`}
                  >
                    {s}
                  </span>
                ))}
              {multi && sources.length > 2 && (
                <span className="inline-flex rounded-full bg-black/55 px-2 py-0.5 text-[9px] font-bold text-white/90 ring-1 ring-white/20 backdrop-blur-md sm:text-[10px]">
                  +{sources.length - 2}
                </span>
              )}
              {cat && (
                <span
                  className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] shadow-md ring-1 ring-white/25 backdrop-blur-md ${categoryBadgeClass(cat)}`}
                >
                  {cat}
                </span>
              )}
            </>
          ) : (
            <>
              {cat && (
                <span
                  className={`inline-flex max-w-[10rem] truncate rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.1em] shadow-md ring-1 ring-white/25 backdrop-blur-md sm:text-[10px] ${categoryBadgeClass(cat)}`}
                >
                  {cat}
                </span>
              )}
              {multi ? (
                <span className="inline-flex rounded-full bg-black/60 px-2 py-0.5 text-[9px] font-bold text-amber-100 ring-1 ring-amber-300/40 backdrop-blur-md sm:text-[10px]">
                  {nSources} sources
                </span>
              ) : (
                src && (
                  <span
                    className={`inline-flex max-w-[9rem] truncate rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.08em] ring-1 backdrop-blur-md sm:max-w-[10rem] sm:text-[10px] ${sourceOverlayBadgeClass(src)}`}
                  >
                    {src}
                  </span>
                )
              )}
            </>
          )}
        </div>

        {/* Bottom copy — above hover darken */}
        <div
          className={`absolute inset-x-0 bottom-0 z-30 flex flex-col ${isLead ? "gap-2 p-4 pb-5 sm:gap-2.5 sm:p-5 sm:pb-6" : "gap-1.5 p-3.5 pb-4 sm:gap-2 sm:p-4 sm:pb-5"}`}
        >
          <h3
            className={
              isLead
                ? "line-clamp-3 text-lg font-bold leading-tight tracking-tight text-white drop-shadow-[0_2px_14px_rgba(0,0,0,0.9)] sm:text-xl sm:leading-snug lg:text-2xl lg:leading-tight md:group-hover:drop-shadow-[0_2px_18px_rgba(0,0,0,0.95)]"
                : "line-clamp-2 text-[15px] font-bold leading-snug text-white drop-shadow-[0_2px_12px_rgba(0,0,0,0.88)] sm:text-base md:group-hover:drop-shadow-[0_2px_16px_rgba(0,0,0,0.92)]"
            }
          >
            {article.title}
          </h3>
          <p
            className={
              isLead
                ? `line-clamp-1 text-[13px] font-normal leading-snug text-white/88 [text-shadow:0_1px_10px_rgba(0,0,0,0.95)] sm:text-sm md:group-hover:text-white/95 ${summaryHoverClasses}`
                : `line-clamp-1 text-[12px] font-normal leading-snug text-white/85 [text-shadow:0_1px_8px_rgba(0,0,0,0.92)] sm:text-[13px] md:group-hover:text-white/95 ${summaryHoverClasses}`
            }
          >
            {line}
          </p>
          <div className="flex flex-wrap items-center gap-1.5 gap-y-1 pt-0.5 transition-opacity duration-300 md:opacity-90 md:group-hover:opacity-100">
            {when && (
              <time
                dateTime={
                  parsePublishedDate(article.published)?.toISOString() ??
                  undefined
                }
                className={`${pillClass} max-w-[14rem] font-medium tabular-nums sm:max-w-[16rem]`}
              >
                {when}
              </time>
            )}
            {article.region && <span className={pillClass}>{article.region}</span>}
            {isLead && !multi && src && (
              <span className={`${pillClass} max-w-[11rem] sm:max-w-[13rem]`}>
                {src}
              </span>
            )}
            {isLead && multi && <span className={pillClass}>{nSources} sources</span>}
            {!isLead && !article.region && !multi && src && (
              <span className={`${pillClass} max-w-[10rem]`}>{src}</span>
            )}
            {!isLead && !article.region && multi && (
              <span className={pillClass}>{nSources} sources</span>
            )}
          </div>
        </div>
      </div>
    </Link>
  );
}
