export function categoryBadgeClass(category: string | undefined): string {
  if (!category) return "bg-slate-500/15 text-slate-200 ring-slate-300/25";
  const c = category.toLowerCase();
  if (c.includes("politics"))
    return "bg-rose-500/18 text-rose-100 ring-rose-300/40";
  if (c.includes("crime")) return "bg-blue-500/18 text-blue-100 ring-blue-300/40";
  if (c.includes("sports"))
    return "bg-emerald-500/18 text-emerald-100 ring-emerald-300/40";
  if (c.includes("business"))
    return "bg-violet-500/18 text-violet-100 ring-violet-300/40";
  if (c.includes("health"))
    return "bg-green-500/18 text-green-100 ring-green-300/40";
  if (c.includes("technology") || c.includes("tech"))
    return "bg-cyan-500/18 text-cyan-100 ring-cyan-300/40";
  if (c.includes("entertainment"))
    return "bg-fuchsia-500/18 text-fuchsia-100 ring-fuchsia-300/40";
  if (c.includes("world")) return "bg-sky-500/18 text-sky-100 ring-sky-300/40";
  if (c.includes("canada"))
    return "bg-amber-500/18 text-amber-100 ring-amber-300/40";
  return "bg-slate-500/15 text-slate-200 ring-slate-300/25";
}
