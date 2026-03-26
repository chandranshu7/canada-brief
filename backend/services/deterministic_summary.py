"""
Non-AI summary text for Canada Brief: RSS / HTML excerpt → short display string.

summary_source values: rss, html, content, title_fallback, default
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Dict, Optional, Tuple

from bs4 import BeautifulSoup

# Target length for card-style summaries (characters).
_SUMMARY_MIN_LEN = 180
_SUMMARY_MAX_LEN = 220

DEFAULT_SUMMARY_FALLBACK = "Read the full story for more details."


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _normalize_summary_tail(text: str) -> str:
    """Collapse noisy trailing punctuation (e.g., '.....') to a single terminal mark."""
    s = (text or "").strip()
    if not s:
        return ""
    # Normalize unicode ellipsis and long dot runs.
    s = s.replace("...", "…")
    s = re.sub(r"[.]{2,}$", "…", s)
    s = re.sub(r"[.!?]{2,}$", ".", s)
    if s[-1] not in ".!?…":
        s += "."
    return s


def clamp_summary_display(text: str, max_len: int = _SUMMARY_MAX_LEN) -> str:
    """
    Strip noise, collapse whitespace, clamp to max_len on a word boundary (no broken words).
    """
    s = (text or "").strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= max_len:
        return _normalize_summary_tail(s)
    cut = s[:max_len]
    sp = cut.rfind(" ")
    if sp > max_len // 2:
        cut = cut[:sp]
    else:
        cut = cut.rstrip()
    return _normalize_summary_tail(cut.rstrip(".,; ") + "…")


def _plain_from_markup(raw: str) -> str:
    if not (raw or "").strip():
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    t = soup.get_text(" ", strip=True)
    t = html_lib.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _looks_like_html(s: str) -> bool:
    return "<" in s and ">" in s


def _first_two_sentences_or_clamp(plain: str) -> str:
    parts = _split_sentences(plain)
    if len(parts) >= 2:
        joined = f"{parts[0]} {parts[1]}"
    elif parts:
        joined = parts[0]
    else:
        joined = plain
    out = clamp_summary_display(joined)
    if len(out) < _SUMMARY_MIN_LEN and len(plain) > len(out):
        out = clamp_summary_display(plain)
    return out


def _two_sentence_from_raw_excerpt(raw: str, _title: str) -> str:
    """First two informative sentences from RSS HTML/text (no AI)."""
    raw = (raw or "").strip()
    if len(raw) < 40:
        return ""
    plain = re.sub(r"<[^>]+>", " ", raw)
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) < 40:
        return ""
    chunk = plain[:2000]
    parts = re.split(r"(?<=[.!?])\s+", chunk)
    parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 20]
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1]}"
    words = chunk.split()
    if len(words) < 24:
        return (chunk[:400].strip() + ".") if chunk else ""
    mid = min(len(words) // 2, 28)
    return f"{' '.join(words[:mid])} {' '.join(words[mid : mid + 28])}"


def deterministic_summary_for_article(
    title: str,
    rss_excerpt: Optional[str],
) -> Tuple[str, str]:
    """
    Build summary from RSS/body text only. Returns (summary, summary_source).

    Priority:
      1. Plain text from RSS description / summary (after HTML strip) — rss or html
      2. First 1–2 sentences from excerpt body — content
      3. Truncated title — title_fallback
      4. Default string — default
    """
    t = (title or "").strip() or "News update."
    ex = (rss_excerpt or "").strip()

    if ex:
        had_html = _looks_like_html(ex)
        plain = _plain_from_markup(ex)
        if len(plain) >= 40:
            out = _first_two_sentences_or_clamp(plain)
            if out:
                src = "html" if had_html else "rss"
                return out, src
        if len(plain) >= 15:
            out = clamp_summary_display(plain)
            if out:
                src = "html" if had_html else "rss"
                return out, src

        if len(ex) >= 40:
            fb = _two_sentence_from_raw_excerpt(ex, t)
            if fb:
                out = clamp_summary_display(fb)
                if out:
                    return out, "content"

    tit = clamp_summary_display(t, max_len=_SUMMARY_MAX_LEN)
    if tit:
        return tit, "title_fallback"
    return DEFAULT_SUMMARY_FALLBACK, "default"


def assign_deterministic_summary_to_row(row: Dict) -> None:
    """Set summary + summary_status on a story dict before DB save."""
    title = row.get("title") or ""
    ex = (row.get("rss_excerpt") or "").strip() or None
    text, src = deterministic_summary_for_article(title, ex)
    row["summary"] = text
    row["summary_status"] = "ready"
    tid = row.get("id")
    preview = (text[:100] + "…") if len(text) > 100 else text
    print(
        f"[summary] ingest summary_source={src} id={tid!r} "
        f"title={(title or '')[:72]!r} preview={preview!r}"
    )
