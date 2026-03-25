from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from englishbot.importing.models import ImportLessonResult


@dataclass(slots=True)
class AddWordsFlowState:
    flow_id: str
    editor_user_id: int
    raw_text: str
    draft_result: ImportLessonResult


@dataclass(slots=True, frozen=True)
class AddWordsApprovalResult:
    import_result: ImportLessonResult
    output_path: Path
