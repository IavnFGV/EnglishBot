from __future__ import annotations

import random
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

from englishbot.application.add_words_flow import AddWordsFlowHarness
from englishbot.application.add_words_use_cases import (
    ApplyAddWordsEditUseCase,
    ApproveAddWordsDraftUseCase,
    CancelAddWordsFlowUseCase,
    GetActiveAddWordsFlowUseCase,
    RegenerateAddWordsDraftUseCase,
    StartAddWordsFlowUseCase,
)
from englishbot.application.clock import FixedClock
from englishbot.application.image_review_flow import ImageReviewFlowHarness
from englishbot.application.image_review_use_cases import (
    AttachUploadedImageUseCase,
    GenerateImageReviewCandidatesUseCase,
    GetActiveImageReviewUseCase,
    PublishImageReviewUseCase,
    SelectImageCandidateUseCase,
    SkipImageReviewItemUseCase,
    StartImageReviewUseCase,
    UpdateImageReviewPromptUseCase,
)
from englishbot.application.review_use_cases import CheckMorningReviewUseCase, ReviewCheckResult
from englishbot.application.services import (
    AnswerChecker,
    DiscardActiveSessionUseCase,
    GetActiveSessionUseCase,
    GetCurrentQuestionUseCase,
    ListLessonsByTopicUseCase,
    ListTopicsUseCase,
    QuestionFactory,
    SessionSummaryCalculator,
    StartTrainingSessionUseCase,
    SubmitAnswerUseCase,
    TrainingFacade,
    UnseenFirstWordSelector,
    ValidateTopicLessonUseCase,
)
from englishbot.application.training_scenarios import TrainingScenarioController, UserScreen
from englishbot.domain.add_words_models import AddWordsApprovalResult, AddWordsFlowState
from englishbot.domain.image_review_models import ImageCandidate, ImageReviewFlowState
from englishbot.domain.models import Lesson, Topic, TrainingMode, VocabularyItem
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import LessonExtractionClient
from englishbot.importing.models import ExtractedVocabularyItemDraft, LessonExtractionDraft
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.repositories import (
    InMemoryAddWordsFlowRepository,
    InMemoryImageReviewFlowRepository,
    InMemoryLessonRepository,
    InMemorySessionRepository,
    InMemoryTopicRepository,
    InMemoryUserProgressRepository,
    InMemoryVocabularyRepository,
)
from englishbot.infrastructure.sqlite_store import SQLiteContentStore
from englishbot.presentation.add_words_text import format_draft_preview


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


class FakeImageCandidateGenerator:
    def generate_candidates(
        self,
        *,
        topic_id: str,
        item_id: str,
        english_word: str,
        prompt: str,
        assets_dir: Path,
        model_names: tuple[str, ...],
    ) -> list[ImageCandidate]:
        candidates: list[ImageCandidate] = []
        for model_name in model_names:
            filename = f"{item_id}--{model_name}.png"
            output_path = assets_dir / topic_id / "review" / filename
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(f"{english_word}|{model_name}|{prompt}".encode())
            candidates.append(
                ImageCandidate(
                    model_name=model_name,
                    image_ref=str(output_path).replace("\\", "/"),
                    output_path=output_path,
                    prompt=prompt,
                )
            )
        return candidates


