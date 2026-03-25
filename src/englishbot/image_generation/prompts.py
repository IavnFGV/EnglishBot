from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")


def fallback_image_prompt(english_word: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", english_word.strip())
    if not normalized:
        normalized = "vocabulary word"
    return (
        f"A simple child-friendly illustration of {normalized.lower()} "
        "on a clean light background."
    )
