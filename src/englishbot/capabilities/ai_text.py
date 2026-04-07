from __future__ import annotations

import logging

from englishbot.importing.runtime import build_lesson_import_pipeline
from englishbot.importing.clients import OllamaLessonExtractionClient
from englishbot.importing.smart_parsing import (
    DisabledSmartLessonParsingGateway,
    OllamaSmartLessonParsingGateway,
)


logger = logging.getLogger(__name__)


def log_ai_text_capability_settings(*, settings) -> None:
    ai_text = settings.ai_text
    logger.info(
        "AI text capability settings enabled=%s model=%s model_file_path=%s "
        "trace_file_path=%s base_url=%s timeout_sec=%s extraction_mode=%s "
        "temperature=%s top_p=%s num_predict=%s extract_line_prompt_path=%s "
        "extract_text_prompt_path=%s image_prompt_path=%s",
        ai_text.enabled,
        ai_text.model,
        ai_text.model_file_path,
        ai_text.trace_file_path,
        ai_text.base_url,
        ai_text.timeout_sec,
        ai_text.extraction_mode,
        ai_text.temperature,
        ai_text.top_p,
        ai_text.num_predict,
        ai_text.extract_line_prompt_path,
        ai_text.extract_text_prompt_path,
        ai_text.image_prompt_path,
    )


def build_smart_parsing_gateway(*, settings, config_service):
    ai_text = settings.ai_text
    if not ai_text.enabled:
        return DisabledSmartLessonParsingGateway()
    return OllamaSmartLessonParsingGateway(
        OllamaLessonExtractionClient(
            config_service=config_service,
            model=ai_text.model,
            model_file_path=ai_text.model_file_path,
            base_url=ai_text.base_url,
            timeout=ai_text.timeout_sec,
            trace_file_path=ai_text.trace_file_path,
            extraction_mode=ai_text.extraction_mode,
            temperature=ai_text.temperature,
            top_p=ai_text.top_p,
            num_predict=ai_text.num_predict,
            extract_line_prompt_path=ai_text.extract_line_prompt_path,
            extract_text_prompt_path=ai_text.extract_text_prompt_path,
        )
    )


def build_ai_text_import_pipeline(*, settings, config_service):
    ai_text = settings.ai_text
    return build_lesson_import_pipeline(
        config_service=config_service,
        ollama_enabled=ai_text.enabled,
        ollama_model=ai_text.model,
        ollama_model_file_path=ai_text.model_file_path,
        ollama_base_url=ai_text.base_url,
        ollama_timeout_sec=ai_text.timeout_sec,
        ollama_trace_file_path=ai_text.trace_file_path,
        ollama_extraction_mode=ai_text.extraction_mode,
        ollama_temperature=ai_text.temperature,
        ollama_top_p=ai_text.top_p,
        ollama_num_predict=ai_text.num_predict,
        ollama_extract_line_prompt_path=ai_text.extract_line_prompt_path,
        ollama_extract_text_prompt_path=ai_text.extract_text_prompt_path,
        ollama_image_prompt_path=ai_text.image_prompt_path,
    )


def register_ai_text_capability(*, app, settings, config_service) -> object:
    log_ai_text_capability_settings(settings=settings)
    smart_parsing_gateway = build_smart_parsing_gateway(
        settings=settings,
        config_service=config_service,
    )
    lesson_import_pipeline = build_ai_text_import_pipeline(
        settings=settings,
        config_service=config_service,
    )
    app.bot_data["smart_parsing_gateway"] = smart_parsing_gateway
    app.bot_data["lesson_import_pipeline"] = lesson_import_pipeline
    return lesson_import_pipeline
