import type { Article } from "./types";

export function filterArticles(
  articles: Article[],
  category: string,
  query: string,
  source: string = "All",
): Article[] {
  const q = query.trim().toLowerCase();
  const cat = category === "All" ? null : category;
  const src = source === "All" ? null : source.trim();

  return articles.filter((a) => {
    if (cat && (a.category ?? "") !== cat) return false;
    if (src) {
      const outlets = a.sources?.length ? a.sources : [a.source];
      if (!outlets.some((x) => (x || "").trim() === src)) return false;
    }
    if (!q) return true;
    const hay = [
      a.title,
      a.summary,
      a.category,
      a.region,
      a.source,
      ...(a.sources ?? []),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  });
}

export function uniqueCategories(articles: Article[]): string[] {
  const set = new Set<string>();
  for (const a of articles) {
    if (a.category) set.add(a.category);
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

export function uniqueSources(articles: Article[]): string[] {
  const set = new Set<string>();
  for (const a of articles) {
    if (a.sources?.length) {
      for (const s of a.sources) {
        const t = (s || "").trim();
        if (t) set.add(t);
      }
    } else {
      const s = (a.source || "").trim();
      if (s) set.add(s);
    }
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}
