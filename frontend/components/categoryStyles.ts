export function categoryBadgeClass(category: string | undefined): string {
  if (!category) return "bg-slate-100 text-slate-700 ring-slate-200/80";
  const c = category.toLowerCase();
  if (c.includes("politics"))
    return "bg-red-50 text-red-800 ring-red-200/80";
  if (c.includes("crime")) return "bg-blue-50 text-blue-800 ring-blue-200/80";
  if (c.includes("sports"))
    return "bg-emerald-50 text-emerald-800 ring-emerald-200/80";
  if (c.includes("business"))
    return "bg-violet-50 text-violet-800 ring-violet-200/80";
  if (c.includes("health"))
    return "bg-green-50 text-green-800 ring-green-200/80";
  if (c.includes("world")) return "bg-sky-50 text-sky-800 ring-sky-200/80";
  if (c.includes("canada"))
    return "bg-orange-50 text-orange-800 ring-orange-200/80";
  return "bg-slate-100 text-slate-700 ring-slate-200/80";
}
