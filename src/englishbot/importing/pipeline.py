from __future__ import annotations

import logging
from pathlib import Path

from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import LessonExtractionClient
from englishbot.importing.enrichment import OllamaImagePromptEnricher
from englishbot.importing.models import ImportLessonResult
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


class LessonImportPipeline:
    def __init__(
        self,
        *,
        extraction_client: LessonExtractionClient,
        validator: LessonExtractionValidator,
        canonicalizer: DraftToContentPackCanonicalizer,
        writer: JsonContentPackWriter,
        image_prompt_enricher: OllamaImagePromptEnricher | None = None,
    ) -> None:
        self._extraction_client = extraction_client
        self._validator = validator
        self._canonicalizer = canonicalizer
        self._writer = writer
        self._image_prompt_enricher = image_prompt_enricher

    @logged_service_call(
        "LessonImportPipeline.run",
        transforms={
            "raw_text": lambda value: {"text_length": len(value)},
            "output_path": lambda value: {"output_path": value},
        },
        include=("enrich_image_prompts",),
        result=lambda result: {
            "is_valid": result.validation.is_valid,
            "error_count": len(result.validation.errors),
            "has_canonicalization": result.canonicalization is not None,
        },
    )
    def run(
        self,
        *,
        raw_text: str,
        output_path: Path | None = None,
        enrich_image_prompts: bool = False,
    ) -> ImportLessonResult:
        draft = self._extraction_client.extract(raw_text)
        validation = self._validator.validate(draft)
        if not validation.is_valid:
            logger.warning(
                "LessonImportPipeline validation failed errors=%s",
                len(validation.errors),
            )
            return ImportLessonResult(draft=draft, validation=validation)  # type: ignore[arg-type]
        canonicalization = self._canonicalizer.convert(draft)
        if enrich_image_prompts:
            if self._image_prompt_enricher is None:
                raise ValueError("Image prompt enrichment requested but no enricher is configured.")
            pack_data = dict(canonicalization.content_pack.data)
            vocabulary_items = pack_data.get("vocabulary_items", [])
            topic_data = pack_data.get("topic", {})
            if not isinstance(vocabulary_items, list):
                raise ValueError("Canonical content pack vocabulary_items must be a list.")
            if not isinstance(topic_data, dict):
                raise ValueError("Canonical content pack topic must be an object.")
            topic_title = str(topic_data.get("title", "")).strip()
            pack_data["vocabulary_items"] = self._image_prompt_enricher.enrich(
                topic_title=topic_title,
                vocabulary_items=vocabulary_items,
            )
            canonicalization = type(canonicalization)(
                content_pack=type(canonicalization.content_pack)(data=pack_data),
                warnings=canonicalization.warnings,
            )
        if output_path is not None:
            self._writer.write(content_pack=canonicalization.content_pack, output_path=output_path)
        return ImportLessonResult(
            draft=draft,
            validation=validation,
            canonicalization=canonicalization,
        )
