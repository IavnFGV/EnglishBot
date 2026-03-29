from __future__ import annotations

import logging
import random
from pathlib import Path

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
from englishbot.config import RuntimeConfigService
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import OllamaLessonExtractionClient
from englishbot.importing.draft_io import JsonDraftReader, JsonDraftWriter
from englishbot.importing.enrichment import OllamaImagePromptEnricher
from englishbot.importing.fallback_parser import TemplateLessonFallbackParser
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.smart_parsing import OllamaSmartLessonParsingGateway
from englishbot.importing.smart_parsing import DisabledSmartLessonParsingGateway
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.repositories import (
    InMemoryLessonRepository,
    InMemorySessionRepository,
    InMemoryTopicRepository,
    InMemoryUserProgressRepository,
    InMemoryVocabularyRepository,
)
from englishbot.infrastructure.sqlite_store import (
    SQLiteContentStore,
    SQLiteLessonRepository,
    SQLiteSessionRepository,
    SQLiteTopicRepository,
    SQLiteUserProgressRepository,
    SQLiteVocabularyRepository,
)

logger = logging.getLogger(__name__)


def build_training_service(
    seed: int = 42,
    *,
    content_directories: list[Path] | None = None,
    db_path: Path | None = None,
) -> TrainingFacade:
    logger.info("Building training service with seed=%s", seed)
    rng = random.Random(seed)
    resolved_directories = content_directories or [Path("content/demo"), Path("content/custom")]
    if db_path is None:
        topic_repository = InMemoryTopicRepository([])
        lesson_repository = InMemoryLessonRepository([])
        vocabulary_repository = InMemoryVocabularyRepository([])
        progress_repository = InMemoryUserProgressRepository()
        session_repository = InMemorySessionRepository()
        store = None
    else:
        store = SQLiteContentStore(db_path=db_path)
        store.initialize()
        if not store.has_runtime_content():
            store.import_json_directories(resolved_directories, replace=True)
        topic_repository = SQLiteTopicRepository(store)
        lesson_repository = SQLiteLessonRepository(store)
        vocabulary_repository = SQLiteVocabularyRepository(store)
        progress_repository = SQLiteUserProgressRepository(store)
        session_repository = SQLiteSessionRepository(store)
    if db_path is None:
        from englishbot.infrastructure.content_loader import JsonContentPackLoader

        loader = JsonContentPackLoader()
        all_topics = []
        all_lessons = []
        all_vocabulary_items = []
        for directory in resolved_directories:
            if not directory.exists():
                logger.info("Skipping missing content directory %s", directory)
                continue
            loaded_content = loader.load_directory(directory)
            all_topics.extend(loaded_content.topics)
            all_lessons.extend(loaded_content.lessons)
            all_vocabulary_items.extend(loaded_content.vocabulary_items)
        topic_repository = InMemoryTopicRepository(all_topics)
        lesson_repository = InMemoryLessonRepository(all_lessons)
        vocabulary_repository = InMemoryVocabularyRepository(all_vocabulary_items)
    question_factory = QuestionFactory(rng)
    selector = UnseenFirstWordSelector(rng, context_provider=store) if store is not None else UnseenFirstWordSelector(rng)

    list_topics = ListTopicsUseCase(topic_repository)
    get_current_question = GetCurrentQuestionUseCase(
        vocabulary_repository=vocabulary_repository,
        session_repository=session_repository,
        question_factory=question_factory,
    )
    start_training_session = StartTrainingSessionUseCase(
        topic_repository=topic_repository,
        vocabulary_repository=vocabulary_repository,
        progress_repository=progress_repository,
        session_repository=session_repository,
        validate_topic_lesson=ValidateTopicLessonUseCase(lesson_repository),
        word_selector=selector,
        question_factory=question_factory,
    )
    submit_answer = SubmitAnswerUseCase(
        progress_repository=progress_repository,
        session_repository=session_repository,
        get_current_question=get_current_question,
        answer_checker=AnswerChecker(),
        summary_calculator=SessionSummaryCalculator(),
    )
    logger.info("Training service wiring completed")
    return TrainingFacade(
        list_topics=list_topics,
        list_lessons_by_topic=ListLessonsByTopicUseCase(lesson_repository),
        start_training_session=start_training_session,
        get_active_session=GetActiveSessionUseCase(session_repository),
        get_current_question=get_current_question,
        discard_active_session=DiscardActiveSessionUseCase(session_repository),
        submit_answer=submit_answer,
    )


def build_lesson_import_pipeline(
    *,
    config_service: RuntimeConfigService | None = None,
    ollama_enabled: bool = True,
    ollama_model: str,
    ollama_model_file_path: Path | None = None,
    ollama_base_url: str,
    ollama_timeout_sec: int = 120,
    ollama_trace_file_path: Path | None = None,
    image_prompt_timeout_sec: int = 30,
    ollama_extraction_mode: str = "line_by_line",
    ollama_temperature: float | None = None,
    ollama_top_p: float | None = None,
    ollama_num_predict: int | None = None,
    ollama_extract_line_prompt_path: Path | None = None,
    ollama_extract_text_prompt_path: Path | None = None,
    ollama_image_prompt_path: Path | None = None,
) -> LessonImportPipeline:
    logger.info(
        "Building lesson import pipeline model=%s model_file=%s base_url=%s extraction_mode=%s timeout=%s "
        "trace_file=%s temperature=%s top_p=%s num_predict=%s extract_line_prompt=%s "
        "extract_text_prompt=%s image_prompt=%s",
        ollama_model,
        ollama_model_file_path,
        ollama_base_url,
        ollama_extraction_mode,
        ollama_timeout_sec,
        ollama_trace_file_path,
        ollama_temperature,
        ollama_top_p,
        ollama_num_predict,
        ollama_extract_line_prompt_path,
        ollama_extract_text_prompt_path,
        ollama_image_prompt_path,
    )
    smart_parser = DisabledSmartLessonParsingGateway() if not ollama_enabled else None
    extraction_client = (
        None
        if not ollama_enabled
        else OllamaLessonExtractionClient(
            config_service=config_service,
            model=ollama_model,
            model_file_path=ollama_model_file_path,
            base_url=ollama_base_url,
            timeout=ollama_timeout_sec,
            trace_file_path=ollama_trace_file_path,
            extraction_mode=ollama_extraction_mode,
            temperature=ollama_temperature,
            top_p=ollama_top_p,
            num_predict=ollama_num_predict,
            extract_line_prompt_path=ollama_extract_line_prompt_path,
            extract_text_prompt_path=ollama_extract_text_prompt_path,
        )
    )
    return LessonImportPipeline(
        smart_parser=(
            smart_parser
            if smart_parser is not None
            else OllamaSmartLessonParsingGateway(extraction_client)
        ),
        fallback_parser=TemplateLessonFallbackParser(),
        validator=LessonExtractionValidator(),
        canonicalizer=DraftToContentPackCanonicalizer(),
        writer=JsonContentPackWriter(),
        draft_writer=JsonDraftWriter(),
        draft_reader=JsonDraftReader(),
        image_prompt_enricher=(
            None
            if not ollama_enabled
            else OllamaImagePromptEnricher(
                config_service=config_service,
                model=ollama_model,
                model_file_path=ollama_model_file_path,
                base_url=ollama_base_url,
                timeout=image_prompt_timeout_sec,
                temperature=ollama_temperature,
                top_p=ollama_top_p,
                num_predict=ollama_num_predict,
                prompt_path=ollama_image_prompt_path,
            )
        ),
    )
