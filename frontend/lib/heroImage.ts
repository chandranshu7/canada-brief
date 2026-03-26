/**
 * Hero image URL helpers: optional weserv proxy when the source looks like a tiny thumbnail.
 */

const WESERV_BASE = "https://images.weserv.nl/";

function shouldProxyImageUrl(url: string): boolean {
  const u = url.trim().toLowerCase();
  if (!u) return false;
  return (
    u.includes("googleusercontent.com") ||
    u.includes("ggpht.com") ||
    u.includes("news.google.com")
  );
}

/**
 * Extract YouTube video ID from various YouTube URL formats.
 */
function extractYoutubeId(url: string): string | null {
  const patterns = [
    /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]+)/,
    /youtube\.com\/v\/([a-zA-Z0-9_-]+)/,
  ];
  
  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match && match[1]) {
      return match[1];
    }
  }
  return null;
}

/**
 * Extract Vimeo video ID from Vimeo URL.
 */
function extractVimeoId(url: string): string | null {
  const match = url.match(/vimeo\.com\/(\d+)/);
  return match ? match[1] : null;
}

/**
 * Get thumbnail URL for a video platform URL.
 * Returns thumbnail URL or empty string if not a recognized video platform.
 */
export function getVideoThumbnailUrl(videoUrl: string): string {
  if (!videoUrl) return "";
  
  const u = videoUrl.toLowerCase();
  
  // YouTube
  if (u.includes("youtube.com") || u.includes("youtu.be")) {
    const videoId = extractYoutubeId(videoUrl);
    if (videoId) {
      // hqdefault = high quality (480x360)
      return `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;
    }
  }
  
  // Vimeo
  if (u.includes("vimeo.com")) {
    const videoId = extractVimeoId(videoUrl);
    if (videoId) {
      return `https://i.vimeocdn.com/video/${videoId}.jpg`;
    }
  }
  
  return "";
}

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

/**
 * Heuristic: reject common non-editorial image assets (logos/icons/sprites) for hero slots.
 */
export function isLikelyNonEditorialImageUrl(url: string): boolean {
  const u = url.trim().toLowerCase();
  if (!u) return false;
  if (/gstatic\.com\/images\/branding/.test(u)) return true;
  if (/\/favicon\.|apple-touch-icon|sprite|logo\.(svg|png|webp|jpg)/.test(u)) {
    return true;
  }
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
  if (isLikelyNonEditorialImageUrl(trimmed)) {
    return { src: "", viaProxy: false };
  }
  if (shouldProxyImageUrl(trimmed) || isLikelyLowResImageUrl(trimmed)) {
    const encoded = encodeURIComponent(trimmed);
    return {
      src: `${WESERV_BASE}?url=${encoded}&w=1200&q=90&fit=cover`,
      viaProxy: true,
    };
  }
  return { src: trimmed, viaProxy: false };
}
