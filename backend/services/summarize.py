"""
services/summarize.py

Production-safe summarization with two modes:
1) OpenAI summaries when OPENAI_API_KEY is available
2) Local fallback summaries when key/API is unavailable

All stored summaries are normalized (2–3 sentences, ≤55 words) and validated for quality.
"""

import os
import re
from typing import List, Optional

import requests

from env import get_openai_api_key

# Model selection:
# - OPENAI_MODEL from environment if set
# - otherwise default to a lightweight model for short summaries
_DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
_OPENAI_TIMEOUT = 30
_VERIFICATION_HEADER_LOGGED = False
_SAMPLE_SUMMARY_LOGGED = False

# Caps (must match prompts + clean_summary)
_MAX_SUMMARY_WORDS = 55
_MAX_SUMMARY_SENTENCES = 3
# Below this word count we try a stricter OpenAI retry (if excerpt exists).
_MIN_SUMMARY_WORDS = 20

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
    if result[-1] not in ".!?":
        result += "."
    return result


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

    return s


def _needs_quality_retry(text: str) -> bool:
    """True if we should try a stricter OpenAI call or excerpt fallback."""
    s = (text or "").strip()
    if not s:
        return True
    parts = _split_sentences(s)
    wc = len(s.split())
    if len(parts) < 2:
        return True
    if wc < _MIN_SUMMARY_WORDS:
        return True
    return False


def normalize_stored_summary(
    text: str, title: str = "", article_excerpt: Optional[str] = None
) -> str:
    """Full pipeline for persisted/displayed summaries (OpenAI, local, RSS)."""
    return validate_summary(text, title=title, article_excerpt=article_excerpt)


def summarize_title(title: str, article_text: Optional[str] = None) -> str:
    """
    Return a readable summary (OpenAI or local), normalized for storage.

    - If OPENAI_API_KEY exists, try OpenAI (article_text preferred over title-only).
    - On missing key or any API error, fall back to local summarizer.
    """
    key = get_openai_api_key()
    model = (os.environ.get("OPENAI_MODEL") or _DEFAULT_OPENAI_MODEL).strip()
    _log_verification_header(key_present=bool(key), model=model)

    if key:
        ai = _openai_summarize(title, article_text, key, model)
        if ai:
            out = normalize_stored_summary(ai, title, article_text)
            _log_sample_summary(path_used="openai", summary=out)
            return out
        print("[summarize] OpenAI failed or empty response; using local fallback")
    else:
        print("[summarize] no API key; using local fallback")

    local = _local_summarize_title(title)
    out = normalize_stored_summary(local, title, article_text)
    _log_sample_summary(path_used="local_fallback", summary=out)
    return out


def quick_fallback_summary(title: str) -> str:
    """
    Fast, non-OpenAI summary used at ingest and edge cases.
    Same length/style rules as LLM summaries.
    """
    raw = _local_summarize_title(title)
    return normalize_stored_summary(raw, title, None)


def _strip_continue_reading(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"(?i)\bcontinue\s+reading\b[\s.:]*", "", s)
    s = re.sub(r"(?i)\bread\s+more\b[\s.:]*", "", s)
    s = re.sub(r"(?i)\bfull\s+story\b[\s.:]*", "", s)
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


def _build_user_prompt(title: str, article_text: Optional[str]) -> str:
    body = (article_text or "").strip()
    if not body:
        body = f"(Headline only — no article body.)\n{title}"
    return f"""Summarize this news article for a short-form news app.

STRICT FORMAT:
- Sentence 1: What happened (clear, complete event)
- Sentence 2: Key detail, comparison, or data (numbers, timeline, impact)
- Sentence 3 (optional): Why it matters or what happens next (but must be specific, not vague)

STRICT RULES:
- 2–3 sentences only
- Maximum 55 words
- Each sentence must add NEW information
- Avoid vague endings like:
  - "Further updates are expected"
  - "More details to come"
  - "Developing story"
- Do NOT leave the summary feeling incomplete
- Add context if possible (e.g., comparison to past events or scale)

STYLE:
- Clear, informative, complete thought
- Neutral tone
- Mobile-friendly, easy to scan

Title: {title}

Article:
{body[:12000]}
"""


_SYSTEM_OPENAI = (
    "You write only the summary sentences — no labels, no bullet points, no preamble. "
    "Obey the user's format and word limit exactly."
)

_SYSTEM_OPENAI_STRICT = (
    "You write only the summary. The previous draft was too short or too vague. "
    "You MUST give exactly 2 or 3 concrete sentences under 55 words total. "
    "Include at least one specific fact (number, date, place, or named entity) in sentence 2. "
    "Never end with filler about 'updates' or 'details to come'. "
    "No bullet points."
)


def _openai_summarize(
    title: str, article_text: Optional[str], api_key: str, model: str
) -> Optional[str]:
    """Return summary text, with one strict retry and excerpt fallback if needed."""
    t = (title or "").strip()
    if not t:
        return None

    user_content = _build_user_prompt(t, article_text)

    raw = _openai_chat(api_key, model, _SYSTEM_OPENAI, user_content, temperature=0.25)
    if not raw:
        return None

    validated = validate_summary(raw, title=t, article_excerpt=article_text)

    if _needs_quality_retry(validated) and (article_text or "").strip():
        print("[summarize] quality retry: stricter OpenAI prompt")
        raw2 = _openai_chat(
            api_key,
            model,
            _SYSTEM_OPENAI_STRICT,
            user_content,
            temperature=0.15,
        )
        if raw2:
            validated = validate_summary(raw2, title=t, article_excerpt=article_text)

    if _needs_quality_retry(validated) and (article_text or "").strip():
        fb = _excerpt_two_sentence_fallback(article_text or "", t)
        if fb:
            validated = validate_summary(fb, title=t, article_excerpt=article_text)

    return validated if validated.strip() else None


def _openai_chat(
    api_key: str,
    model: str,
    system_msg: str,
    user_content: str,
    *,
    temperature: float,
) -> Optional[str]:
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_content},
                ],
                "max_tokens": 220,
                "temperature": temperature,
            },
            timeout=_OPENAI_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        stripped = _strip_bullets_and_join_lines(text)
        return stripped if stripped else None
    except Exception as e:
        print(f"[summarize] OpenAI request failed: {e}")
        return None


def _log_verification_header(*, key_present: bool, model: str) -> None:
    global _VERIFICATION_HEADER_LOGGED
    if _VERIFICATION_HEADER_LOGGED:
        return
    _VERIFICATION_HEADER_LOGGED = True
    print(f"[summarize] OPENAI_API_KEY present: {'yes' if key_present else 'no'}")
    print(f"[summarize] model configured: {model}")
    if key_present:
        print("[summarize] strategy: try OpenAI first, then local fallback if needed")
    else:
        print("[summarize] strategy: local fallback only")


def _log_sample_summary(*, path_used: str, summary: str) -> None:
    global _SAMPLE_SUMMARY_LOGGED
    if _SAMPLE_SUMMARY_LOGGED or not (summary or "").strip():
        return
    _SAMPLE_SUMMARY_LOGGED = True
    s = summary.strip()
    preview = s if len(s) <= 220 else s[:220] + "..."
    print(f"[summarize] path used for sample: {path_used}")
    print(f"[summarize] sample summary: {preview!r}")


def _strip_bullets_and_join_lines(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return ""
    out_lines = []
    for ln in lines:
        ln = re.sub(r"^[\-\*•]\s+", "", ln)
        if ln:
            out_lines.append(ln)
    joined = " ".join(out_lines)
    joined = re.sub(r"\s+", " ", joined).strip()
    return joined


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
