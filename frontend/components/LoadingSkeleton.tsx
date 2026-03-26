import { FeedCardSkeleton } from "./FeedCardSkeleton";

type LoadingSkeletonProps = {
  /** Number of placeholder cards (default matches first-page feel). */
  count?: number;
  withBookmark?: boolean;
};

/** Full-feed initial load — matches `FeedCard` rows for stable layout. */
export function LoadingSkeleton({
  count = 5,
  withBookmark = true,
}: LoadingSkeletonProps) {
  return (
    <div className="flex flex-col gap-3 pb-4" role="status" aria-live="polite">
      <span className="sr-only">Loading stories</span>
      <div className="mb-1 inline-flex items-center gap-2 self-start rounded-full border border-[var(--cb-border-subtle)] bg-[var(--cb-surface)] px-2.5 py-1 text-xs font-medium text-[var(--cb-text-tertiary)]">
        <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--cb-accent)] motion-reduce:animate-none" aria-hidden />
        Fetching latest stories
      </div>
      {Array.from({ length: count }, (_, i) => (
        <FeedCardSkeleton key={i} index={i} withBookmark={withBookmark} />
      ))}
    </div>
  );
}