def build_import_draft(
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


def _default_topics() -> list[Topic]:
    return [
        Topic(id="weather", title="Weather"),
        Topic(id="seasons", title="Seasons"),
    ]


def _default_lessons() -> list[Lesson]:
    return [
        Lesson(id="lesson-1", title="Lesson 1", topic_id="weather"),
        Lesson(id="lesson-2", title="Lesson 2", topic_id="weather"),
    ]


def _default_items() -> list[VocabularyItem]:
    return [
        VocabularyItem(
            id="1",
            english_word="sun",
            translation="солнце",
            topic_id="weather",
            lesson_id="lesson-1",
        ),
        VocabularyItem(
            id="2",
            english_word="rain",
            translation="дождь",
            topic_id="weather",
            lesson_id="lesson-1",
        ),
        VocabularyItem(
            id="3",
            english_word="cloud",
            translation="облако",
            topic_id="weather",
            lesson_id="lesson-2",
        ),
        VocabularyItem(
            id="4",
            english_word="wind",
            translation="ветер",
            topic_id="weather",
            lesson_id="lesson-2",
        ),
        VocabularyItem(
            id="5",
            english_word="spring",
            translation="весна",
            topic_id="seasons",
        ),
        VocabularyItem(
            id="6",
            english_word="winter",
            translation="зима",
            topic_id="seasons",
        ),
    ]


class AppHarness:
    def __init__(
        self,
        *,
        content_dir: Path,
        import_drafts: list[LessonExtractionDraft | object] | None = None,
    ) -> None:
        self.content_dir = content_dir
        self.db_path = content_dir / "englishbot.db"
        self.content_store = SQLiteContentStore(db_path=self.db_path)
        self.clock = FixedClock(datetime(2026, 3, 25, 8, 0, tzinfo=UTC))
        self.screen: UserScreen | None = None
        self.flow: AddWordsFlowState | None = None
        self.approval: AddWordsApprovalResult | None = None
        self.image_review_flow: ImageReviewFlowState | None = None
        self.image_review_output_path: Path | None = None
        self.review: ReviewCheckResult | None = None
        self.last_import_preview: str | None = None
        self._build_learning_stack(
            topics=_default_topics(),
            lessons=_default_lessons(),
            items=_default_items(),
        )
        self._build_import_stack(import_drafts or [build_import_draft()])

    def when_user_starts_learning(self, *, user_id: int = 1) -> AppHarness:
        self.screen = self.training_controller.start(user_id=user_id)
        return self

    def when_user_selects_topic(self, topic_id: str) -> AppHarness:
        self.screen = self.training_controller.choose_topic(topic_id=topic_id)
        return self

    def when_user_selects_lesson(
        self,
        *,
        topic_id: str,
        lesson_id: str | None,
    ) -> AppHarness:
        self.screen = self.training_controller.choose_lesson(topic_id=topic_id, lesson_id=lesson_id)
        return self

    def when_user_selects_mode(
        self,
        *,
        topic_id: str,
        lesson_id: str | None,
        mode: TrainingMode,
        user_id: int = 1,
        session_size: int = 2,
    ) -> AppHarness:
        self.screen = self.training_controller.choose_mode(
            user_id=user_id,
            topic_id=topic_id,
            lesson_id=lesson_id,
            mode=mode,
            session_size=session_size,
        )
        return self

    def when_user_answers(self, answer: str, *, user_id: int = 1) -> AppHarness:
        self.screen = self.training_controller.answer(user_id=user_id, answer=answer)
        return self

    def when_learning_is_interrupted(self, *, user_id: int = 1) -> AppHarness:
        self.training_service.discard_active_session(user_id=user_id)
        self.screen = None
        return self

    def when_time_advances(self, *, hours: int = 0, minutes: int = 0) -> AppHarness:
        self.clock.advance(delta=timedelta(hours=hours, minutes=minutes))
        return self

    def when_morning_review_trigger_runs(self, *, user_id: int = 1) -> AppHarness:
        self.review = self.review_use_case.execute(user_id=user_id)
        return self

    def when_editor_imports_teacher_text(
        self,
        *,
        raw_text: str,
        user_id: int = 100,
    ) -> AppHarness:
        self.flow = self.start_add_words.execute(user_id=user_id, raw_text=raw_text)
        self.last_import_preview = format_draft_preview(self.flow.draft_result)
        return self

    def when_editor_edits_import_draft(
        self,
        *,
        edited_text: str,
        user_id: int = 100,
    ) -> AppHarness:
        flow = self._require_flow()
        self.flow = self.apply_add_words_edit.execute(
            user_id=user_id,
            flow_id=flow.flow_id,
            edited_text=edited_text,
        )
        self.last_import_preview = format_draft_preview(self.flow.draft_result)
        return self

    def when_editor_regenerates_import_draft(self, *, user_id: int = 100) -> AppHarness:
        flow = self._require_flow()
        self.flow = self.regenerate_add_words.execute(user_id=user_id, flow_id=flow.flow_id)
        self.last_import_preview = format_draft_preview(self.flow.draft_result)
        return self

    def when_editor_approves_import(
        self,
        *,
        user_id: int = 100,
        output_path: Path | None = None,
    ) -> AppHarness:
        flow = self._require_flow()
        self.approval = self.approve_add_words.execute(
            user_id=user_id,
            flow_id=flow.flow_id,
            output_path=output_path,
        )
        self.flow = None
        return self

    def when_editor_starts_image_review(
        self,
        *,
        user_id: int = 100,
        model_names: tuple[str, ...] = ("dreamshaper", "realistic-vision"),
    ) -> AppHarness:
        if self.approval is None:
            raise AssertionError("No approved import is available.")
        self.image_review_flow = self.start_image_review.execute(
            user_id=user_id,
            draft=self.approval.import_result.draft,
            model_names=model_names,
        )
        self.image_review_flow = self.generate_image_review_candidates.execute(
            user_id=user_id,
            flow_id=self.image_review_flow.flow_id,
        )
        return self

    def when_editor_selects_image_candidate(
        self,
        *,
        item_id: str,
        candidate_index: int,
        user_id: int = 100,
    ) -> AppHarness:
        flow = self._require_image_review_flow()
        self.image_review_flow = self.select_image_candidate.execute(
            user_id=user_id,
            flow_id=flow.flow_id,
            item_id=item_id,
            candidate_index=candidate_index,
        )
        if self.image_review_flow is not None and not self.image_review_flow.completed:
            self.image_review_flow = self.generate_image_review_candidates.execute(
                user_id=user_id,
                flow_id=self.image_review_flow.flow_id,
            )
        return self

    def when_editor_skips_image_item(
        self,
        *,
        item_id: str,
        user_id: int = 100,
    ) -> AppHarness:
        flow = self._require_image_review_flow()
        self.image_review_flow = self.skip_image_item.execute(
            user_id=user_id,
            flow_id=flow.flow_id,
            item_id=item_id,
        )
        if self.image_review_flow is not None and not self.image_review_flow.completed:
            self.image_review_flow = self.generate_image_review_candidates.execute(
                user_id=user_id,
                flow_id=self.image_review_flow.flow_id,
            )
        return self

    def when_editor_updates_image_prompt(
        self,
        *,
        item_id: str,
        prompt: str,
        user_id: int = 100,
    ) -> AppHarness:
        flow = self._require_image_review_flow()
        self.image_review_flow = self.update_image_review_prompt.execute(
            user_id=user_id,
            flow_id=flow.flow_id,
            item_id=item_id,
            prompt=prompt,
        )
        self.image_review_flow = self.generate_image_review_candidates.execute(
            user_id=user_id,
            flow_id=self.image_review_flow.flow_id,
        )
        return self

    def when_editor_publishes_image_review(
        self,
        *,
        output_path: Path,
        user_id: int = 100,
    ) -> AppHarness:
        flow = self._require_image_review_flow()
        self.image_review_output_path = self.publish_image_review.execute(
            user_id=user_id,
            flow_id=flow.flow_id,
            output_path=output_path,
        )
        self.image_review_flow = None
        return self

    def when_editor_attaches_uploaded_image(
        self,
        *,
        item_id: str,
        image_ref: str,
        output_path: Path,
        user_id: int = 100,
    ) -> AppHarness:
        flow = self._require_image_review_flow()
        self.image_review_flow = self.attach_uploaded_image.execute(
            user_id=user_id,
            flow_id=flow.flow_id,
            item_id=item_id,
            image_ref=image_ref,
            output_path=output_path,
        )
        return self

    def when_learning_content_is_reloaded(
        self,
        *,
        include_default_content: bool = False,
    ) -> AppHarness:
        self.content_store.import_json_directories([self.content_dir], replace=True)
        topics = self.content_store.list_topics()
        items = self.content_store.list_all_vocabulary()
        loaded_lessons: list[Lesson] = []
        for topic in topics:
            loaded_lessons.extend(self.content_store.list_lessons_by_topic(topic.id))
        lessons = loaded_lessons
        if include_default_content:
            topics = [*_default_topics(), *topics]
            lessons = [*_default_lessons(), *lessons]
            items = [*_default_items(), *items]
        self._build_learning_stack(topics=topics, lessons=lessons, items=items)
        return self

    def active_session_info(self, *, user_id: int = 1):
        return self.training_service.get_active_session(user_id=user_id)

    def _build_learning_stack(
        self,
        *,
        topics: list[Topic],
        lessons: list[Lesson],
        items: list[VocabularyItem],
    ) -> None:
        rng = random.Random(7)
        topic_repository = InMemoryTopicRepository(topics)
        lesson_repository = InMemoryLessonRepository(lessons)
        vocabulary_repository = InMemoryVocabularyRepository(items)
        progress_repository = InMemoryUserProgressRepository()
        session_repository = InMemorySessionRepository()
        question_factory = QuestionFactory(rng)
        get_current_question = GetCurrentQuestionUseCase(
            vocabulary_repository=vocabulary_repository,
            session_repository=session_repository,
            question_factory=question_factory,
        )
        self.training_service = TrainingFacade(
            list_topics=ListTopicsUseCase(topic_repository),
            list_lessons_by_topic=ListLessonsByTopicUseCase(lesson_repository),
            start_training_session=StartTrainingSessionUseCase(
                topic_repository=topic_repository,
                vocabulary_repository=vocabulary_repository,
                progress_repository=progress_repository,
                session_repository=session_repository,
                validate_topic_lesson=ValidateTopicLessonUseCase(lesson_repository),
                word_selector=UnseenFirstWordSelector(rng),
                question_factory=question_factory,
            ),
            get_active_session=GetActiveSessionUseCase(session_repository),
            get_current_question=get_current_question,
            discard_active_session=DiscardActiveSessionUseCase(session_repository),
            submit_answer=SubmitAnswerUseCase(
                progress_repository=progress_repository,
                session_repository=session_repository,
                get_current_question=get_current_question,
                answer_checker=AnswerChecker(),
                summary_calculator=SessionSummaryCalculator(),
                clock=self.clock,
            ),
        )
        self.training_controller = TrainingScenarioController(self.training_service)
        self.review_use_case = CheckMorningReviewUseCase(
            progress_repository=progress_repository,
            vocabulary_repository=vocabulary_repository,
            clock=self.clock,
        )

    def _build_import_stack(self, import_drafts: list[LessonExtractionDraft | object]) -> None:
        extraction_client: LessonExtractionClient = SequenceLessonExtractionClient(import_drafts)
        pipeline = LessonImportPipeline(
            extraction_client=extraction_client,
            validator=LessonExtractionValidator(),
            canonicalizer=DraftToContentPackCanonicalizer(),
            writer=JsonContentPackWriter(),
            image_prompt_enricher=FakeImagePromptEnricher(),  # type: ignore[arg-type]
        )
        repository = InMemoryAddWordsFlowRepository()
        harness = AddWordsFlowHarness(
            pipeline=pipeline,
            validator=LessonExtractionValidator(),
            writer=JsonContentPackWriter(),
            custom_content_dir=self.content_dir,
            content_store=self.content_store,
        )
        self.start_add_words = StartAddWordsFlowUseCase(
            harness=harness,
            flow_repository=repository,
        )
        self.apply_add_words_edit = ApplyAddWordsEditUseCase(
            harness=harness,
            flow_repository=repository,
        )
        self.regenerate_add_words = RegenerateAddWordsDraftUseCase(
            harness=harness,
            flow_repository=repository,
        )
        self.approve_add_words = ApproveAddWordsDraftUseCase(
            harness=harness,
            flow_repository=repository,
        )
        self.cancel_add_words = CancelAddWordsFlowUseCase(repository)
        self.get_active_add_words = GetActiveAddWordsFlowUseCase(repository)
        image_review_repository = InMemoryImageReviewFlowRepository()
        image_review_harness = ImageReviewFlowHarness(
            canonicalizer=DraftToContentPackCanonicalizer(),
            writer=JsonContentPackWriter(),
            candidate_generator=FakeImageCandidateGenerator(),
            assets_dir=self.content_dir / "assets",
            content_store=self.content_store,
        )
        self.start_image_review = StartImageReviewUseCase(
            harness=image_review_harness,
            repository=image_review_repository,
        )
        self.get_active_image_review = GetActiveImageReviewUseCase(image_review_repository)
        self.generate_image_review_candidates = GenerateImageReviewCandidatesUseCase(
            harness=image_review_harness,
            repository=image_review_repository,
        )
        self.select_image_candidate = SelectImageCandidateUseCase(
            harness=image_review_harness,
            repository=image_review_repository,
        )
        self.skip_image_item = SkipImageReviewItemUseCase(
            harness=image_review_harness,
            repository=image_review_repository,
        )
        self.update_image_review_prompt = UpdateImageReviewPromptUseCase(
            harness=image_review_harness,
            repository=image_review_repository,
        )
        self.attach_uploaded_image = AttachUploadedImageUseCase(
            harness=image_review_harness,
            repository=image_review_repository,
        )
        self.publish_image_review = PublishImageReviewUseCase(
            harness=image_review_harness,
            repository=image_review_repository,
        )

    def _require_flow(self) -> AddWordsFlowState:
        if self.flow is None:
            raise AssertionError("No active add-words flow.")
        return self.flow

    def _require_image_review_flow(self) -> ImageReviewFlowState:
        if self.image_review_flow is None:
            raise AssertionError("No active image review flow.")
        return self.image_review_flow
