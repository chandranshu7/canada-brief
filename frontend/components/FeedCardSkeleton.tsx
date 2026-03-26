/** Skeleton matching the hero-image card shell used by `FeedCard`. */

type FeedCardSkeletonProps = {
  index?: number;
  /** Match feed cards that show the bookmark column. */
  withBookmark?: boolean;
};

const line = (className: string) => (
  <div
    className={`rounded-md bg-[linear-gradient(90deg,var(--cb-skeleton-muted)_0%,var(--cb-skeleton)_45%,var(--cb-skeleton-muted)_100%)] bg-[length:200%_100%] animate-shimmer ${className}`}
    aria-hidden
  />
);

export function FeedCardSkeleton({
  index = 0,
  withBookmark = true,
}: FeedCardSkeletonProps) {
  const delayMs = Math.min(index * 45, 240);
  return (
    <div
      className="animate-fade-in opacity-0 motion-reduce:animate-none motion-reduce:opacity-100"
      style={{ animationDelay: `${delayMs}ms` }}
      aria-hidden
    >
      <div className="relative">
        <div className="overflow-hidden rounded-xl border border-[var(--cb-article-card-border)] bg-[var(--cb-article-card-bg)]">
          <div className="relative h-[188px] w-full bg-[var(--cb-thumb-bg)] sm:h-[196px]">
            <div className="h-full w-full bg-[linear-gradient(135deg,var(--cb-skeleton-muted)_0%,var(--cb-skeleton)_50%,var(--cb-skeleton-muted)_100%)] bg-[length:200%_200%] animate-shimmer opacity-90" />
            <div className="absolute bottom-2.5 left-2.5 h-6 w-11 rounded-full bg-black/35" />
            <div className="absolute right-2.5 bottom-2.5 h-6 w-24 rounded-full bg-black/35" />
          </div>
          <div className="p-[15px]">
            {line("h-2.5 w-28")}
            <div className="mt-3 space-y-2">
              {line("h-4 w-full")}
              {line("h-4 w-[90%]")}
            </div>
            <div className="mt-3 border-l-2 border-[var(--cb-ai-label)] pl-3">
              {line("h-2.5 w-16")}
              <div className="mt-1.5 space-y-1.5">
                {line("h-3.5 w-full opacity-90")}
                {line("h-3.5 w-[86%] opacity-90")}
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              {line("h-2.5 w-20")}
              {line("h-2.5 w-16 opacity-80")}
            </div>
          </div>
        </div>
        {withBookmark ? (
          <div
            className="absolute top-2.5 right-2.5 h-7 w-7 rounded-lg bg-[linear-gradient(90deg,var(--cb-skeleton-muted)_0%,var(--cb-skeleton)_50%,var(--cb-skeleton-muted)_100%)] bg-[length:200%_100%] animate-shimmer ring-1 ring-white/30"
            aria-hidden
          />
        ) : null}
      </div>
    </div>
  );
}
