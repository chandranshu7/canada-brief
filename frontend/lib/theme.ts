/**
 * Theme preference (stored) vs resolved paint theme (dark | light only).
 */

export const THEME_STORAGE_KEY = "canada-brief-theme";

export type ThemePreference = "dark" | "light" | "system";

export type ResolvedTheme = "dark" | "light";

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference === "dark") return "dark";
  if (preference === "light") return "light";
  if (typeof window === "undefined") {
    return "dark";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function loadThemePreference(): ThemePreference {
  if (typeof window === "undefined") return "system";
  try {
    const v = localStorage.getItem(THEME_STORAGE_KEY);
    if (v === "dark" || v === "light" || v === "system") return v;
  } catch {
    /* ignore */
  }
  return "system";
}

export function saveThemePreference(preference: ThemePreference): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    /* ignore */
  }
}

/** Apply resolved theme + preference markers on <html> (for CSS + debugging). */
export function applyThemeToDocument(preference: ThemePreference): void {
  if (typeof document === "undefined") return;
  const resolved = resolveTheme(preference);
  document.documentElement.setAttribute("data-theme", resolved);
  document.documentElement.setAttribute("data-theme-preference", preference);
}

/**
 * Inline script for <head>: must stay in sync with loadThemePreference / resolveTheme.
 * Runs before paint to avoid flash.
 */
export function themeInitScript(): string {
  const k = THEME_STORAGE_KEY;
  return `!function(){try{var k='${k}';var v=localStorage.getItem(k);var p='system';if(v==='dark'||v==='light'||v==='system')p=v;var r=p==='dark'?'dark':p==='light'?'light':window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';document.documentElement.setAttribute('data-theme',r);document.documentElement.setAttribute('data-theme-preference',p);}catch(e){document.documentElement.setAttribute('data-theme','dark');document.documentElement.setAttribute('data-theme-preference','system');}}();`;
}
