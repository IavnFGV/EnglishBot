from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from englishbot.application.fill_word_images_use_cases import select_best_pixabay_candidate
from englishbot.domain.models import VocabularyItem
from englishbot.image_generation.pixabay import PixabayImageResult
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ImageRerankManifestItem:
    item_id: str
    english_word: str
    translation: str
    topic_id: str
    topic_title: str
    query: str
    current_image_ref: str | None = None


@dataclass(slots=True, frozen=True)
class ImageRerankManifest:
    exported_at: str
    item_count: int
    items: list[ImageRerankManifestItem]


@dataclass(slots=True, frozen=True)
class ImageRerankDecisionItem:
    item_id: str
    english_word: str
    translation: str
    topic_id: str
    topic_title: str
    query: str
    decision_source: str
    selected_index: int
    confidence: float | None
    rationale: str
    selected_candidate: dict[str, object]


@dataclass(slots=True, frozen=True)
class ImageRerankDecisions:
    generated_at: str
    model: str
    item_count: int
    items: list[ImageRerankDecisionItem]


def write_image_rerank_manifest(*, manifest: ImageRerankManifest, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "exported_at": manifest.exported_at,
                "item_count": manifest.item_count,
                "items": [asdict(item) for item in manifest.items],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def read_image_rerank_manifest(*, input_path: Path) -> ImageRerankManifest:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    raw_items = raw.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Manifest must contain an items list.")
    items = [
        ImageRerankManifestItem(
            item_id=str(item["item_id"]),
            english_word=str(item["english_word"]),
            translation=str(item["translation"]),
            topic_id=str(item["topic_id"]),
            topic_title=str(item["topic_title"]),
            query=str(item["query"]),
            current_image_ref=_optional_string(item.get("current_image_ref")),
        )
        for item in raw_items
    ]
    return ImageRerankManifest(
        exported_at=str(raw.get("exported_at") or ""),
        item_count=len(items),
        items=items,
    )


def write_image_rerank_decisions(*, decisions: ImageRerankDecisions, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "generated_at": decisions.generated_at,
                "model": decisions.model,
                "item_count": decisions.item_count,
                "items": [asdict(item) for item in decisions.items],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def read_image_rerank_decisions(*, input_path: Path) -> ImageRerankDecisions:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    raw_items = raw.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Decisions file must contain an items list.")
    items = [
        ImageRerankDecisionItem(
            item_id=str(item["item_id"]),
            english_word=str(item["english_word"]),
            translation=str(item["translation"]),
            topic_id=str(item["topic_id"]),
            topic_title=str(item["topic_title"]),
            query=str(item["query"]),
            decision_source=str(item["decision_source"]),
            selected_index=int(item["selected_index"]),
            confidence=float(item["confidence"]) if isinstance(item.get("confidence"), (int, float)) else None,
            rationale=str(item.get("rationale") or ""),
            selected_candidate=dict(item["selected_candidate"]),
        )
        for item in raw_items
    ]
    return ImageRerankDecisions(
        generated_at=str(raw.get("generated_at") or ""),
        model=str(raw.get("model") or ""),
        item_count=len(items),
        items=items,
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _topic_titles_by_id(store) -> dict[str, str]:
    return {topic.id: topic.title for topic in store.list_topics()}


def _target_image_path(*, assets_dir: Path, topic_id: str, item_id: str, full_image_url: str) -> Path:
    suffix = Path(urlparse(full_image_url).path).suffix or ".jpg"
    return assets_dir / topic_id / f"{item_id}{suffix}"


class ExportImageRerankManifestUseCase:
    def __init__(self, *, store) -> None:
        self._store = store

    @logged_service_call(
        "ExportImageRerankManifestUseCase.execute",
        include=("topic_id", "limit", "only_missing_images"),
        result=lambda value: {"item_count": value.item_count},
    )
    def execute(
        self,
        *,
        topic_id: str | None = None,
        limit: int | None = None,
        only_missing_images: bool = False,
    ) -> ImageRerankManifest:
        topic_titles = _topic_titles_by_id(self._store)
        items: list[ImageRerankManifestItem] = []
        for item in self._store.list_all_vocabulary():
            if not item.is_active:
                continue
            if item.topic_id is None:
                continue
            if topic_id is not None and item.topic_id != topic_id:
                continue
            if only_missing_images and _optional_string(item.image_ref) is not None:
                continue
            items.append(
                ImageRerankManifestItem(
                    item_id=item.id,
                    english_word=item.english_word,
                    translation=item.translation,
                    topic_id=item.topic_id,
                    topic_title=topic_titles.get(item.topic_id, item.topic_id),
                    query=(item.pixabay_search_query or item.english_word).strip(),
                    current_image_ref=item.image_ref,
                )
            )
        if limit is not None:
            items = items[:limit]
        return ImageRerankManifest(
            exported_at=_current_timestamp(),
            item_count=len(items),
            items=items,
        )


class RerankImageManifestUseCase:
    def __init__(
        self,
        *,
        image_search_client,
        reranker_client,
        candidate_count: int = 3,
    ) -> None:
        self._image_search_client = image_search_client
        self._reranker_client = reranker_client
        self._candidate_count = candidate_count

    @logged_service_call(
        "RerankImageManifestUseCase.execute",
        include=("candidate_count",),
        transforms={"manifest": lambda value: {"item_count": len(value.items)}},
        result=lambda value: {"item_count": value.item_count},
    )
    def execute(
        self,
        *,
        manifest: ImageRerankManifest,
        model_name: str,
    ) -> ImageRerankDecisions:
        items: list[ImageRerankDecisionItem] = []
        for item in manifest.items:
            normalized_query, candidates = self._image_search_client.search(
                english_word=item.english_word,
                query=item.query,
                per_page=self._candidate_count,
            )
            if not candidates:
                logger.warning("No Pixabay candidates found item_id=%s query=%s", item.item_id, normalized_query)
                continue
            selected_index: int | None = None
            confidence: float | None = None
            rationale = ""
            decision_source = "ollama"
            try:
                decision = self._reranker_client.rerank(
                    english_word=item.english_word,
                    translation=item.translation,
                    topic_title=item.topic_title,
                    candidates=[_candidate_to_payload(candidate) for candidate in candidates],
                )
                selected_index = decision.selected_index
                confidence = decision.confidence
                rationale = decision.rationale
            except Exception:  # noqa: BLE001
                logger.exception(
                    "LLM rerank failed item_id=%s english_word=%s query=%s; falling back to heuristic selection",
                    item.item_id,
                    item.english_word,
                    normalized_query,
                )
                fallback = select_best_pixabay_candidate(
                    english_word=item.english_word,
                    normalized_query=normalized_query,
                    candidates=candidates,
                )
                if fallback is None:
                    continue
                selected_index = candidates.index(fallback)
                decision_source = "heuristic_fallback"
                rationale = "Fallback to heuristic Pixabay candidate scoring."
            items.append(
                ImageRerankDecisionItem(
                    item_id=item.item_id,
                    english_word=item.english_word,
                    translation=item.translation,
                    topic_id=item.topic_id,
                    topic_title=item.topic_title,
                    query=normalized_query,
                    decision_source=decision_source,
                    selected_index=selected_index,
                    confidence=confidence,
                    rationale=rationale,
                    selected_candidate=_candidate_to_payload(candidates[selected_index]),
                )
            )
        return ImageRerankDecisions(
            generated_at=_current_timestamp(),
            model=model_name,
            item_count=len(items),
            items=items,
        )


class ApplyImageRerankDecisionsUseCase:
    def __init__(
        self,
        *,
        store,
        remote_image_downloader,
        assets_dir: Path,
    ) -> None:
        self._store = store
        self._remote_image_downloader = remote_image_downloader
        self._assets_dir = assets_dir

    @logged_service_call(
        "ApplyImageRerankDecisionsUseCase.execute",
        include=("dry_run",),
        transforms={"decisions": lambda value: {"item_count": len(value.items)}},
        result=lambda value: value,
    )
    def execute(
        self,
        *,
        decisions: ImageRerankDecisions,
        dry_run: bool = False,
    ) -> dict[str, int]:
        updated_count = 0
        failed_count = 0
        for item in decisions.items:
            full_image_url = str(item.selected_candidate.get("full_image_url") or "").strip()
            source_page_url = str(item.selected_candidate.get("source_page_url") or "").strip()
            source_id = str(item.selected_candidate.get("source_id") or "").strip()
            if not full_image_url or not source_page_url:
                failed_count += 1
                logger.warning("Decision item is missing full_image_url or source_page_url item_id=%s", item.item_id)
                continue
            output_path = _target_image_path(
                assets_dir=self._assets_dir,
                topic_id=item.topic_id,
                item_id=item.item_id,
                full_image_url=full_image_url,
            )
            if not dry_run:
                self._remote_image_downloader.download(url=full_image_url, output_path=output_path)
                self._store.update_word_image(
                    item_id=item.item_id,
                    image_ref=output_path.as_posix(),
                    image_source=f"pixabay:{item.decision_source}",
                    pixabay_search_query=item.query,
                    source_fragment=source_page_url,
                )
            logger.info(
                "Applied reranked image item_id=%s source_id=%s output_path=%s decision_source=%s",
                item.item_id,
                source_id,
                output_path,
                item.decision_source,
            )
            updated_count += 1
        return {"updated_count": updated_count, "failed_count": failed_count}


def _candidate_to_payload(candidate: PixabayImageResult) -> dict[str, object]:
    return {
        "source_id": candidate.source_id,
        "preview_url": candidate.preview_url,
        "full_image_url": candidate.full_image_url,
        "source_page_url": candidate.source_page_url,
        "width": candidate.width,
        "height": candidate.height,
        "tags": list(candidate.tags),
    }
