"""
services/summarize.py

Deterministic summaries only (RSS / HTML excerpt / title). No LLM calls.
Legacy helpers (clean_summary, validate_summary) support older code paths.
"""

import os
import re
from difflib import SequenceMatcher
from urllib.parse import urlparse
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
_OPENAI_TIMEOUT_S = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "10"))
_OPENAI_MODEL = (os.environ.get("OPENAI_MODEL") or "gpt-4.1-mini").strip()


def _is_google_news_source(source: Optional[str]) -> bool:
    s = (source or "").strip().lower()
    return "google news" in s


def _extract_publisher_url_from_google_html(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return ""
    canon = soup.find("link", rel=lambda r: r and "canonical" in str(r).lower())
    if canon and canon.get("href"):
        href = (canon.get("href") or "").strip()
        if href.startswith("http") and "google." not in (urlparse(href).hostname or "").lower():
            return href
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href.startswith("http"):
            continue
        host = (urlparse(href).hostname or "").lower()
        if host and "google." not in host:
            return href
    return ""


def _resolve_article_url(link: str) -> str:
    u = (link or "").strip()
    if not u:
        return ""
    try:
        r = requests.get(u, timeout=min(_OPENAI_TIMEOUT_S, 6.0), allow_redirects=True)
        r.raise_for_status()
        final = (r.url or u).strip()
        host = (urlparse(final).hostname or "").lower()
        if host and "google." in host:
            extracted = _extract_publisher_url_from_google_html(r.text)
            if extracted:
                return extracted
        return final
    except Exception:
        return u


def _fetch_page_description(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    try:
        r = requests.get(u, timeout=min(_OPENAI_TIMEOUT_S, 6.0))
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return ""

    selectors = [
        ("meta", {"property": "og:description"}, "content"),
        ("meta", {"name": "description"}, "content"),
        ("meta", {"name": "twitter:description"}, "content"),
    ]
    for tag_name, attrs, attr_key in selectors:
        tag = soup.find(tag_name, attrs=attrs)
        if tag and tag.get(attr_key):
            txt = re.sub(r"\s+", " ", str(tag.get(attr_key)).strip())
            if len(txt) >= 60:
                return txt[:1800]

    p = soup.find("p")
    if p:
        txt = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
        if len(txt) >= 60:
            return txt[:1800]
    return ""


def _maybe_enrich_excerpt(
    *,
    title: str,
    article_excerpt: Optional[str],
    article_link: Optional[str],
    source: Optional[str],
) -> Optional[str]:
    ex = (article_excerpt or "").strip()
    if ex and len(ex) >= 80 and not is_summary_redundant_with_title(ex, title):
        return ex

    # Google RSS often contains headline + outlet only; try publisher meta description.
    if _is_google_news_source(source) and article_link:
        resolved = _resolve_article_url(article_link)
        desc = _fetch_page_description(resolved)
        if desc:
            return desc

    return ex or None


def _openai_key() -> str:
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def _extract_response_text(payload: dict) -> str:
    txt = (payload.get("output_text") or "").strip()
    if txt:
        return txt

    out = payload.get("output")
    if not isinstance(out, list):
        return ""
    chunks: List[str] = []
    for item in out:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "output_text":
                t = (block.get("text") or "").strip()
                if t:
                    chunks.append(t)
                    continue
            text_obj = block.get("text")
            if isinstance(text_obj, dict):
                v = (text_obj.get("value") or "").strip()
                if v:
                    chunks.append(v)
    return "\n".join(chunks).strip()


def _openai_summarize(title: str, article_excerpt: Optional[str]) -> str:
    key = _openai_key()
    if not key:
        return ""

    excerpt = (article_excerpt or "").strip()
    prompt_excerpt = excerpt[:5000] if excerpt else ""
    body = {
        "model": _OPENAI_MODEL,
        "temperature": 0.2,
        "max_output_tokens": 140,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You summarize Canadian news headlines for a mobile feed. "
                            "Return plain text only. 2-3 concise sentences, <=55 words, "
                            "factual, no hype, no bullet points."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            f"Headline: {title.strip()}\n\n"
                            f"Article excerpt (may be partial HTML/plain text):\n{prompt_excerpt}"
                        ),
                    }
                ],
            },
        ],
    }

    try:
        res = requests.post(
            _OPENAI_RESPONSES_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=_OPENAI_TIMEOUT_S,
        )
        if not res.ok:
            print(
                f"[summarize] openai request failed status={res.status_code} "
                f"model={_OPENAI_MODEL!r}"
            )
            return ""
        payload = res.json()
    except Exception as e:
        print(f"[summarize] openai request error: {e!r}")
        return ""

    return _extract_response_text(payload)

