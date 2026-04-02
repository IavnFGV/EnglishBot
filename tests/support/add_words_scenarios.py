from __future__ import annotations

from collections import deque
from pathlib import Path

from englishbot.application.add_words_flow import AddWordsFlowHarness
from englishbot.application.add_words_use_cases import (
    ApplyAddWordsEditUseCase,
    ApproveAddWordsDraftUseCase,
    CancelAddWordsFlowUseCase,
    GenerateAddWordsImagePromptsUseCase,
    GetActiveAddWordsFlowUseCase,
    MarkAddWordsImageReviewStartedUseCase,
    RegenerateAddWordsDraftUseCase,
    SaveApprovedAddWordsDraftUseCase,
    StartAddWordsFlowUseCase,
)
from englishbot.domain.add_words_models import AddWordsApprovalResult, AddWordsFlowState
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import LessonExtractionClient
from englishbot.importing.models import ExtractedVocabularyItemDraft, LessonExtractionDraft
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.repositories import InMemoryAddWordsFlowRepository
from englishbot.infrastructure.sqlite_store import SQLiteContentStore

FAIRY_TALES_LESSON_TEXT = (
    "Fairy Tales\n\n"
    "Princess / Prince — принцесса / принц\n"
    "Castle — замок\n"
    "King / Queen — король / королева\n"
    "Dragon — дракон\n"
    "Fairy — фея\n"
    "Wizard — волшебник\n"
    "Mermaid — русалка\n"
    "Giant — великан\n"
    "Magic lamp — магическая лампа\n"
    "Jinn — джинн\n"
    "Ghost — привидение\n"
    "Dwarf — гномик\n"
    "Troll — тролль\n"
    "Ogre — огр (великан)\n"
    "Werewolf — оборотень\n"
    "Magic potion — волшебный эликсир\n"
    "Monster — чудовище\n"
    "Elf — эльф\n"
)

FAIRY_TALES_ITEMS = [
    ("Princess", "принцесса"),
    ("Prince", "принц"),
    ("Castle", "замок"),
    ("King", "король"),
    ("Queen", "королева"),
    ("Dragon", "дракон"),
    ("Fairy", "фея"),
    ("Wizard", "волшебник"),
    ("Mermaid", "русалка"),
    ("Giant", "великан"),
    ("Magic lamp", "магическая лампа"),
    ("Jinn", "джинн"),
    ("Ghost", "привидение"),
    ("Dwarf", "гномик"),
    ("Troll", "тролль"),
    ("Ogre", "огр (великан)"),
    ("Werewolf", "оборотень"),
    ("Magic potion", "волшебный эликсир"),
    ("Monster", "чудовище"),
    ("Elf", "эльф"),
]


def build_draft(
    *,
    topic_title: str = "Fairy Tales",
    lesson_title: str | None = None,
    items: list[tuple[str, str]] | None = None,
) -> LessonExtractionDraft:
    vocabulary_items = [
        ExtractedVocabularyItemDraft(
            item_id=english.lower().replace(" ", "-"),
            english_word=english,
            translation=translation,
            source_fragment=f"{english} — {translation}",
        )
        for english, translation in (items or [("Princess", "принцесса"), ("Prince", "принц")])
    ]
    return LessonExtractionDraft(
        topic_title=topic_title,
        lesson_title=lesson_title,
        vocabulary_items=vocabulary_items,
    )


class SequenceLessonExtractionClient:
    def __init__(self, drafts: list[LessonExtractionDraft | object]) -> None:
        self._drafts = deque(drafts)
        self._last = drafts[-1]

    def extract(self, raw_text: str) -> LessonExtractionDraft | object:  # noqa: ARG002
        if self._drafts:
            self._last = self._drafts.popleft()
        return self._last


