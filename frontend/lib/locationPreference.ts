/**
 * Feed mode + structured Canada location (from `data/canadian_cities.json`).
 */

import rawDataset from "../data/canadian_cities.json";

export type FeedMode = "general" | "local";

export type CanadianCityRecord = {
  city: string;
  province: string;
  province_code: string;
  slug: string;
  lat: number;
  lon: number;
  population_rank?: number;
  strong_local_coverage?: boolean;
};

type DatasetFile = { version: number; cities: CanadianCityRecord[] };

const dataset = rawDataset as DatasetFile;

/** All cities in the bundled dataset (expandable). */
export const CANADIAN_CITY_LIST: CanadianCityRecord[] = dataset.cities;

export type CanadianCityOption = CanadianCityRecord & {
  /** Display name (usually same as city). */
  label: string;
};

export type LocationPreference = {
  city: string | null;
  province: string | null;
  province_code: string | null;
  slug: string | null;
  label: string;
};

const STORAGE_V2 = "canada_brief_prefs_v2";
const STORAGE_V1 = "canada_brief_location_v1";

export type AppPreferences = {
  feedMode: FeedMode;
  location: LocationPreference;
};

export const EMPTY_LOCATION: LocationPreference = {
  city: null,
  province: null,
  province_code: null,
  slug: null,
  label: "",
};

export const DEFAULT_APP_PREFERENCES: AppPreferences = {
  feedMode: "general",
  location: EMPTY_LOCATION,
};

function norm(s: string | null | undefined): string {
  return (s || "").trim().toLowerCase();
}

function findRecord(
  city: string | null | undefined,
  province: string | null | undefined,
): CanadianCityRecord | null {
  const c = norm(city);
  const p = norm(province);
  if (!c || !p) return null;
  for (const row of CANADIAN_CITY_LIST) {
    if (norm(row.city) === c && norm(row.province) === p) {
      return row;
    }
  }
  return null;
}

/** Enrich legacy stored prefs with province_code / slug when city+province match the dataset. */
export function enrichLocation(loc: LocationPreference): LocationPreference {
  if (!loc.city || !loc.province) return loc;
  const row = findRecord(loc.city, loc.province);
  if (!row) {
    return {
      ...loc,
      province_code: loc.province_code ?? null,
      slug: loc.slug ?? null,
      label: loc.label || loc.city,
    };
  }
  return {
    city: row.city,
    province: row.province,
    province_code: row.province_code,
    slug: row.slug,
    label: loc.label || row.city,
  };
}

function isValidLocationForLocal(loc: LocationPreference): boolean {
  return Boolean(loc.city && loc.province && findRecord(loc.city, loc.province));
}

function migrateFromV1(): AppPreferences | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(STORAGE_V1);
  if (!raw) return null;
  try {
    const o = JSON.parse(raw) as Partial<LocationPreference>;
    if (typeof o.label !== "string") return null;
    const city = o.city === null || typeof o.city === "string" ? o.city : null;
    const province =
      o.province === null || typeof o.province === "string" ? o.province : null;
    const loc: LocationPreference = enrichLocation({
      city,
      province,
      province_code: null,
      slug: null,
      label: o.label || "",
    });
    return {
      feedMode: isValidLocationForLocal(loc) ? "local" : "general",
      location: loc,
    };
  } catch {
    return null;
  }
}

function parseV2(raw: string | null): AppPreferences | null {
  if (!raw) return null;
  try {
    const o = JSON.parse(raw) as Partial<AppPreferences>;
    const mode =
      o.feedMode === "local" || o.feedMode === "general" ? o.feedMode : "general";
    const loc = o.location as Partial<LocationPreference> | undefined;
    if (!loc || typeof loc.label !== "string") return null;
    const location: LocationPreference = enrichLocation({
      city:
        loc.city === null || typeof loc.city === "string" ? loc.city : null,
      province:
        loc.province === null || typeof loc.province === "string"
          ? loc.province
          : null,
      province_code:
        loc.province_code === null || typeof loc.province_code === "string"
          ? loc.province_code
          : null,
      slug: loc.slug === null || typeof loc.slug === "string" ? loc.slug : null,
      label: loc.label,
    });
    return { feedMode: mode, location };
  } catch {
    return null;
  }
}

