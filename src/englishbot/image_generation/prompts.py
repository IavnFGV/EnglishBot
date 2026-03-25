from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")
_DEFAULT_STYLE_PROMPT = (
    "Children's vocabulary flashcard, cute cartoon illustration, single main subject, "
    "centered composition, soft colors, clean light background, thick friendly outlines, "
    "simple shapes, educational card for a young child"
)


def fallback_image_prompt(english_word: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", english_word.strip())
    if not normalized:
        normalized = "vocabulary word"
    return compose_image_prompt(f"{normalized.lower()}")


def compose_image_prompt(subject_prompt: str, *, style_prompt: str | None = None) -> str:
    normalized_subject = _WHITESPACE_RE.sub(" ", subject_prompt.strip()).strip(" .,")
    if not normalized_subject:
        normalized_subject = "vocabulary word"
    normalized_style = _WHITESPACE_RE.sub(
        " ",
        (style_prompt or _DEFAULT_STYLE_PROMPT).strip(),
    ).strip(" .,")
    return f"{normalized_style}. Show {normalized_subject}."
