from __future__ import annotations

import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from englishbot.domain.models import VocabularyItem
from englishbot.image_generation.paths import resolve_existing_image_path
from englishbot.image_generation.pixabay import PixabayImageResult
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class FillWordImagesSummary:
    scanned_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0


def _normalize_phrase(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(normalized.lower().split()).strip()


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", _normalize_phrase(value)))


def _candidate_text(candidate: PixabayImageResult) -> str:
    parsed = urlparse(candidate.source_page_url)
    path_text = " ".join(segment for segment in parsed.path.split("/") if segment)
    return " ".join((*candidate.tags, path_text))


def _candidate_score(
    *,
    english_word: str,
    normalized_query: str,
    candidate: PixabayImageResult,
) -> int:
    normalized_english = _normalize_phrase(english_word)
    candidate_text = _candidate_text(candidate)
    candidate_tokens = set(_tokenize(candidate_text))
    english_tokens = set(_tokenize(normalized_english))
    query_tokens = set(_tokenize(normalized_query))
    normalized_tags = {_normalize_phrase(tag) for tag in candidate.tags}
    score = 0

    if normalized_english and normalized_english in normalized_tags:
        score += 300
    if normalized_query and normalized_query in normalized_tags:
        score += 220
    if normalized_english and normalized_english in candidate_text:
        score += 120
    if normalized_query and normalized_query in candidate_text:
        score += 80

    score += 35 * len(english_tokens & candidate_tokens)
    score += 15 * len(query_tokens & candidate_tokens)

    if candidate.width is not None and candidate.height is not None:
        smaller_side = min(candidate.width, candidate.height)
        if smaller_side >= 900:
            score += 30
        elif smaller_side >= 600:
            score += 18
        elif smaller_side >= 300:
            score += 8
        ratio = candidate.width / candidate.height if candidate.height > 0 else 0
        if 0.75 <= ratio <= 1.6:
            score += 12
    return score


def select_best_pixabay_candidate(
    *,
    english_word: str,
    normalized_query: str,
    candidates: list[PixabayImageResult],
) -> PixabayImageResult | None:
    if not candidates:
        return None
    ranked = sorted(
        enumerate(candidates),
        key=lambda pair: (
            _candidate_score(
                english_word=english_word,
                normalized_query=normalized_query,
                candidate=pair[1],
            ),
            -pair[0],
        ),
        reverse=True,
    )
    return ranked[0][1]


def _target_image_path(*, assets_dir: Path, item: VocabularyItem, candidate: PixabayImageResult) -> Path:
    topic_id = item.topic_id or "shared"
    suffix = Path(urlparse(candidate.full_image_url).path).suffix or ".jpg"
    return assets_dir / topic_id / f"{item.id}{suffix}"


class FillWordImagesUseCase:
    def __init__(
        self,
        *,
        store,
        image_search_client,
        remote_image_downloader,
        assets_dir: Path,
    ) -> None:
        self._store = store
        self._image_search_client = image_search_client
        self._remote_image_downloader = remote_image_downloader
        self._assets_dir = assets_dir

    @logged_service_call(
        "FillWordImagesUseCase.execute",
        include=("topic_id", "limit", "force", "dry_run", "delay_sec"),
        result=lambda value: {
            "scanned_count": value.scanned_count,
            "updated_count": value.updated_count,
            "skipped_count": value.skipped_count,
            "failed_count": value.failed_count,
        },
    )
    def execute(
        self,
        *,
        topic_id: str | None = None,
        limit: int | None = None,
        force: bool = False,
        dry_run: bool = False,
        delay_sec: float = 0.0,
    ) -> FillWordImagesSummary:
        scanned_count = 0
        updated_count = 0
        skipped_count = 0
        failed_count = 0
        items = [
            item
            for item in self._store.list_all_vocabulary()
            if item.is_active and (topic_id is None or item.topic_id == topic_id)
        ]
        if limit is not None:
            items = items[:limit]
        for item in items:
            scanned_count += 1
            existing_path = resolve_existing_image_path(item.image_ref)
            if not force and existing_path is not None:
                skipped_count += 1
                continue
            query = (item.pixabay_search_query or item.english_word).strip()
            try:
                normalized_query, candidates = self._image_search_client.search(
                    english_word=item.english_word,
                    query=query,
                    per_page=20,
                )
                selected = select_best_pixabay_candidate(
                    english_word=item.english_word,
                    normalized_query=normalized_query,
                    candidates=candidates,
                )
                if selected is None:
                    failed_count += 1
                    logger.warning("No Pixabay candidates found item_id=%s query=%s", item.id, normalized_query)
                    continue
                output_path = _target_image_path(
                    assets_dir=self._assets_dir,
                    item=item,
                    candidate=selected,
                )
                logger.info(
                    "Selected Pixabay image item_id=%s english_word=%s query=%s source_id=%s tags=%s output_path=%s",
                    item.id,
                    item.english_word,
                    normalized_query,
                    selected.source_id,
                    selected.tags,
                    output_path,
                )
                if not dry_run:
                    self._remote_image_downloader.download(
                        url=selected.full_image_url,
                        output_path=output_path,
                    )
                    self._store.update_word_image(
                        item_id=item.id,
                        image_ref=output_path.as_posix(),
                        image_source="pixabay",
                        pixabay_search_query=normalized_query,
                        source_fragment=selected.source_page_url,
                    )
                updated_count += 1
            except Exception:  # noqa: BLE001
                failed_count += 1
                logger.exception("Failed to backfill image item_id=%s english_word=%s", item.id, item.english_word)
            if delay_sec > 0:
                time.sleep(delay_sec)
        return FillWordImagesSummary(
            scanned_count=scanned_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
        )