export function loadAppPreferences(): AppPreferences {
  if (typeof window === "undefined") return DEFAULT_APP_PREFERENCES;
  const v2 = parseV2(localStorage.getItem(STORAGE_V2));
  if (v2) return v2;
  const v1 = migrateFromV1();
  if (v1) return v1;
  return DEFAULT_APP_PREFERENCES;
}

export function saveAppPreferences(prefs: AppPreferences): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_V2, JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
}

/** Reset feed mode + location to defaults (same keys as normal prefs). */
export function resetFeedPreferencesToDefaults(): void {
  saveAppPreferences(DEFAULT_APP_PREFERENCES);
}

/** Stable key for refetching when mode or location changes. */
export function buildPreferenceKey(prefs: AppPreferences): string {
  const l = prefs.location;
  return `${prefs.feedMode}|${l.city ?? ""}|${l.province ?? ""}|${l.province_code ?? ""}|${l.slug ?? ""}|${l.label}`;
}

/**
 * Future: map Canadian postal FSA → city. Returns null until implemented.
 */
export function tryMatchPostalCode(_input: string): CanadianCityOption | null {
  return null;
}

function scoreMatch(
  q: string,
  c: CanadianCityRecord,
): number {
  const qn = q.trim().toLowerCase();
  if (!qn) return 0;
  const city = c.city.toLowerCase();
  const prov = c.province.toLowerCase();
  const provCode = c.province_code.toLowerCase();
  const hay = `${city} ${prov} ${provCode}`;
  if (
    !city.includes(qn) &&
    !prov.includes(qn) &&
    !provCode.includes(qn) &&
    !hay.includes(qn)
  ) {
    return -1;
  }
  let score = 0;
  if (city.startsWith(qn)) score += 100_000;
  else if (city.includes(qn)) score += 50_000;
  if (prov.startsWith(qn)) score += 30_000;
  else if (prov.includes(qn)) score += 15_000;
  if (provCode.startsWith(qn)) score += 25_000;
  const pr = c.population_rank ?? 999;
  score += Math.max(0, 500 - pr);
  score -= city.charCodeAt(0) / 1000;
  return score;
}

/** Search all bundled cities; sort by prefix match, size, then A–Z. */
export function filterCitySuggestions(
  query: string,
  limit = 10,
): CanadianCityOption[] {
  const q = query.trim().toLowerCase();
  if (!q) {
    const rows = [...CANADIAN_CITY_LIST].sort((a, b) => {
      const pa = a.population_rank ?? 999;
      const pb = b.population_rank ?? 999;
      if (pa !== pb) return pa - pb;
      return a.city.localeCompare(b.city, "en-CA");
    });
    return rows.slice(0, limit).map((row) => ({ ...row, label: row.city }));
  }
  const scored: { row: CanadianCityRecord; s: number }[] = [];
  for (const row of CANADIAN_CITY_LIST) {
    const s = scoreMatch(q, row);
    if (s >= 0) {
      scored.push({ row, s });
    }
  }
  scored.sort((a, b) => {
    if (b.s !== a.s) return b.s - a.s;
    return a.row.city.localeCompare(b.row.city, "en-CA");
  });
  return scored.slice(0, limit).map(({ row }) => ({
    ...row,
    label: row.city,
  }));
}

/** True when city has curated metro feeds in the dataset (for future UX messaging). */
export function hasStrongLocalCoverage(
  city: string | null | undefined,
  province: string | null | undefined,
): boolean {
  const r = findRecord(city, province);
  return Boolean(r?.strong_local_coverage);
}
