from __future__ import annotations

import logging
from pathlib import Path

from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import LessonExtractionClient
from englishbot.importing.draft_io import JsonDraftReader, JsonDraftWriter
from englishbot.importing.enrichment import OllamaImagePromptEnricher
from englishbot.importing.models import (
    ExtractedVocabularyItemDraft,
    ImportLessonResult,
    LessonExtractionDraft,
)
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
        draft_writer: JsonDraftWriter | None = None,
        draft_reader: JsonDraftReader | None = None,
        image_prompt_enricher: OllamaImagePromptEnricher | None = None,
    ) -> None:
        self._extraction_client = extraction_client
        self._validator = validator
        self._canonicalizer = canonicalizer
        self._writer = writer
        self._draft_writer = draft_writer or JsonDraftWriter()
        self._draft_reader = draft_reader or JsonDraftReader()
        self._image_prompt_enricher = image_prompt_enricher

    @logged_service_call(
        "LessonImportPipeline.extract_draft",
        transforms={
            "raw_text": lambda value: {"text_length": len(value)},
            "output_path": lambda value: {"output_path": value},
            "intermediate_output_path": lambda value: {"intermediate_output_path": value},
        },
        include=("enrich_image_prompts",),
        result=lambda result: {
            "is_valid": result.validation.is_valid,
            "error_count": len(result.validation.errors),
            "draft_item_count": (
                len(result.draft.vocabulary_items)
                if isinstance(result.draft, LessonExtractionDraft)
                else None
            ),
        },
    )
    def extract_draft(
        self,
        *,
        raw_text: str,
        output_path: Path | None = None,
        intermediate_output_path: Path | None = None,
        enrich_image_prompts: bool = False,
    ) -> ImportLessonResult:
        draft = self._extraction_client.extract(raw_text)
        validation = self._validator.validate(draft)
        if not isinstance(draft, LessonExtractionDraft):
            logger.warning("LessonImportPipeline draft extraction returned malformed result")
            return ImportLessonResult(draft=draft, validation=validation)  # type: ignore[arg-type]
        parsed_output_path = intermediate_output_path
        if parsed_output_path is None and enrich_image_prompts and output_path is not None:
            parsed_output_path = self._default_intermediate_output_path(output_path)
        if parsed_output_path is not None:
            self._draft_writer.write(draft=draft, output_path=parsed_output_path)
        if validation.is_valid and enrich_image_prompts:
            if self._image_prompt_enricher is None:
                raise ValueError("Image prompt enrichment requested but no enricher is configured.")
            draft = self._enrich_draft_image_prompts(draft)
        if output_path is not None:
            self._draft_writer.write(draft=draft, output_path=output_path)
        return ImportLessonResult(draft=draft, validation=validation)

    @logged_service_call(
        "LessonImportPipeline.finalize_draft",
        transforms={"output_path": lambda value: {"output_path": value}},
        result=lambda result: {
            "is_valid": result.validation.is_valid,
            "error_count": len(result.validation.errors),
            "has_canonicalization": result.canonicalization is not None,
        },
    )
    def finalize_draft(
        self,
        *,
        draft: LessonExtractionDraft,
        output_path: Path | None = None,
    ) -> ImportLessonResult:
        validation = self._validator.validate(draft)
        if not validation.is_valid:
            logger.warning(
                "LessonImportPipeline finalization validation failed errors=%s",
                len(validation.errors),
            )
            return ImportLessonResult(draft=draft, validation=validation)
        canonicalization = self._canonicalizer.convert(draft)
        if output_path is not None:
            self._writer.write(content_pack=canonicalization.content_pack, output_path=output_path)
        return ImportLessonResult(
            draft=draft,
            validation=validation,
            canonicalization=canonicalization,
        )

    @logged_service_call(
        "LessonImportPipeline.finalize_draft_from_file",
        transforms={
            "input_path": lambda value: {"input_path": value},
            "output_path": lambda value: {"output_path": value},
        },
        result=lambda result: {
            "is_valid": result.validation.is_valid,
            "error_count": len(result.validation.errors),
            "has_canonicalization": result.canonicalization is not None,
        },
    )
    def finalize_draft_from_file(
        self,
        *,
        input_path: Path,
        output_path: Path | None = None,
    ) -> ImportLessonResult:
        draft = self._draft_reader.read(input_path=input_path)
        return self.finalize_draft(draft=draft, output_path=output_path)

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
        draft_result = self.extract_draft(
            raw_text=raw_text,
            enrich_image_prompts=enrich_image_prompts,
        )
        if not draft_result.validation.is_valid:
            return draft_result
        return self.finalize_draft(
            draft=draft_result.draft,
            output_path=output_path,
        )

    @logged_service_call(
        "LessonImportPipeline.enrich_draft_image_prompts",
        transforms={"output_path": lambda value: {"output_path": value}},
        result=lambda result: {
            "is_valid": result.validation.is_valid,
            "error_count": len(result.validation.errors),
            "draft_item_count": len(result.draft.vocabulary_items),
        },
    )
    def enrich_draft_image_prompts(
        self,
        *,
        draft: LessonExtractionDraft,
        output_path: Path | None = None,
    ) -> ImportLessonResult:
        if self._image_prompt_enricher is None:
            raise ValueError("Image prompt enrichment requested but no enricher is configured.")
        enriched_draft = self._enrich_draft_image_prompts(draft)
        validation = self._validator.validate(enriched_draft)
        if output_path is not None:
            self._draft_writer.write(draft=enriched_draft, output_path=output_path)
        return ImportLessonResult(draft=enriched_draft, validation=validation)

    def _enrich_draft_image_prompts(self, draft: LessonExtractionDraft) -> LessonExtractionDraft:
        enriched_items_data = self._image_prompt_enricher.enrich(
            topic_title=draft.topic_title,
            vocabulary_items=[
                {
                    "id": item.item_id or item.english_word,
                    "english_word": item.english_word,
                    "translation": item.translation,
                }
                for item in draft.vocabulary_items
            ],
        )
        prompts_by_key = {
            str(item.get("id", "")).strip(): str(item.get("image_prompt", "")).strip()
            for item in enriched_items_data
            if str(item.get("image_prompt", "")).strip()
        }
        prompts_by_word = {
            str(item.get("english_word", "")).strip().lower(): (
                str(item.get("image_prompt", "")).strip()
            )
            for item in enriched_items_data
            if str(item.get("english_word", "")).strip()
            and str(item.get("image_prompt", "")).strip()
        }
        return LessonExtractionDraft(
            topic_title=draft.topic_title,
            lesson_title=draft.lesson_title,
            vocabulary_items=[
                ExtractedVocabularyItemDraft(
                    item_id=item.item_id,
                    english_word=item.english_word,
                    translation=item.translation,
                    source_fragment=item.source_fragment,
                    notes=item.notes,
                    image_prompt=(
                        prompts_by_key.get(item.item_id or item.english_word)
                        or prompts_by_word.get(item.english_word.strip().lower())
                        or item.image_prompt
                    ),
                )
                for item in draft.vocabulary_items
            ],
            warnings=list(draft.warnings),
            unparsed_lines=list(draft.unparsed_lines),
            confidence_notes=list(draft.confidence_notes),
        )

    def _default_intermediate_output_path(self, output_path: Path) -> Path:
        return output_path.with_name(f"{output_path.stem}.parsed{output_path.suffix}")
