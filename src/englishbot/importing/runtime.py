from __future__ import annotations

import logging
from pathlib import Path

from englishbot.config import RuntimeConfigService
from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import OllamaLessonExtractionClient
from englishbot.importing.draft_io import JsonDraftReader, JsonDraftWriter
from englishbot.importing.enrichment import OllamaImagePromptEnricher
from englishbot.importing.fallback_parser import TemplateLessonFallbackParser
from englishbot.importing.pipeline import LessonImportPipeline
from englishbot.importing.smart_parsing import DisabledSmartLessonParsingGateway
from englishbot.importing.smart_parsing import OllamaSmartLessonParsingGateway
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter

logger = logging.getLogger(__name__)


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