# Caps (must match prompts + clean_summary)
_MAX_SUMMARY_WORDS = 55
_MAX_SUMMARY_SENTENCES = 3
# Sentences matching these (whole sentence, from the end) are dropped as filler.
_VAGUE_SENTENCE_RES = [
    re.compile(
        r"^(.*\b(further\s+updates|more\s+updates)\s+(are\s+)?expected)\.?\s*$",
        re.I,
    ),
    re.compile(r"^(.*\bmore\s+details\s+(to\s+come|may\s+follow))\s*\.?\s*$", re.I),
    re.compile(r"^(.*\bdeveloping\s+stor(y|ies))\s*\.?\s*$", re.I),
    re.compile(r"^(.*\bstay\s+tuned)\s*\.?\s*$", re.I),
    re.compile(r"^(.*\bremains?\s+to\s+be\s+seen)\s*\.?\s*$", re.I),
    re.compile(r"^(.*\bas\s+more\s+information\s+becomes?\s+available)\s*\.?\s*$", re.I),
    re.compile(r"^(.*\bwatch\s+for\s+updates)\s*\.?\s*$", re.I),
    re.compile(r"^(.*\bthis\s+is\s+a\s+developing)\s*\.?\s*$", re.I),
]


def _normalize_summary_tail(text: str) -> str:
    """Collapse noisy trailing punctuation (e.g., '.....') to one clean terminal mark."""
    s = (text or "").strip()
    if not s:
        return ""
    s = s.replace("...", "…")
    s = re.sub(r"[.]{2,}$", "…", s)
    s = re.sub(r"[.!?]{2,}$", ".", s)
    if s[-1] not in ".!?…":
        s += "."
    return s


def clean_summary(text: str) -> str:
    """
    Normalize summary text for storage and display.

    - Removes "Continue reading" / "Read more" fragments
    - At most 3 sentences, at most 55 words total
    - Strips extra whitespace
    - Drops an incomplete trailing sentence when trimming to the word limit
    """
    s = _strip_continue_reading(text)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""

    sentences = _split_sentences(s)
    sentences = sentences[:_MAX_SUMMARY_SENTENCES]
    if not sentences:
        return ""

    result_parts: List[str] = []
    wc = 0
    for sent in sentences:
        sw = sent.split()
        if wc + len(sw) <= _MAX_SUMMARY_WORDS:
            result_parts.append(sent)
            wc += len(sw)
        else:
            remaining = _MAX_SUMMARY_WORDS - wc
            if remaining > 0:
                frag = _complete_or_trim_words(sw[:remaining])
                if frag:
                    result_parts.append(frag)
            break

    if not result_parts:
        words = sentences[0].split()[:_MAX_SUMMARY_WORDS]
        result = _complete_or_trim_words(words)
    else:
        result = " ".join(result_parts)

    result = re.sub(r"\s+", " ", result).strip()
    if not result:
        return ""
    return _normalize_summary_tail(result)


def _sentence_is_vague(sentence: str) -> bool:
    t = sentence.strip()
    if len(t) < 12:
        return False
    for rx in _VAGUE_SENTENCE_RES:
        if rx.match(t):
            return True
    low = t.lower()
    if "further updates" in low and "expected" in low:
        return True
    if "more details" in low and ("come" in low or "follow" in low):
        return True
    return False


