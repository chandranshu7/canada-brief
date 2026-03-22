/** Single-story loading state — matches one large hero card. */
export function LoadingSkeleton() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-5">
      <div className="overflow-hidden rounded-2xl border border-slate-100 bg-white/90 shadow-premium ring-1 ring-slate-900/[0.03]">
        <div
          className="relative isolate aspect-[21/10] w-full max-w-full overflow-hidden bg-slate-100 sm:aspect-[21/9]"
          style={{ position: "relative" }}
        >
          <div className="absolute inset-0 z-[1] animate-shimmer bg-[linear-gradient(110deg,transparent_40%,rgba(255,255,255,0.5)_50%,transparent_60%)] bg-[length:200%_100%]" />
        </div>
        <div className="space-y-4 px-6 py-7 sm:space-y-5 sm:px-9 sm:py-9">
          <div className="flex flex-wrap gap-1.5">
            <div className="h-5 w-20 rounded-md bg-slate-100" />
            <div className="h-5 w-16 rounded-md bg-slate-100" />
          </div>
          <div className="h-9 w-full max-w-xl rounded-lg bg-slate-100" />
          <div className="h-4 w-full max-w-2xl rounded bg-slate-100" />
          <div className="h-4 w-[92%] max-w-2xl rounded bg-slate-50" />
          <div className="h-3.5 w-28 rounded bg-slate-50" />
          <div className="h-11 w-full max-w-xs rounded-lg bg-slate-200/70" />
        </div>
      </div>
    </div>
  );
}
