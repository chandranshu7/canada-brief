import type { ReactNode } from "react";

type SectionHeaderProps = {
  eyebrow: string;
  title: string;
  subtitle?: string;
  right?: ReactNode;
};

export function SectionHeader({
  eyebrow,
  title,
  subtitle,
  right,
}: SectionHeaderProps) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:mb-8 sm:flex-row sm:items-end sm:justify-between sm:gap-6">
      <div className="min-w-0 space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
          {eyebrow}
        </p>
        <h2 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-[1.75rem] sm:leading-none">
          {title}
        </h2>
        {subtitle && (
          <p className="max-w-xl text-sm leading-relaxed text-slate-500">{subtitle}</p>
        )}
      </div>
      {right && (
        <div className="shrink-0 text-right text-xs font-medium text-slate-400">
          {right}
        </div>
      )}
    </div>
  );
}
