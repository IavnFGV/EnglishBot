from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class ImageCandidate:
    model_name: str
    image_ref: str
    output_path: Path
    prompt: str


@dataclass(slots=True)
class ImageReviewItem:
    item_id: str
    english_word: str
    translation: str
    prompt: str
    candidates: list[ImageCandidate]
    selected_candidate_index: int | None = None
    skipped: bool = False


@dataclass(slots=True)
class ImageReviewFlowState:
    flow_id: str
    editor_user_id: int
    content_pack: dict[str, object]
    items: list[ImageReviewItem]
    current_index: int = 0
    output_path: Path | None = None

    @property
    def completed(self) -> bool:
        return self.current_index >= len(self.items)

    @property
    def current_item(self) -> ImageReviewItem | None:
        if self.completed:
            return None
        return self.items[self.current_index]
