from pathlib import Path

import pytest

from tests.support.add_words_scenarios import (
    FAIRY_TALES_LESSON_TEXT,
    build_draft,
    build_driver,
    build_fairy_tales_draft,
)


def test_editor_starts_flow_and_sees_extracted_draft() -> None:
    scenario = build_driver().when_editor_starts_flow(raw_text="fairy tale words")

    assert scenario.flow is not None
    assert scenario.flow.draft_result.validation.is_valid is True
    assert scenario.flow.stage == "draft_review"
    assert [item.english_word for item in scenario.flow.draft_result.draft.vocabulary_items] == [
        "Princess",
        "Prince",
    ]


def test_editor_starts_flow_with_fairy_tales_lesson_text_and_gets_valid_twenty_item_draft() -> None:
    scenario = build_driver(drafts=[build_fairy_tales_draft()]).when_editor_starts_flow(
        raw_text=FAIRY_TALES_LESSON_TEXT
    )

    assert scenario.flow is not None
    assert scenario.flow.raw_text == FAIRY_TALES_LESSON_TEXT
    assert scenario.flow.draft_result.validation.is_valid is True
    assert len(scenario.flow.draft_result.validation.errors) == 0
    assert len(scenario.flow.draft_result.draft.vocabulary_items) == 20
    assert [
        item.english_word for item in scenario.flow.draft_result.draft.vocabulary_items[:5]
    ] == [
        "Princess",
        "Prince",
        "Castle",
        "King",
        "Queen",
    ]


def test_editor_starts_flow_with_malformed_extraction_and_falls_back_to_valid_draft() -> None:
    scenario = build_driver(drafts=[{"error": "broken extraction"}]).when_editor_starts_flow(
        raw_text=FAIRY_TALES_LESSON_TEXT
    )

    assert scenario.flow is not None
    assert scenario.flow.draft_result.validation.is_valid is True
    assert scenario.flow.draft_result.extraction_metadata is not None
    assert scenario.flow.draft_result.extraction_metadata.parse_path == "fallback"
    assert scenario.flow.draft_result.extraction_metadata.smart_parse_status == "remote_error"
    assert [item.english_word for item in scenario.flow.draft_result.draft.vocabulary_items[:3]] == [
        "Рrincess",
        "Prince",
        "Castle",
    ]


def test_editor_edits_draft_and_replaces_words() -> None:
    scenario = (
        build_driver()
        .when_editor_starts_flow()
        .when_editor_edits_draft(
            edited_text=(
                "Topic: Fairy Tales\n"
                "Lesson: Royal Family\n\n"
                "Queen: королева\n"
                "King: король\n"
            )
        )
    )

    assert scenario.flow is not None
    assert scenario.flow.draft_result.draft.lesson_title == "Royal Family"
    assert [item.english_word for item in scenario.flow.draft_result.draft.vocabulary_items] == [
        "Queen",
        "King",
    ]


def test_editor_regenerates_draft_and_gets_latest_extraction_result() -> None:
    scenario = (
        build_driver(
            drafts=[
                build_draft(items=[("Princess", "принцесса")]),
                build_draft(items=[("Dragon", "дракон")]),
            ]
        )
        .when_editor_starts_flow()
        .when_editor_regenerates_draft()
    )

    assert scenario.flow is not None
    assert [item.english_word for item in scenario.flow.draft_result.draft.vocabulary_items] == [
        "Dragon",
    ]


def test_editor_regenerate_uses_edited_text_as_current_source() -> None:
    edited_text = (
        "Topic: Fairy Tales\n"
        "Lesson: Royal Family\n\n"
        "Dragon: дракон\n"
    )
    scenario = (
        build_driver(
            drafts=[
                build_draft(items=[("Princess", "принцесса")]),
                build_draft(items=[("Dragon", "дракон")]),
            ]
        )
        .when_editor_starts_flow(raw_text="raw source text")
        .when_editor_edits_draft(edited_text=edited_text)
        .when_editor_regenerates_draft()
    )

    assert scenario.flow is not None
    assert scenario.flow.raw_text == edited_text
    assert [item.english_word for item in scenario.flow.draft_result.draft.vocabulary_items] == [
        "Dragon",
    ]


def test_editor_cancels_flow_and_old_edit_action_becomes_stale() -> None:
    scenario = build_driver().when_editor_starts_flow()
    stale_flow_id = scenario.flow.flow_id if scenario.flow is not None else ""

    scenario.when_editor_cancels_flow()

    assert scenario.get_active_flow() is None
    with pytest.raises(ValueError, match="no longer active"):
        scenario.when_editor_edits_draft(
            flow_id=stale_flow_id,
            edited_text="Topic: Fairy Tales\n\nPrincess: принцесса",
        )


def test_editor_starts_new_flow_and_old_approve_action_becomes_stale() -> None:
    scenario = build_driver()
    first_flow = scenario.when_editor_starts_flow(raw_text="first").flow
    first_flow_id = first_flow.flow_id if first_flow is not None else ""

    scenario.when_editor_starts_flow(raw_text="second")

    with pytest.raises(ValueError, match="no longer active"):
        scenario.when_editor_approves_draft(flow_id=first_flow_id)


def test_editor_cannot_approve_invalid_draft_and_flow_stays_active(tmp_path: Path) -> None:
    scenario = (
        build_driver(custom_content_dir=tmp_path)
        .when_editor_starts_flow()
        .when_editor_edits_draft(
            edited_text=(
                "Topic: Fairy Tales\n"
                "Lesson: -\n\n"
                "Princess: принцесса\n"
                "Princess: принц\n"
            )
        )
    )

    assert scenario.flow is not None
    assert scenario.flow.draft_result.validation.is_valid is False
    with pytest.raises(ValueError, match="Draft finalization failed"):
        scenario.when_editor_approves_draft(output_path=tmp_path / "broken.json")
    assert scenario.get_active_flow() is not None


def test_editor_approves_valid_draft_and_content_pack_is_written(tmp_path: Path) -> None:
    scenario = build_driver(custom_content_dir=tmp_path).when_editor_starts_flow()
    output_path = tmp_path / "fairy-tales.json"

    scenario.when_editor_approves_draft(output_path=output_path)

    assert scenario.approval is not None
    assert scenario.approval.published_topic_id == "fairy-tales"
    assert scenario.approval.output_path == output_path
    assert output_path.exists()
    assert scenario.get_active_flow() is None


def test_editor_can_save_approved_draft_then_generate_prompts_then_start_image_review(
    tmp_path: Path,
) -> None:
    scenario = (
        build_driver(custom_content_dir=tmp_path)
        .when_editor_starts_flow()
        .when_editor_saves_approved_draft(output_path=tmp_path / "fairy-tales.draft.json")
        .when_editor_generates_image_prompts()
        .when_editor_starts_image_review_task(image_review_flow_id="review-123")
    )

    assert scenario.flow is not None
    assert scenario.flow.stage == "image_review"
    assert scenario.flow.draft_output_path == tmp_path / "fairy-tales.draft.json"
    assert scenario.flow.draft_output_path.exists()
    assert scenario.flow.image_review_flow_id == "review-123"
    assert [
        item.image_prompt for item in scenario.flow.draft_result.draft.vocabulary_items
    ] == ["Prompt for Princess", "Prompt for Prince"]