class FakeImagePromptEnricher:
    def enrich(
        self,
        *,
        topic_title: str,  # noqa: ARG002
        vocabulary_items: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        enriched: list[dict[str, object]] = []
        for item in vocabulary_items:
            updated = dict(item)
            english_word = str(item.get("english_word", "")).strip()
            if english_word:
                updated["image_prompt"] = f"Prompt for {english_word}"
            enriched.append(updated)
        return enriched


def build_fairy_tales_draft() -> LessonExtractionDraft:
    return build_draft(items=FAIRY_TALES_ITEMS)


def build_driver(
    *,
    drafts: list[LessonExtractionDraft | object] | None = None,
    custom_content_dir: Path | None = None,
    db_path: Path | None = None,
) -> AddWordsScenarioDriver:
    extraction_client: LessonExtractionClient
    if drafts is None:
        drafts = [build_draft()]
    extraction_client = SequenceLessonExtractionClient(drafts)
    pipeline = LessonImportPipeline(
        extraction_client=extraction_client,
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        image_prompt_enricher=FakeImagePromptEnricher(),  # type: ignore[arg-type]
    )
    repository = InMemoryAddWordsFlowRepository()
    resolved_content_dir = custom_content_dir or Path("content/custom")
    content_store = SQLiteContentStore(
        db_path=db_path or resolved_content_dir / "englishbot.db"
    )
    harness = AddWordsFlowHarness(
        pipeline=pipeline,
        validator=LessonExtractionValidator(),
        writer=JsonContentPackWriter(),
        custom_content_dir=resolved_content_dir,
        content_store=content_store,
    )
    return AddWordsScenarioDriver(
        start=StartAddWordsFlowUseCase(harness=harness, flow_repository=repository),
        get_active=GetActiveAddWordsFlowUseCase(repository),
        apply_edit=ApplyAddWordsEditUseCase(harness=harness, flow_repository=repository),
        regenerate=RegenerateAddWordsDraftUseCase(harness=harness, flow_repository=repository),
        approve=ApproveAddWordsDraftUseCase(harness=harness, flow_repository=repository),
        save_approved_draft=SaveApprovedAddWordsDraftUseCase(
            harness=harness,
            flow_repository=repository,
        ),
        generate_image_prompts=GenerateAddWordsImagePromptsUseCase(
            harness=harness,
            flow_repository=repository,
        ),
        mark_image_review_started=MarkAddWordsImageReviewStartedUseCase(
            harness=harness,
            flow_repository=repository,
        ),
        cancel=CancelAddWordsFlowUseCase(repository),
    )


class AddWordsScenarioDriver:
    def __init__(
        self,
        *,
        start: StartAddWordsFlowUseCase,
        get_active: GetActiveAddWordsFlowUseCase,
        apply_edit: ApplyAddWordsEditUseCase,
        regenerate: RegenerateAddWordsDraftUseCase,
        approve: ApproveAddWordsDraftUseCase,
        save_approved_draft: SaveApprovedAddWordsDraftUseCase,
        generate_image_prompts: GenerateAddWordsImagePromptsUseCase,
        mark_image_review_started: MarkAddWordsImageReviewStartedUseCase,
        cancel: CancelAddWordsFlowUseCase,
    ) -> None:
        self._start = start
        self._get_active = get_active
        self._apply_edit = apply_edit
        self._regenerate = regenerate
        self._approve = approve
        self._save_approved_draft = save_approved_draft
        self._generate_image_prompts = generate_image_prompts
        self._mark_image_review_started = mark_image_review_started
        self._cancel = cancel
        self.flow: AddWordsFlowState | None = None
        self.approval: AddWordsApprovalResult | None = None

    def when_editor_starts_flow(
        self,
        *,
        user_id: int = 1,
        raw_text: str = "raw text",
    ) -> AddWordsScenarioDriver:
        self.flow = self._start.execute(user_id=user_id, raw_text=raw_text)
        return self

    def when_editor_edits_draft(
        self,
        *,
        user_id: int = 1,
        flow_id: str | None = None,
        edited_text: str,
    ) -> AddWordsScenarioDriver:
        resolved_flow_id = flow_id or self._require_flow().flow_id
        self.flow = self._apply_edit.execute(
            user_id=user_id,
            flow_id=resolved_flow_id,
            edited_text=edited_text,
        )
        return self

    def when_editor_regenerates_draft(
        self,
        *,
        user_id: int = 1,
        flow_id: str | None = None,
    ) -> AddWordsScenarioDriver:
        resolved_flow_id = flow_id or self._require_flow().flow_id
        self.flow = self._regenerate.execute(
            user_id=user_id,
            flow_id=resolved_flow_id,
        )
        return self

    def when_editor_cancels_flow(self, *, user_id: int = 1) -> AddWordsScenarioDriver:
        self._cancel.execute(user_id=user_id)
        self.flow = None
        return self

    def when_editor_approves_draft(
        self,
        *,
        user_id: int = 1,
        flow_id: str | None = None,
        output_path: Path | None = None,
    ) -> AddWordsScenarioDriver:
        resolved_flow_id = flow_id or self._require_flow().flow_id
        self.approval = self._approve.execute(
            user_id=user_id,
            flow_id=resolved_flow_id,
            output_path=output_path,
        )
        self.flow = None
        return self

    def when_editor_saves_approved_draft(
        self,
        *,
        user_id: int = 1,
        flow_id: str | None = None,
        output_path: Path | None = None,
    ) -> AddWordsScenarioDriver:
        resolved_flow_id = flow_id or self._require_flow().flow_id
        self.flow = self._save_approved_draft.execute(
            user_id=user_id,
            flow_id=resolved_flow_id,
            output_path=output_path,
        )
        return self

    def when_editor_generates_image_prompts(
        self,
        *,
        user_id: int = 1,
        flow_id: str | None = None,
    ) -> AddWordsScenarioDriver:
        resolved_flow_id = flow_id or self._require_flow().flow_id
        self.flow = self._generate_image_prompts.execute(
            user_id=user_id,
            flow_id=resolved_flow_id,
        )
        return self

    def when_editor_starts_image_review_task(
        self,
        *,
        user_id: int = 1,
        flow_id: str | None = None,
        image_review_flow_id: str = "image-review-1",
    ) -> AddWordsScenarioDriver:
        resolved_flow_id = flow_id or self._require_flow().flow_id
        self.flow = self._mark_image_review_started.execute(
            user_id=user_id,
            flow_id=resolved_flow_id,
            image_review_flow_id=image_review_flow_id,
        )
        return self

    def get_active_flow(self, *, user_id: int = 1) -> AddWordsFlowState | None:
        return self._get_active.execute(user_id=user_id)

    def _require_flow(self) -> AddWordsFlowState:
        if self.flow is None:
            raise AssertionError("No active flow in driver.")
        return self.flow
