from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from englishbot.importing.canonicalizer import DraftToContentPackCanonicalizer
from englishbot.importing.models import (
    CanonicalContentPack,
    ExtractedVocabularyItemDraft,
    LessonExtractionDraft,
)
from englishbot.importing.writer import JsonContentPackWriter
from englishbot.infrastructure.sqlite_store import SQLiteContentStore
from englishbot.presentation.add_words_text import parse_edited_vocabulary_line
from englishbot.text_variants import expand_aligned_slash_variants


@dataclass(frozen=True, slots=True)
class BulkTopicImportResult:
    topic_title: str
    topic_id: str
    output_path: Path | None
    item_count: int


def parse_bulk_topic_text(text: str) -> list[LessonExtractionDraft]:
    drafts: list[LessonExtractionDraft] = []
    current_topic_title: str | None = None
    current_items: list[ExtractedVocabularyItemDraft] = []
    previous_line_was_blank = True

    def flush_current() -> None:
        nonlocal current_topic_title, current_items
        if current_topic_title is None:
            return
        if not current_items:
            raise ValueError(f"Topic '{current_topic_title}' has no vocabulary items.")
        drafts.append(
            LessonExtractionDraft(
                topic_title=current_topic_title,
                vocabulary_items=list(current_items),
            )
        )
        current_topic_title = None
        current_items = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            previous_line_was_blank = True
            continue

        explicit_topic_title = _parse_topic_header(line)
        if explicit_topic_title is not None:
            flush_current()
            current_topic_title = explicit_topic_title
            previous_line_was_blank = False
            continue

        parsed_pair = parse_edited_vocabulary_line(line)
        if parsed_pair is not None:
            if current_topic_title is None:
                raise ValueError(
                    f"Vocabulary line appears before a topic header at line {line_number}: {line}"
                )
            english_word, translation = parsed_pair
            english_variants, translation_variants = expand_aligned_slash_variants(
                english_word=english_word,
                translation=translation,
            )
            for variant, resolved_translation in zip(
                english_variants,
                translation_variants,
                strict=False,
            ):
                current_items.append(
                    ExtractedVocabularyItemDraft(
                        english_word=variant,
                        translation=resolved_translation,
                        source_fragment=f"{variant} — {resolved_translation}",
                    )
                )
            previous_line_was_blank = False
            continue

        if current_topic_title is None or previous_line_was_blank:
            flush_current()
            current_topic_title = line
            previous_line_was_blank = False
            continue

        raise ValueError(f"Could not parse line {line_number}: {line}")

    flush_current()
    if not drafts:
        raise ValueError("No topic blocks were found in the input.")
    return drafts


def write_bulk_topic_content_packs(
    *,
    drafts: list[LessonExtractionDraft],
    output_dir: Path | None = None,
    db_path: Path | None = None,
) -> list[BulkTopicImportResult]:
    canonicalizer = DraftToContentPackCanonicalizer()
    writer = JsonContentPackWriter() if output_dir is not None else None
    store = SQLiteContentStore(db_path=db_path) if db_path is not None else None
    if writer is None and store is None:
        raise ValueError("Provide at least one destination: output_dir and/or db_path.")
    if store is not None:
        store.initialize()

    results: list[BulkTopicImportResult] = []
    for draft in drafts:
        canonical = canonicalizer.convert(draft)
        content_pack = canonical.content_pack
        output_path = (
            _output_path_for_content_pack(output_dir=output_dir, content_pack=content_pack)
            if output_dir is not None
            else None
        )
        if writer is not None and output_path is not None:
            writer.write(content_pack=content_pack, output_path=output_path)
        if store is not None:
            store.upsert_content_pack(content_pack.data)
        topic = content_pack.data["topic"]
        assert isinstance(topic, dict)
        results.append(
            BulkTopicImportResult(
                topic_title=str(topic["title"]),
                topic_id=str(topic["id"]),
                output_path=output_path,
                item_count=len(content_pack.data.get("vocabulary_items", [])),
            )
        )
    return results


def _parse_topic_header(line: str) -> str | None:
    lowered = line.lower()
    if lowered.startswith("topic:"):
        topic_title = line.partition(":")[2].strip()
        return topic_title or None
    return None


def _output_path_for_content_pack(*, output_dir: Path, content_pack: CanonicalContentPack) -> Path:
    topic = content_pack.data["topic"]
    assert isinstance(topic, dict)
    topic_id = str(topic["id"]).strip()
    return output_dir / f"{topic_id}.json"
