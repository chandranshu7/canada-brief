import { CANADIAN_CITY_LIST } from "./locationPreference";
import type { LocationPreference } from "./locationPreference";

/** City name → province (from bundled dataset + territories). */
const CITY_TO_PROVINCE: Record<string, string> = (() => {
  const m: Record<string, string> = {};
  for (const row of CANADIAN_CITY_LIST) {
    m[row.city] = row.province;
  }
  return m;
})();

const PROVINCES = new Set([
  "Ontario",
  "Quebec",
  "Alberta",
  "British Columbia",
  "Manitoba",
  "Saskatchewan",
  "Nova Scotia",
  "New Brunswick",
  "Prince Edward Island",
  "Newfoundland and Labrador",
  "Yukon",
  "Northwest Territories",
  "Nunavut",
]);

function articleProvince(region: string): string | null {
  const r = region.trim();
  if (!r) return null;
  if (PROVINCES.has(r)) return r;
  return CITY_TO_PROVINCE[r] ?? null;
}

/**
 * Subtle context line for the hero (e.g. "Local to Toronto", "Ontario", "Canada").
 */
export function buildStoryLocationContext(
  region: string | undefined,
  pref: LocationPreference,
): string | null {
  const r = (region || "").trim();
  if (!pref.city && !pref.province) {
    if (r === "Canada") return "Canada";
    return r || null;
  }
  if (pref.city && r.toLowerCase() === pref.city.toLowerCase()) {
    return `Local to ${pref.city}`;
  }
  const ap = articleProvince(r);
  if (pref.province && ap && ap === pref.province) {
    return pref.province;
  }
  if (r === "Canada") return "Canada";
  return r || null;
}
