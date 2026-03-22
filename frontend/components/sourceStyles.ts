/**
 * Distinct, light badge styles per outlet (editorial chips).
 */
export function sourceBadgeClass(source: string | undefined): string {
  const s = (source || "").trim().toLowerCase();
  if (s.includes("cbc")) return "bg-red-50/90 text-red-900/95 ring-red-200/50";
  if (s.includes("ctv")) return "bg-sky-50/90 text-sky-900/95 ring-sky-200/50";
  if (s.includes("global")) return "bg-slate-50 text-slate-800 ring-slate-200/70";
  if (s.includes("national post")) return "bg-blue-50/90 text-blue-900/95 ring-blue-200/50";
  if (s.includes("toronto star")) return "bg-indigo-50/90 text-indigo-900/95 ring-indigo-200/50";
  if (s.includes("financial post")) return "bg-amber-50/90 text-amber-900/95 ring-amber-200/50";
  return "bg-zinc-50 text-zinc-800 ring-zinc-200/70";
}

/**
 * Badges on dark image overlays: frosted pill + subtle hue.
 */
export function sourceOverlayBadgeClass(source: string | undefined): string {
  const s = (source || "").trim().toLowerCase();
  if (s.includes("cbc")) return "bg-red-950/50 text-red-100 ring-red-300/40";
  if (s.includes("ctv")) return "bg-sky-950/45 text-sky-100 ring-sky-300/40";
  if (s.includes("global")) return "bg-slate-950/50 text-slate-100 ring-slate-300/40";
  if (s.includes("national post")) return "bg-blue-950/45 text-blue-100 ring-blue-300/40";
  if (s.includes("toronto star")) return "bg-indigo-950/45 text-indigo-100 ring-indigo-300/40";
  if (s.includes("financial post")) return "bg-amber-950/45 text-amber-100 ring-amber-300/40";
  return "bg-white/15 text-white ring-white/35";
}
