/** Loading placeholder aligned with `DailyBriefCard` loaded layout. */

const line = (className: string) => (
  <div
    className={`rounded-md bg-[linear-gradient(90deg,var(--cb-skeleton-muted)_0%,var(--cb-skeleton)_45%,var(--cb-skeleton-muted)_100%)] bg-[length:200%_100%] animate-shimmer ${className}`}
    aria-hidden
  />
);

export function DailyBriefSkeleton() {
  return (
    <section
      className="rounded-2xl border border-[var(--cb-border-subtle)] bg-[var(--cb-surface)]/90 p-4 shadow-sm ring-1 ring-[var(--cb-card-ring)] backdrop-blur-sm transition-opacity duration-200"
      aria-busy="true"
      aria-label="Daily Brief loading"
    >
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        {line("h-5 w-3/4 sm:w-1/2")}
        <div className="flex gap-2">
          {line("h-3 w-24")}
          {line("h-3 w-20")}
        </div>
      </div>
      <ul className="list-none space-y-[14px]">
        {[0, 1, 2, 3, 4].map((i) => (
          <li
            key={i}
            className="overflow-hidden rounded-xl border border-[var(--cb-article-card-border)] bg-[var(--cb-article-card-bg)]"
          >
            <div className="relative h-[188px] w-full bg-[var(--cb-thumb-bg)] sm:h-[196px]">
              <div className="h-full w-full bg-[linear-gradient(135deg,var(--cb-skeleton-muted)_0%,var(--cb-skeleton)_50%,var(--cb-skeleton-muted)_100%)] bg-[length:200%_200%] animate-shimmer opacity-90" />
              <div className="absolute bottom-2.5 left-2.5 h-6 w-11 rounded-full bg-black/35" />
              <div className="absolute right-2.5 bottom-2.5 h-6 w-24 rounded-full bg-black/35" />
            </div>
            <div className="p-[15px]">
              <div className="space-y-2">
                {line("h-4 w-full")}
                {line("h-4 w-[90%]")}
              </div>
              <div className="mt-3 border-l-2 border-[var(--cb-ai-label)] pl-3">
                {line("h-2.5 w-16")}
                <div className="mt-1.5 min-h-[2.25rem] space-y-1.5">
                  {line("h-2.5 w-full opacity-90")}
                  {line("h-2.5 w-[85%] opacity-90")}
                </div>
              </div>
              <div className="mt-3 flex gap-2">
                {line("h-2.5 w-16")}
                {line("h-2.5 w-12 opacity-80")}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
