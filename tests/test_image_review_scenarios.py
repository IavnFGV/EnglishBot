import json
from pathlib import Path

from tests.support.app_harness import AppHarness, build_import_draft


def test_editor_can_review_two_image_candidates_per_word_and_publish_selected_images(
    tmp_path: Path,
) -> None:
    app = AppHarness(
        content_dir=tmp_path,
        import_drafts=[
            build_import_draft(
                topic_title="Fairy Tales",
                lesson_title="Story Creatures",
                items=[("Dragon", "дракон"), ("Fairy", "фея")],
            )
        ],
    )

    app.when_editor_imports_teacher_text(raw_text="Fairy Tales source")
    app.when_editor_approves_import(output_path=tmp_path / "fairy-tales-draft-approved.json")
    app.when_editor_starts_image_review()

    assert app.image_review_flow is not None
    assert len(app.image_review_flow.items) == 2
    first_item = app.image_review_flow.current_item
    assert first_item is not None
    assert first_item.english_word == "Dragon"
    assert [candidate.model_name for candidate in first_item.candidates] == [
        "dreamshaper",
        "realistic-vision",
    ]

    app.when_editor_selects_image_candidate(item_id=first_item.item_id, candidate_index=1)

    assert app.image_review_flow is not None
    second_item = app.image_review_flow.current_item
    assert second_item is not None
    assert second_item.english_word == "Fairy"

    app.when_editor_skips_image_item(item_id=second_item.item_id)
    output_path = tmp_path / "fairy-tales-with-images.json"
    app.when_editor_publishes_image_review(output_path=output_path)

    assert app.image_review_output_path == output_path
    content = json.loads(output_path.read_text(encoding="utf-8"))
    first_item_data = content["vocabulary_items"][0]
    second_item_data = content["vocabulary_items"][1]
    assert first_item_data["image_ref"].endswith("dragon--realistic-vision.png")
    assert second_item_data["image_ref"] is None


def test_image_review_selection_advances_one_word_at_a_time(
    tmp_path: Path,
) -> None:
    app = AppHarness(
        content_dir=tmp_path,
        import_drafts=[
            build_import_draft(
                topic_title="Fairy Tales",
                items=[("Dragon", "дракон"), ("Fairy", "фея"), ("Wizard", "волшебник")],
            )
        ],
    )

    app.when_editor_imports_teacher_text(raw_text="Fairy Tales source")
    app.when_editor_approves_import(output_path=tmp_path / "approved.json")
    app.when_editor_starts_image_review(
        model_names=("dreamshaper", "realistic-vision", "sd15")
    )

    assert app.image_review_flow is not None
    assert app.image_review_flow.current_index == 0
    assert app.image_review_flow.current_item is not None
    assert app.image_review_flow.current_item.english_word == "Dragon"

    app.when_editor_selects_image_candidate(
        item_id=app.image_review_flow.current_item.item_id,
        candidate_index=0,
    )
    assert app.image_review_flow is not None
    assert app.image_review_flow.current_index == 1
    assert app.image_review_flow.current_item is not None
    assert app.image_review_flow.current_item.english_word == "Fairy"

    app.when_editor_selects_image_candidate(
        item_id=app.image_review_flow.current_item.item_id,
        candidate_index=1,
    )
    assert app.image_review_flow is not None
    assert app.image_review_flow.current_index == 2
    assert app.image_review_flow.current_item is not None
    assert app.image_review_flow.current_item.english_word == "Wizard"


def test_editor_can_edit_prompt_and_regenerate_current_image_candidates(
    tmp_path: Path,
) -> None:
    app = AppHarness(
        content_dir=tmp_path,
        import_drafts=[
            build_import_draft(
                topic_title="Fairy Tales",
                items=[("Dragon", "дракон")],
            )
        ],
    )

    app.when_editor_imports_teacher_text(raw_text="Fairy Tales source")
    app.when_editor_approves_import(output_path=tmp_path / "approved.json")
    app.when_editor_starts_image_review()

    assert app.image_review_flow is not None
    item = app.image_review_flow.current_item
    assert item is not None
    original_prompt = item.prompt

    app.when_editor_updates_image_prompt(
        item_id=item.item_id,
        prompt=(
            "simple cartoon illustration of a red dragon, centered, "
            "white background, bright colors, no text"
        ),
    )

    assert app.image_review_flow is not None
    updated_item = app.image_review_flow.current_item
    assert updated_item is not None
    assert updated_item.prompt != original_prompt
    assert updated_item.prompt.startswith("simple cartoon illustration of a red dragon")
    assert [candidate.prompt for candidate in updated_item.candidates] == [
        updated_item.prompt,
        updated_item.prompt,
    ]


def test_editor_can_attach_uploaded_image_for_current_item(
    tmp_path: Path,
) -> None:
    app = AppHarness(
        content_dir=tmp_path,
        import_drafts=[
            build_import_draft(
                topic_title="Fairy Tales",
                items=[("Dragon", "дракон"), ("Fairy", "фея")],
            )
        ],
    )

    app.when_editor_imports_teacher_text(raw_text="Fairy Tales source")
    app.when_editor_approves_import(output_path=tmp_path / "approved.json")
    app.when_editor_starts_image_review()

    uploaded_path = tmp_path / "assets" / "fairy-tales" / "review" / "dragon--user-upload.jpg"
    uploaded_path.parent.mkdir(parents=True, exist_ok=True)
    uploaded_path.write_bytes(b"jpg")

    assert app.image_review_flow is not None
    item = app.image_review_flow.current_item
    assert item is not None

    app.when_editor_attaches_uploaded_image(
        item_id=item.item_id,
        image_ref="assets/fairy-tales/review/dragon--user-upload.jpg",
        output_path=uploaded_path,
    )

    assert app.image_review_flow is not None
    assert app.image_review_flow.current_index == 1
    content_pack = app.image_review_flow.content_pack
    assert content_pack["vocabulary_items"][0]["image_ref"].endswith("dragon--user-upload.jpg")
