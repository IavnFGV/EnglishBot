from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from englishbot.importing.models import ImportLessonResult

AddWordsFlowStage = Literal[
    "draft_review",
    "draft_saved",
    "prompts_generated",
    "image_review",
]


@dataclass(slots=True)
class AddWordsFlowState:
    flow_id: str
    editor_user_id: int
    raw_text: str
    draft_result: ImportLessonResult
    stage: AddWordsFlowStage = "draft_review"
    draft_output_path: Path | None = None
    final_output_path: Path | None = None
    image_review_flow_id: str | None = None


@dataclass(slots=True, frozen=True)
class AddWordsApprovalResult:
    import_result: ImportLessonResult
    output_path: Path
