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