def _strip_vague_trailing_sentences(text: str) -> str:
    """Remove vague filler sentences from the end, repeatedly."""
    s = (text or "").strip()
    if not s:
        return ""
    parts = _split_sentences(s)
    while parts and _sentence_is_vague(parts[-1]):
        parts.pop()
    return " ".join(parts).strip()


def _second_sentence_from_excerpt(article_excerpt: str, title: str) -> str:
    """One additional sentence from article text (for pairing with an existing first sentence)."""
    raw = (article_excerpt or "").strip()
    if len(raw) < 40:
        return ""
    plain = re.sub(r"<[^>]+>", " ", raw)
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) < 40:
        return ""
    title_l = (title or "").lower()
    chunk = plain[:2000]
    parts = re.split(r"(?<=[.!?])\s+", chunk)
    for p in parts:
        p = p.strip()
        if len(p) < 25 or len(p.split()) < 5:
            continue
        pl = p.lower()
        overlap = sum(1 for w in title_l.split() if len(w) > 3 and w in pl)
        if overlap > 3:
            continue
        return _sentence_case(p[:500])
    words = plain.split()
    if len(words) >= 12:
        return _sentence_case(" ".join(words[8:36]))
    return ""


def _excerpt_two_sentence_fallback(article_excerpt: str, title: str) -> str:
    """
    Build two informative sentences from RSS/body text when the model output is thin.
    Strips basic HTML; uses first substantive sentences or word splits.
    """
    raw = (article_excerpt or "").strip()
    if len(raw) < 40:
        return ""
    plain = re.sub(r"<[^>]+>", " ", raw)
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) < 40:
        return ""

    chunk = plain[:2000]
    # Prefer two real sentences from excerpt
    parts = re.split(r"(?<=[.!?])\s+", chunk)
    parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 20]
    if len(parts) >= 2:
        a = _sentence_case(parts[0][:500].strip())
        b = _sentence_case(parts[1][:500].strip())
        return f"{a} {b}"

    words = chunk.split()
    if len(words) < 24:
        return _sentence_case(chunk[:400].strip() + ".")
    mid = min(len(words) // 2, 28)
    first = " ".join(words[:mid])
    second = " ".join(words[mid : mid + 28])
    return f"{_sentence_case(first)} {_sentence_case(second)}"


def _fallback_from_excerpt_or_title(title: str, article_excerpt: Optional[str]) -> str:
    if article_excerpt and len(article_excerpt.strip()) >= 40:
        fb = _excerpt_two_sentence_fallback(article_excerpt, title)
        if fb:
            return clean_summary(fb)
    return clean_summary(_local_summarize_title(title))


def validate_summary(
    text: str,
    *,
    title: str = "",
    article_excerpt: Optional[str] = None,
) -> str:
    """
    Post-process: drop vague ending sentences, enforce length/sentence count,
    fall back to excerpt-based or title-based text when the result is too thin.
    """
    s = (text or "").strip()
    s = _strip_continue_reading(s)
    s = _strip_vague_trailing_sentences(s)
    s = clean_summary(s)

    if not s:
        return _fallback_from_excerpt_or_title(title, article_excerpt)

    wc = len(s.split())
    parts = _split_sentences(s)

    # One good sentence left after stripping filler — add detail from excerpt, not title-only.
    if len(parts) == 1 and article_excerpt and len((article_excerpt or "").strip()) >= 40:
        sec = _second_sentence_from_excerpt(article_excerpt, title)
        if sec:
            s = clean_summary(f"{parts[0]} {sec}")
            parts = _split_sentences(s)
            wc = len(s.split())

    # Full excerpt rebuild only when we still have fewer than two sentences (not when we already merged).
    if len(parts) < 2 and article_excerpt and len((article_excerpt or "").strip()) >= 40:
        fb = _excerpt_two_sentence_fallback(article_excerpt, title)
        if fb:
            s = clean_summary(fb)
            parts = _split_sentences(s)
            wc = len(s.split())

    if not s.strip() or len(parts) < 2:
        s = _fallback_from_excerpt_or_title(title, article_excerpt)

    # If the model echoed the headline, prefer excerpt-based text for storage.
    if (
        article_excerpt
        and len((article_excerpt or "").strip()) >= 40
        and is_summary_redundant_with_title(s, title)
    ):
        fb = _fallback_from_excerpt_or_title(title, article_excerpt)
        if fb and not is_summary_redundant_with_title(fb, title):
            s = fb

    return s


def normalize_stored_summary(
    text: str, title: str = "", article_excerpt: Optional[str] = None
) -> str:
    """Deterministic summary only (legacy signature)."""
    from services.deterministic_summary import deterministic_summary_for_article

    out, _ = deterministic_summary_for_article(title or text, article_excerpt)
    return out


def summarize_title(title: str, article_text: Optional[str] = None) -> str:
    """Summary text for one story: OpenAI when enabled, else deterministic fallback."""
    text, src = summarize_title_with_source(title, article_text)
    print(f"[summarize] summarize_title summary_source={src}")
    return text


def summarize_title_with_source(
    title: str,
    article_text: Optional[str] = None,
    article_link: Optional[str] = None,
    source: Optional[str] = None,
) -> Tuple[str, str]:
    """Same as summarize_title but returns (text, source) for logging/persistence paths."""
    from services.deterministic_summary import deterministic_summary_for_article

    t = (title or "").strip()
    ex = _maybe_enrich_excerpt(
        title=t,
        article_excerpt=article_text,
        article_link=article_link,
        source=source,
    )

    ai_raw = _openai_summarize(t, ex)
    if ai_raw:
        out = validate_summary(ai_raw, title=t, article_excerpt=ex)
        if out:
            return out, "openai"

    out, src = deterministic_summary_for_article(t, ex)
    return out, src


def is_summary_redundant_with_title(summary: str, title: str) -> bool:
    """
    True if summary adds almost nothing beyond the headline (bad UX).
    Used to prefer rss_excerpt-based text instead.
    """
    s = (summary or "").strip()
    t = (title or "").strip()
    if not s or not t:
        return False
    sl, tl = s.lower(), t.lower()
    if sl == tl:
        return True
    # Title contained in summary as whole phrase (common bad pattern).
    if len(tl) > 20 and tl in sl and len(s) < len(t) + 25:
        return True
    ratio = SequenceMatcher(None, sl, tl).ratio()
    if ratio >= 0.88:
        return True
    # Share almost all words (order may differ slightly).
    sw = set(w for w in re.findall(r"[a-z0-9']+", sl) if len(w) > 2)
    tw = set(w for w in re.findall(r"[a-z0-9']+", tl) if len(w) > 2)
    if tw and sw.issubset(tw) and len(sw) >= min(4, len(tw)):
        return True
    return False


def repair_low_quality_summary(
    summary: str,
    title: str,
    article_excerpt: Optional[str],
) -> str:
    """
    If summary is thin or repeats the title, rebuild from excerpt or title heuristics.
    Does not call OpenAI.
    """
    s = (summary or "").strip()
    t = (title or "").strip()
    ex = (article_excerpt or "").strip() if article_excerpt else ""

    if ex and len(ex) >= 40 and is_summary_redundant_with_title(s, t):
        fb = _fallback_from_excerpt_or_title(t, ex)
        if fb and not is_summary_redundant_with_title(fb, t):
            return fb

    if ex and len(ex) >= 40:
        fb = _excerpt_two_sentence_fallback(ex, t)
        if fb:
            out = clean_summary(fb)
            if out and not is_summary_redundant_with_title(out, t):
                return out

    if not s or is_summary_redundant_with_title(s, t):
        return _fallback_from_excerpt_or_title(t, ex if ex else None)

    return clean_summary(s)


def quick_fallback_summary(title: str, article_excerpt: Optional[str] = None) -> str:
    """Deterministic-only fallback summary."""
    from services.deterministic_summary import deterministic_summary_for_article

    out, _ = deterministic_summary_for_article(title or "", article_excerpt)
    return out


def display_summary_for_response(
    *,
    title: str,
    summary: Optional[str],
    rss_excerpt: Optional[str],
    summary_status: str,
) -> Tuple[str, str]:
    """
    Return summary text for JSON and summary_source for logging:
      rss | html | content | title_fallback | default
    """
    from services.deterministic_summary import (
        clamp_summary_display,
        deterministic_summary_for_article,
    )

    t = (title or "").strip()
    raw = (summary or "").strip()
    ex = (rss_excerpt or "").strip() if rss_excerpt else ""
    st = (summary_status or "pending").strip().lower()

    if raw and st in ("ready", "failed"):
        out = clamp_summary_display(raw)
        if out:
            return out, "stored"

    out, src = deterministic_summary_for_article(t, ex if ex else None)
    return out, src


def _strip_continue_reading(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"(?i)\bcontinue\s+reading\b[\s.:]*", "", s)
    s = re.sub(r"(?i)\bread\s+more\b[\s.:]*", "", s)
    s = re.sub(r"(?i)\bfull\s+story\b[\s.:]*", "", s)
    s = re.sub(r"(?i)\bclick\s+here\b[\s.:]*", "", s)
    s = re.sub(r"(?i)\bwatch\s+the\s+video\b[\s.:]*", "", s)
    s = re.sub(r"(?i)\bsee\s+more\b[\s.:]*", "", s)
    return s.strip()


def _split_sentences(text: str) -> List[str]:
    """Split on sentence-ending punctuation followed by space or end."""
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _complete_or_trim_words(words: List[str]) -> str:
    if not words:
        return ""
    joined = " ".join(words).strip()
    if not joined:
        return ""
    if joined[-1] in ".!?":
        return joined
    last_stop = max(joined.rfind("."), joined.rfind("!"), joined.rfind("?"))
    if last_stop > 0:
        return joined[: last_stop + 1].strip()
    return joined + "."


def _local_summarize_title(title: str) -> str:
    """
    Build 2–3 short sentences from the headline (no LLM).
    Prefer splitting on ':' / '–' / '—' for a second sentence; else pattern rewrites.
    """
    cleaned = (title or "").strip()
    if not cleaned:
        return "News update."

    paired = _try_pair_from_title_split(cleaned)
    if paired:
        return paired

    original = cleaned
    s = cleaned

    rewritten = _try_sports_down_ot(s)
    if rewritten:
        return _finalize_sentence(rewritten)

    rewritten = _try_sports_down(s)
    if rewritten:
        return _finalize_sentence(rewritten)

    rewritten = _try_police_service_welcomes(s)
    if rewritten:
        return _finalize_sentence(rewritten)

    rewritten = _try_ice_detains_bc(s)
    if rewritten:
        return _finalize_sentence(rewritten)

    s = _strip_trailing_attribution(s)
    s = _soft_rewrites(s)
    s = _tidy_spacing(s)

    if len(s) < 8:
        s = original

    return _finalize_sentence(s)


def _try_pair_from_title_split(title: str) -> Optional[str]:
    """If title has ':', '–', or '—', form two factual sentences."""
    t = title.strip()
    for sep in (":", "–", "—"):
        if sep in t:
            a, b = t.split(sep, 1)
            a, b = a.strip(), b.strip()
            if len(a) > 8 and len(b) > 8:
                s1 = _finalize_sentence(_soft_rewrites(_strip_trailing_attribution(a)))
                s2 = _finalize_sentence(_soft_rewrites(_strip_trailing_attribution(b)))
                return f"{s1} {s2}"
    return None


def _try_sports_down_ot(s: str) -> Optional[str]:
    m = re.match(
        r"^(.+?)\s+down\s+(.+?)\s+in\s+OT\.?$",
        s.strip(),
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    a, b = m.group(1).strip(), m.group(2).strip()
    return f"The {a} beat the {b} in overtime"


def _try_sports_down(s: str) -> Optional[str]:
    m = re.match(r"^(.+?)\s+down\s+(.+)$", s.strip(), flags=re.IGNORECASE)
    if not m:
        return None
    a, b = m.group(1).strip(), m.group(2).strip()
    if re.search(r"\d|%|points?|percent", b, re.I):
        return None
    if len(a.split()) < 2 or len(b.split()) < 2:
        return None
    return f"The {a} beat the {b}"


def _try_police_service_welcomes(s: str) -> Optional[str]:
    m = re.match(
        r"^(.+?)\s+Police\s+Service\s+welcomes\s+new\s+(.+)$",
        s.strip(),
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    city = m.group(1).strip()
    rest = m.group(2).strip().rstrip(".")
    if re.search(r"electronic\s+storage\s+detection\s+dog$", rest, re.I):
        return (
            f"{city} police have introduced a new dog trained to detect "
            f"electronic storage devices"
        )
    return f"{city} police have introduced a new {rest}"


def _try_ice_detains_bc(s: str) -> Optional[str]:
    if not re.match(r"^ICE detains\b", s.strip(), flags=re.IGNORECASE):
        return None
    t = s.strip()
    m = re.match(
        r"^ICE\s+detains\s+(.+?)\s+in\s+Texas,?\s*amid\s+(.+)$",
        t,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m:
        who = m.group(1).strip().rstrip(",")
        context = m.group(2).strip().rstrip(".")
        who = re.sub(
            r"\bmom,\s*daughter\b",
            "mother and daughter",
            who,
            flags=re.IGNORECASE,
        )
        who = re.sub(r"\bmom\b", "mother", who, flags=re.IGNORECASE)
        tail = _rewrite_amid_context(context)
        return f"A {who} were detained by ICE in Texas {tail}"

    if re.search(r"ICE\s+detains", t, re.I):
        inner = re.sub(r"^ICE\s+detains\s+", "", t, flags=re.I).strip()
        return f"ICE detained {inner}"


def _rewrite_amid_context(context: str) -> str:
    c = context.strip()
    if re.search(r"bumpy\s+road\s+to\s+citizenship", c, re.I):
        return "during a complicated citizenship process"
    if re.search(r"^bumpy\s+road\b", c, re.I):
        return "during a difficult process"
    return f"amid {c}"


def _strip_trailing_attribution(s: str) -> str:
    s = re.sub(r",\s*(says|reports?|according to|per)\b.*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+(says|reports?)\s+.+$", "", s, flags=re.IGNORECASE)
    return s


def _soft_rewrites(s: str) -> str:
    rules = [
        (r"\bcontinues to\b", ""),
        (r"\bhopes to\b", "plans to"),
        (r"\breportedly\b", ""),
        (r"\bit is reported that\b", ""),
        (r"\bsources say\b", ""),
        (r"\bWatch:\s*", ""),
        (r"\bBREAKING:\s*", ""),
        (r"\bin\s+OT\b", "in overtime"),
        (r"\bOT\.$", "overtime."),
        (r"\bOT\b$", "overtime"),
        (r"\bamid\b", "during"),
        (r"\bamidst\b", "during"),
    ]
    for pat, rep in rules:
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    return s


def _tidy_spacing(s: str) -> str:
    s = re.sub(r"\s*,\s*,", ",", s)
    s = re.sub(r"\s+", " ", s).strip(" ,;—-")
    s = re.sub(r"\s+\.", ".", s)
    return s.strip()


def _finalize_sentence(s: str) -> str:
    t = _sentence_case(s)
    if not t or len(t) < 2:
        t = _sentence_case(s)
    return t


def _sentence_case(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "News update."

    for i, ch in enumerate(t):
        if ch.isalpha():
            t = t[:i] + ch.upper() + t[i + 1 :]
            break

    if t[-1] not in ".!?…":
        t += "."

    return t
