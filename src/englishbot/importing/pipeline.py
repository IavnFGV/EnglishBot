from __future__ import annotations

import logging
from pathlib import Path

from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.clients import LessonExtractionClient
from englishbot.importing.models import ImportLessonResult
from englishbot.importing.validator import LessonExtractionValidator
from englishbot.importing.writer import JsonContentPackWriter

logger = logging.getLogger(__name__)


class LessonImportPipeline:
    def __init__(
        self,
        *,
        extraction_client: LessonExtractionClient,
        validator: LessonExtractionValidator,
        canonicalizer: DraftToContentPackCanonicalizer,
        writer: JsonContentPackWriter,
    ) -> None:
        self._extraction_client = extraction_client
        self._validator = validator
        self._canonicalizer = canonicalizer
        self._writer = writer

    def run(self, *, raw_text: str, output_path: Path | None = None) -> ImportLessonResult:
        logger.info(
            "LessonImportPipeline started text_length=%s output_path=%s",
            len(raw_text),
            output_path,
        )
        draft = self._extraction_client.extract(raw_text)
        validation = self._validator.validate(draft)
        if not validation.is_valid:
            logger.warning(
                "LessonImportPipeline validation failed errors=%s",
                len(validation.errors),
            )
            return ImportLessonResult(draft=draft, validation=validation)  # type: ignore[arg-type]
        canonicalization = self._canonicalizer.convert(draft)
        if output_path is not None:
            self._writer.write(content_pack=canonicalization.content_pack, output_path=output_path)
        logger.info("LessonImportPipeline finished successfully output_path=%s", output_path)
        return ImportLessonResult(
            draft=draft,
            validation=validation,
            canonicalization=canonicalization,
        )
