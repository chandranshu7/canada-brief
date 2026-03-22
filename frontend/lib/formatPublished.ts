/**
 * Parse RSS / ISO / common backend date strings for display-only formatting.
 */

function tryParseMs(s: string): number | null {
  const t = Date.parse(s);
  return Number.isNaN(t) ? null : t;
}

/**
 * Returns a valid Date or null if the string cannot be parsed safely.
 */
export function parsePublishedDate(value: string | undefined): Date | null {
  const raw = (value ?? "").trim();
  if (!raw) return null;

  let ms = tryParseMs(raw);
  if (ms != null) return new Date(ms);

  // "Fri, 20 Mar 2026 18:40:32 +0000" — some engines need the weekday stripped
  const noWeekday = raw.replace(/^[A-Za-z]{3,9},\s*/i, "").trim();
  ms = tryParseMs(noWeekday);
  if (ms != null) return new Date(ms);

  // "20 Mar 2026 18:40:32 GMT"
  const spaced = raw.replace(/\sGMT\s*$/i, " UTC");
  ms = tryParseMs(spaced);
  if (ms != null) return new Date(ms);

  // "2026-03-20 18:40:32" → ISO-like
  if (/^\d{4}-\d{2}-\d{2}\s+\d/.test(raw)) {
    ms = tryParseMs(raw.replace(" ", "T"));
    if (ms != null) return new Date(ms);
  }

  return null;
}

function publishedStringLooksLikeTimeIncluded(raw: string): boolean {
  return (
    /\d{1,2}:\d{2}/.test(raw) ||
    /T\d{1,2}:/i.test(raw) ||
    /\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{1,2}:\d{2}/.test(raw)
  );
}

/**
 * Human-friendly published line for cards and spotlight.
 * - Date-only sources → "Mar 20, 2026"
 * - If the original string likely includes a time → "Mar 20, 2026 · 6:40 PM" (local)
 * If parsing fails, returns the original trimmed string (never throws).
 */
export function formatPublishedDisplay(value: string | undefined): string {
  const raw = (value ?? "").trim();
  if (!raw) return "";

  const d = parsePublishedDate(raw);
  if (!d || Number.isNaN(d.getTime())) return raw;

  const datePart = d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  if (publishedStringLooksLikeTimeIncluded(raw)) {
    const timePart = d.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
    });
    return `${datePart} · ${timePart}`;
  }

  return datePart;
}

/**
 * @deprecated Prefer {@link formatPublishedDisplay}. Same behavior now.
 */
export function formatPublishedShort(value: string | undefined): string {
  return formatPublishedDisplay(value);
}
