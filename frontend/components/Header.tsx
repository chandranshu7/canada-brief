import { IconRss } from "./icons";

export function Header() {
  return (
    <header className="relative overflow-hidden border-b border-slate-200/60 bg-white/40">
      {/* Layered ambient background */}
      <div
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_90%_60%_at_50%_-30%,rgba(99,102,241,0.12),transparent)]"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute -left-[20%] top-0 h-[min(520px,80vw)] w-[min(520px,90vw)] rounded-full bg-gradient-to-br from-rose-100/50 via-orange-50/30 to-transparent blur-3xl"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute -right-[15%] top-8 h-[min(400px,70vw)] w-[min(440px,85vw)] rounded-full bg-gradient-to-bl from-sky-100/45 via-violet-50/25 to-transparent blur-3xl"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-slate-200/80 to-transparent"
        aria-hidden
      />

      <div className="relative mx-auto max-w-5xl px-4 pb-8 pt-8 sm:px-6 sm:pb-10 sm:pt-10 lg:px-8">
        <div className="max-w-2xl motion-safe:animate-fade-in-up">
          <div className="inline-flex items-center gap-2 rounded-full border border-slate-200/90 bg-white/70 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-600 shadow-sm ring-1 ring-white/80 backdrop-blur-md sm:text-xs">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-gradient-to-br from-red-500 to-rose-600 text-white shadow-sm">
              <IconRss className="h-3 w-3" />
            </span>
            Live Canadian feed
          </div>

          <h1 className="mt-5 text-[2rem] font-semibold leading-[1.08] tracking-tight text-slate-950 sm:text-[2.65rem] sm:leading-[1.05]">
            Canada Brief
          </h1>
          <p className="mt-3 max-w-lg text-[15px] leading-relaxed text-slate-600 sm:text-base sm:leading-relaxed">
            Fast, snackable Canadian headlines — curated for clarity, built for
            busy readers.
          </p>
        </div>
      </div>
    </header>
  );
}
