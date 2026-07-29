from __future__ import annotations

import html
import re

_URL_RE = re.compile(r"(?:https?://|t\.me/|www\.)\S+", re.IGNORECASE)
_MENTION_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{4,}")
_HASHTAG_RE = re.compile(r"(?<!\w)#[\wА-Яа-яЁё]+")
_SPACE_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


def normalize_for_llm(text: str) -> str:
    """Remove transport noise while preserving authorial punctuation and layout."""
    value = html.unescape(text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = _URL_RE.sub("<URL>", value)
    value = _MENTION_RE.sub("<MENTION>", value)
    value = _HASHTAG_RE.sub("<HASHTAG>", value)
    value = "\n".join(_SPACE_RE.sub(" ", line).strip() for line in value.splitlines())
    return _BLANK_RE.sub("\n\n", value).strip()


def compact_excerpt(text: str, limit: int = 180) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"
