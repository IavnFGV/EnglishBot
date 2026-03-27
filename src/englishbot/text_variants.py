from __future__ import annotations

import re

_SLASH_SPLIT_RE = re.compile(r"\s*/\s*")


def split_slash_variants(value: str) -> list[str]:
    normalized = " ".join(value.split()).strip()
    if "/" not in normalized:
        return [normalized] if normalized else []
    variants: list[str] = []
    for raw_part in _SLASH_SPLIT_RE.split(normalized):
        cleaned = raw_part.strip().strip("-").strip()
        if cleaned and cleaned not in variants:
            variants.append(cleaned)
    return variants or ([normalized] if normalized else [])


def expand_aligned_slash_variants(*, english_word: str, translation: str) -> tuple[list[str], list[str]]:
    english_variants = split_slash_variants(english_word) if "/" in english_word else [english_word]
    translation_variants = split_slash_variants(translation) if "/" in translation else [translation]
    if len(english_variants) > 1 and len(english_variants) == len(translation_variants):
        return english_variants, translation_variants
    if len(english_variants) > 1 and len(translation_variants) == 1:
        return english_variants, [translation_variants[0]] * len(english_variants)
    return [english_word], [translation]
