from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")
_LEADING_SHOW_RE = re.compile(r"^\s*show\s+", re.IGNORECASE)
_DEFAULT_STYLE_PROMPT = (
    "Vocabulary flashcard, clear cartoon illustration, single main subject, "
    "centered composition, soft colors, clean light background, thick friendly outlines, "
    "simple shapes"
)
_LEGACY_STYLE_PROMPTS = (
    "Children's vocabulary flashcard, cute cartoon illustration, single main subject, "
    "centered composition, soft colors, clean light background, thick friendly outlines, "
    "simple shapes, educational card for a young child",
)
_HUMAN_ROLE_HINTS = {
    "king": "a human king wearing a golden crown and royal clothes",
    "queen": "a human queen wearing a jeweled crown and royal dress",
    "prince": "a human prince wearing a golden crown and royal clothes",
    "princess": "a human princess wearing a jeweled tiara and royal dress",
    "wizard": "a human wizard with a pointed hat and robe",
}


def fallback_image_prompt(english_word: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", english_word.strip())
    if not normalized:
        normalized = "vocabulary word"
    return compose_image_prompt(f"{normalized.lower()}", english_word=normalized)


def compose_image_prompt(
    subject_prompt: str,
    *,
    english_word: str | None = None,
    style_prompt: str | None = None,
) -> str:
    normalized_subject = _normalize_subject_prompt(subject_prompt)
    if not normalized_subject:
        normalized_subject = "vocabulary word"
    normalized_subject = _apply_subject_hints(
        normalized_subject,
        english_word=english_word or normalized_subject,
    )
    normalized_style = _WHITESPACE_RE.sub(
        " ",
        (style_prompt or _DEFAULT_STYLE_PROMPT).strip(),
    ).strip(" .,")
    return f"{normalized_style}. Show {normalized_subject}."


def _normalize_subject_prompt(subject_prompt: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", subject_prompt.strip()).strip(" .,")
    if not normalized:
        return ""

    while True:
        lowered = normalized.lower()
        matched_style = next(
            (
                style
                for style in (_DEFAULT_STYLE_PROMPT, *_LEGACY_STYLE_PROMPTS)
                if lowered.startswith(style.lower())
            ),
            None,
        )
        if matched_style is not None:
            remainder = normalized[len(matched_style) :].strip(" .")
            remainder = _LEADING_SHOW_RE.sub("", remainder).strip(" .")
            normalized = remainder or normalized
            if remainder:
                continue
        break

    normalized = _LEADING_SHOW_RE.sub("", normalized).strip(" .")
    return normalized


def _apply_subject_hints(subject_prompt: str, *, english_word: str) -> str:
    normalized_word = _WHITESPACE_RE.sub(" ", english_word.strip()).lower()
    if normalized_word in _HUMAN_ROLE_HINTS:
        return _HUMAN_ROLE_HINTS[normalized_word]
    return subject_prompt
