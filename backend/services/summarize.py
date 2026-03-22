"""
services/summarize.py

Production-safe summarization with two modes:
1) OpenAI summaries when OPENAI_API_KEY is available
2) Local fallback summaries when key/API is unavailable
"""

import os
import re
from typing import Optional

import requests

from env import get_openai_api_key

# Model selection:
# - OPENAI_MODEL from environment if set
# - otherwise default to a lightweight model for short summaries
_DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
_OPENAI_TIMEOUT = 30
_VERIFICATION_HEADER_LOGGED = False
_SAMPLE_SUMMARY_LOGGED = False


def summarize_title(title: str, article_text: Optional[str] = None) -> str:
    """
    Return a readable summary (OpenAI: ~2–4 sentences when article_text is available).

    Public function used by the app.
    - If OPENAI_API_KEY exists, try OpenAI (article_text preferred over title-only).
    - On missing key or any API error, fall back to local summarizer.
    """
    key = get_openai_api_key()
    model = (os.environ.get("OPENAI_MODEL") or _DEFAULT_OPENAI_MODEL).strip()
    _log_verification_header(key_present=bool(key), model=model)

    if key:
        ai = _openai_summarize(title, article_text, key, model)
        if ai:
            _log_sample_summary(path_used="openai", summary=ai)
            return ai
        print("[summarize] OpenAI failed or empty response; using local fallback")
    else:
        print("[summarize] no API key; using local fallback")

    local = _local_summarize_title(title)
    _log_sample_summary(path_used="local_fallback", summary=local)
    return local


def quick_fallback_summary(title: str) -> str:
    """
    Fast, non-OpenAI summary text used at ingest time (before lazy AI on page view).
    Keeps refresh fast; real AI summary runs later only for rows still marked pending.
    """
    return _local_summarize_title(title)


def _local_summarize_title(title: str) -> str:
    """
    Turn a headline into a short, readable one-sentence summary.

    Uses simple pattern rules and light rewrites—no "In brief:" framing.
    Falls back to a cleaned, sentence-shaped version of the title.
    """
    cleaned = (title or "").strip()
    if not cleaned:
        return "News update."

    original = cleaned
    s = cleaned

    # --- Specific headline templates (checked first) ---
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

    # --- General cleanup & soft rewrites ---
    s = _strip_trailing_attribution(s)
    s = _soft_rewrites(s)
    s = _tidy_spacing(s)

    if len(s) < 8:
        s = original

    return _finalize_sentence(s)


def _openai_summarize(
    title: str, article_text: Optional[str], api_key: str, model: str
) -> Optional[str]:
    """Return cleaned summary text, or None on error / empty response."""
    t = (title or "").strip()
    if not t:
        return None

    body = (article_text or "").strip()
    if body:
        user_block = f"Title:\n{t}\n\nArticle text:\n{body[:12000]}"
    else:
        user_block = f"Only this headline is available:\n{t}"

    system_msg = (
        "Write a clear, factual summary of this news story in 2 to 4 sentences. "
        "Include the main event, who is involved, and the most important context "
        "(timing, place, or why it matters) when that information appears in the text. "
        "Use plain language for a general reader. "
        "Do not repeat the headline verbatim, add opinions, hype, or filler. "
        "Do not use bullet points. "
        "If the source text is thin, still stay within 2–4 sentences without inventing facts."
    )

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
                    {"role": "user", "content": user_block},
                ],
                "max_tokens": 380,
                "temperature": 0.3,
            },
            timeout=_OPENAI_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        cleaned = _clean_model_summary(text)
        return cleaned if cleaned else None
    except Exception as e:
        print(f"[summarize] OpenAI request failed: {e}")
        return None


def _log_verification_header(*, key_present: bool, model: str) -> None:
    """Once per process: confirm env + model (never print the secret key)."""
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
    """One sample line so you can see real output and which path produced it."""
    global _SAMPLE_SUMMARY_LOGGED
    if _SAMPLE_SUMMARY_LOGGED or not (summary or "").strip():
        return
    _SAMPLE_SUMMARY_LOGGED = True
    s = summary.strip()
    preview = s if len(s) <= 220 else s[:220] + "..."
    print(f"[summarize] path used for sample: {path_used}")
    print(f"[summarize] sample summary: {preview!r}")


