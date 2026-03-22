/**
 * Hero image URL helpers: optional weserv proxy when the source looks like a tiny thumbnail.
 */

const WESERV_BASE = "https://images.weserv.nl/";

/**
 * Heuristic: RSS/CDN URLs that often resolve to small bitmaps.
 * Full-size hero URLs typically avoid these patterns.
 */
export function isLikelyLowResImageUrl(url: string): boolean {
  const u = url.trim().toLowerCase();
  if (!u) return false;
  if (/[?&]w=\d{1,3}(?:&|$)/.test(u)) return true;
  if (/[?&]width=\d{1,3}(?:&|$)/.test(u)) return true;
  if (/[?&]h=\d{1,3}(?:&|$)/.test(u)) return true;
  if (/thumb|thumbnail|\/small\/|-\d{2,3}x\d{2,3}\./.test(u)) return true;
  return false;
}

export type HeroImageDisplay = {
  src: string;
  /** True when using images.weserv.nl (allowed in next.config remotePatterns). */
  viaProxy: boolean;
};

/**
 * Prefer original URL for crisp full-size assets; upscale questionable thumbs via weserv.
 */
export function getHeroImageDisplay(originalUrl: string): HeroImageDisplay {
  const trimmed = originalUrl.trim();
  if (!trimmed) {
    return { src: "", viaProxy: false };
  }
  if (isLikelyLowResImageUrl(trimmed)) {
    const encoded = encodeURIComponent(trimmed);
    return {
      src: `${WESERV_BASE}?url=${encoded}&w=1200&q=90&fit=cover`,
      viaProxy: true,
    };
  }
  return { src: trimmed, viaProxy: false };
}
