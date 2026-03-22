export function categoryBadgeClass(category: string | undefined): string {
  if (!category) return "bg-slate-50 text-slate-700 ring-slate-200/60";
  const c = category.toLowerCase();
  if (c.includes("politics"))
    return "bg-red-50/90 text-red-800/95 ring-red-200/50";
  if (c.includes("crime")) return "bg-blue-50/90 text-blue-800/95 ring-blue-200/50";
  if (c.includes("sports"))
    return "bg-emerald-50/90 text-emerald-800/95 ring-emerald-200/50";
  if (c.includes("business"))
    return "bg-violet-50/90 text-violet-800/95 ring-violet-200/50";
  if (c.includes("health"))
    return "bg-green-50/90 text-green-800/95 ring-green-200/50";
  if (c.includes("world")) return "bg-sky-50/90 text-sky-800/95 ring-sky-200/50";
  if (c.includes("canada"))
    return "bg-orange-50/90 text-orange-800/95 ring-orange-200/50";
  return "bg-slate-50 text-slate-700 ring-slate-200/60";
}
