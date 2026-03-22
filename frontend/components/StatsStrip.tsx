"use client";

type StatsStripProps = {
  totalArticles: number;
  topicCount: number;
  visibleCount: number;
};

export function StatsStrip({
  totalArticles,
  topicCount,
  visibleCount,
}: StatsStripProps) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3 rounded-2xl border border-slate-200/80 bg-white/60 px-5 py-4 text-center shadow-sm backdrop-blur-sm sm:justify-between sm:px-8 sm:text-left">
      <Stat label="In feed" value={String(totalArticles)} />
      <div className="hidden h-8 w-px bg-gradient-to-b from-transparent via-slate-200 to-transparent sm:block" />
      <Stat label="Topics" value={String(topicCount)} />
      <div className="hidden h-8 w-px bg-gradient-to-b from-transparent via-slate-200 to-transparent sm:block" />
      <Stat label="Showing" value={String(visibleCount)} highlight />
    </div>
  );
}

function Stat({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="min-w-[5.5rem]">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
        {label}
      </p>
      <p
        className={`mt-0.5 text-2xl font-semibold tabular-nums tracking-tight ${
          highlight ? "text-slate-900" : "text-slate-700"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
