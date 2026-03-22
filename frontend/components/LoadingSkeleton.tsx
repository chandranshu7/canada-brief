export function LoadingSkeleton() {
  return (
    <div className="space-y-12">
      {/* Top stories block */}
      <div className="space-y-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-2">
            <div className="h-3 w-20 rounded-full bg-slate-200/90" />
            <div className="h-8 w-48 max-w-full rounded-lg bg-slate-200/80" />
            <div className="h-4 w-full max-w-md rounded bg-slate-100" />
          </div>
          <div className="h-4 w-28 rounded-full bg-slate-100" />
        </div>

        <div className="grid gap-4 sm:gap-5 lg:grid-cols-3">
          <div className="lg:col-span-2 lg:row-span-2">
            <div className="relative h-[min(420px,70vh)] overflow-hidden rounded-[1.35rem] bg-slate-100 ring-1 ring-slate-200/80">
              <div className="absolute inset-0 animate-shimmer bg-[linear-gradient(110deg,transparent_40%,rgba(255,255,255,0.5)_50%,transparent_60%)] bg-[length:200%_100%]" />
            </div>
          </div>
          <div className="flex flex-col gap-4 lg:col-span-1">
            {[1, 2].map((i) => (
              <div
                key={i}
                className="relative h-[220px] overflow-hidden rounded-[1.35rem] bg-slate-100 ring-1 ring-slate-200/80"
              >
                <div className="absolute inset-0 animate-shimmer bg-[linear-gradient(110deg,transparent_40%,rgba(255,255,255,0.45)_50%,transparent_60%)] bg-[length:200%_100%]" />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Feed block */}
      <div className="space-y-4">
        <div className="h-3 w-24 rounded-full bg-slate-200/80" />
        <div className="h-7 w-40 rounded-lg bg-slate-200/70" />
        <ul className="space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <li
              key={i}
              className="flex gap-4 rounded-[1.15rem] border border-slate-100 bg-white/80 p-4 sm:gap-5 sm:p-5"
            >
              <div className="relative aspect-[4/3] w-[6.75rem] shrink-0 overflow-hidden rounded-xl bg-slate-100 sm:w-[7.75rem]">
                <div className="absolute inset-0 animate-shimmer bg-[linear-gradient(110deg,transparent_40%,rgba(255,255,255,0.5)_50%,transparent_60%)] bg-[length:200%_100%]" />
              </div>
              <div className="flex-1 space-y-3 pt-1">
                <div className="h-3 w-24 rounded-full bg-slate-100" />
                <div className="h-5 w-full max-w-lg rounded-md bg-slate-100" />
                <div className="h-5 w-[85%] max-w-md rounded-md bg-slate-50" />
                <div className="h-3 w-1/3 rounded bg-slate-50" />
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