def _clean_model_summary(text: str) -> str:
    """Remove common list markers; keep a short paragraph."""
    s = (text or "").strip()
    if not s:
        return ""
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return ""
    # Drop leading bullet-style lines if the model ignored instructions
    out_lines = []
    for ln in lines:
        ln = re.sub(r"^[\-\*•]\s+", "", ln)
        if ln:
            out_lines.append(ln)
    joined = " ".join(out_lines)
    joined = re.sub(r"\s+", " ", joined).strip()
    return joined


def _try_sports_down_ot(s: str) -> Optional[str]:
    """
    'Team A down Team B in OT' -> 'The Team A beat the Team B in overtime.'
    """
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
    """Two-name sports headline: 'X down Y' (no OT in title)."""
    m = re.match(r"^(.+?)\s+down\s+(.+)$", s.strip(), flags=re.IGNORECASE)
    if not m:
        return None
    a, b = m.group(1).strip(), m.group(2).strip()
    # Avoid false positives ('prices down 5%')
    if re.search(r"\d|%|points?|percent", b, re.I):
        return None
    # Need two multi-word sides (avoids "Stocks down sharply")
    if len(a.split()) < 2 or len(b.split()) < 2:
        return None
    return f"The {a} beat the {b}"


def _try_police_service_welcomes(s: str) -> Optional[str]:
    """
    'Saskatoon Police Service welcomes new electronic storage detection dog'
    -> natural sentence with 'police have introduced...'
    """
    m = re.match(
        r"^(.+?)\s+Police\s+Service\s+welcomes\s+new\s+(.+)$",
        s.strip(),
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    city = m.group(1).strip()
    rest = m.group(2).strip().rstrip(".")
    # Optional: expand 'X detection dog' style endings slightly
    if re.search(r"electronic\s+storage\s+detection\s+dog$", rest, re.I):
        return (
            f"{city} police have introduced a new dog trained to detect "
            f"electronic storage devices"
        )
    return f"{city} police have introduced a new {rest}"


def _try_ice_detains_bc(s: str) -> Optional[str]:
    """
    ICE / B.C. family detention headlines → neutral passive summary.
    """
    if not re.match(r"^ICE detains\b", s.strip(), flags=re.IGNORECASE):
        return None
    t = s.strip()
    # Example shape: ICE detains B.C. mom, daughter in Texas, amid ...
    m = re.match(
        r"^ICE\s+detains\s+(.+?)\s+in\s+Texas,?\s*amid\s+(.+)$",
        t,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m:
        who = m.group(1).strip().rstrip(",")
        context = m.group(2).strip().rstrip(".")
        # Light normalization of 'mom, daughter' -> mother and daughter
        who = re.sub(
            r"\bmom,\s*daughter\b",
            "mother and daughter",
            who,
            flags=re.IGNORECASE,
        )
        who = re.sub(r"\bmom\b", "mother", who, flags=re.IGNORECASE)
        tail = _rewrite_amid_context(context)
        return f"A {who} were detained by ICE in Texas {tail}"

    # Shorter ICE line
    if re.search(r"ICE\s+detains", t, re.I):
        inner = re.sub(r"^ICE\s+detains\s+", "", t, flags=re.I).strip()
        return f"ICE detained {inner}"


def _rewrite_amid_context(context: str) -> str:
    """Turn trailing 'amid X' into a readable clause."""
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
    """Small deterministic substitutions that usually read better in summary form."""
    rules = [
        (r"\bcontinues to\b", ""),
        (r"\bhopes to\b", "plans to"),
        (r"\breportedly\b", ""),
        (r"\bit is reported that\b", ""),
        (r"\bsources say\b", ""),
        (r"\bWatch:\s*", ""),
        (r"\bBREAKING:\s*", ""),
        # Expand common headline shorthand
        (r"\bin\s+OT\b", "in overtime"),
        (r"\bOT\.$", "overtime."),
        (r"\bOT\b$", "overtime"),
        # Slightly softer connectors
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
    """One readable sentence: sentence case + ending period."""
    t = _sentence_case(s)
    if not t or len(t) < 2:
        t = _sentence_case(s)
    return t


def _sentence_case(text: str) -> str:
    """Ensure a single sentence with capital start and trailing period."""
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
