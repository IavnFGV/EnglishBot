from pathlib import Path
from types import SimpleNamespace

import pytest

from englishbot.bot import (
    add_words_approve_draft_handler,
    add_words_text_handler,
    image_review_attach_photo_handler,
    image_review_edit_prompt_handler,
    image_review_photo_handler,
)
from englishbot.domain.add_words_models import AddWordsFlowState
from englishbot.domain.image_review_models import (
    ImageCandidate,
    ImageReviewFlowState,
    ImageReviewItem,
)
from englishbot.importing.models import (
    ExtractedVocabularyItemDraft,
    ImportLessonResult,
    LessonExtractionDraft,
    ValidationResult,
)


class _FakeCallbackMessage:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.reply_text_calls: list[str] = []
        self.reply_text_markups: list[object] = []
        self.reply_photo_captions: list[str] = []
        self.replies: list[SimpleNamespace] = []

    async def reply_text(self, text: str, reply_markup=None):  # noqa: ARG002
        self.reply_text_calls.append(text)
        self.reply_text_markups.append(reply_markup)
        sent = _FakeSentMessage(text=text, message_id=len(self.reply_text_calls))
        self.replies.append(sent)
        return sent

    async def reply_photo(self, photo, caption=None, reply_markup=None):  # noqa: ARG002
        self.reply_photo_captions.append(caption or "")
        photo.read()
        return SimpleNamespace(message_id=100 + len(self.reply_photo_captions))


class _FakeSentMessage(SimpleNamespace):
    def __init__(self, text: str, message_id: int) -> None:
        super().__init__(text=text, message_id=message_id)
        self.edits: list[str] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:  # noqa: ARG002
        self.edits.append(text)
        self.text = text


class _FakeQuery:
    def __init__(self, data: str, message: _FakeCallbackMessage) -> None:
        self.data = data
        self.message = message
        self.edits: list[str] = []

    async def answer(self) -> None:
        return None

    async def edit_message_text(self, text: str, reply_markup=None) -> None:  # noqa: ARG002
        self.edits.append(text)


class _FakeGetActiveFlowUseCase:
    def __init__(self, flow: AddWordsFlowState) -> None:
        self._flow = flow

    def execute(self, *, user_id: int):  # noqa: ARG002
        return self._flow


class _FakeCancelAddWordsUseCase:
    def execute(self, *, user_id: int) -> None:  # noqa: ARG002
        return None


class _FakeSaveApprovedDraftUseCase:
    def __init__(self, flow: AddWordsFlowState) -> None:
        self._flow = flow

    def execute(self, *, user_id: int, flow_id: str, output_path=None):  # noqa: ARG002
        assert flow_id == self._flow.flow_id
        updated = AddWordsFlowState(
            flow_id=self._flow.flow_id,
            editor_user_id=self._flow.editor_user_id,
            raw_text=self._flow.raw_text,
            draft_result=self._flow.draft_result,
            stage="draft_saved",
            draft_output_path=Path("content/custom/fairy-tales.draft.json"),
        )
        return updated


class _FakeGenerateAddWordsImagePromptsUseCase:
    def __init__(self, flow: AddWordsFlowState) -> None:
        self._flow = flow

    def execute(self, *, user_id: int, flow_id: str):  # noqa: ARG002
        assert flow_id == self._flow.flow_id
        draft = LessonExtractionDraft(
            topic_title=self._flow.draft_result.draft.topic_title,
            lesson_title=self._flow.draft_result.draft.lesson_title,
            vocabulary_items=[
                ExtractedVocabularyItemDraft(
                    english_word="Dragon",
                    translation="дракон",
                    source_fragment="Dragon — дракон",
                    image_prompt="Prompt for Dragon",
                )
            ],
        )
        return AddWordsFlowState(
            flow_id=self._flow.flow_id,
            editor_user_id=self._flow.editor_user_id,
            raw_text=self._flow.raw_text,
            draft_result=ImportLessonResult(draft=draft, validation=ValidationResult(errors=[])),
            stage="prompts_generated",
            draft_output_path=Path("content/custom/fairy-tales.draft.json"),
        )


class _FakeStartImageReviewUseCase:
    def __init__(self, flow: ImageReviewFlowState) -> None:
        self._flow = flow

    def execute(self, *, user_id: int, draft, model_names=None):  # noqa: ARG002
        return self._flow


class _FakeGenerateImageReviewCandidatesUseCase:
    def __init__(self, flow: ImageReviewFlowState) -> None:
        self._flow = flow

    def execute(self, *, user_id: int, flow_id: str):  # noqa: ARG002
        assert flow_id == self._flow.flow_id
        return self._flow


class _FakeGetActiveImageReviewUseCase:
    def __init__(self, flow: ImageReviewFlowState) -> None:
        self._flow = flow

    def execute(self, *, user_id: int):  # noqa: ARG002
        return self._flow


class _FakeUpdateImageReviewPromptUseCase:
    def __init__(self, flow: ImageReviewFlowState) -> None:
        self._flow = flow
        self.updated_prompt: str | None = None

    def execute(self, *, user_id: int, flow_id: str, item_id: str, prompt: str):  # noqa: ARG002
        assert flow_id == self._flow.flow_id
        assert item_id == self._flow.current_item.item_id
        self.updated_prompt = prompt
        return ImageReviewFlowState(
            flow_id=self._flow.flow_id,
            editor_user_id=self._flow.editor_user_id,
            content_pack=self._flow.content_pack,
            items=[
                ImageReviewItem(
                    item_id=self._flow.items[0].item_id,
                    english_word=self._flow.items[0].english_word,
                    translation=self._flow.items[0].translation,
                    prompt=prompt,
                    candidates=[],
                )
            ],
        )


class _FakeMarkImageReviewStartedUseCase:
    def execute(self, *, user_id: int, flow_id: str, image_review_flow_id: str):  # noqa: ARG002
        assert flow_id == "flow123"
        assert image_review_flow_id == "review123"
        return None


class _FakeAttachUploadedImageUseCase:
    def __init__(self, flow: ImageReviewFlowState) -> None:
        self._flow = flow
        self.image_ref: str | None = None

    def execute(  # noqa: PLR0913
        self,
        *,
        user_id: int,  # noqa: ARG002
        flow_id: str,
        item_id: str,
        image_ref: str,
        output_path: Path,  # noqa: ARG002
    ) -> ImageReviewFlowState:
        assert flow_id == self._flow.flow_id
        assert item_id == self._flow.current_item.item_id
        self.image_ref = image_ref
        return ImageReviewFlowState(
            flow_id=self._flow.flow_id,
            editor_user_id=self._flow.editor_user_id,
            content_pack={
                "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
                "vocabulary_items": [{"id": "dragon", "image_ref": image_ref}],
            },
            items=self._flow.items,
            current_index=1,
        )


class _FakePublishImageReviewUseCase:
    def execute(self, *, user_id: int, flow_id: str, output_path: Path):  # noqa: ARG002
        return output_path


class _FakePhotoFile:
    def __init__(self, content: bytes) -> None:
        self._content = content

    async def download_to_drive(self, custom_path: str) -> None:
        Path(custom_path).write_bytes(self._content)


class _FakePhotoSize:
    def __init__(self, content: bytes) -> None:
        self._content = content

    async def get_file(self) -> _FakePhotoFile:
        return _FakePhotoFile(self._content)


@pytest.mark.anyio
async def test_approve_draft_handler_starts_image_review_and_sends_first_step(
    tmp_path: Path,
) -> None:
    draft = LessonExtractionDraft(
        topic_title="Fairy Tales",
        vocabulary_items=[
            ExtractedVocabularyItemDraft(
                english_word="Dragon",
                translation="дракон",
                source_fragment="Dragon — дракон",
            )
        ],
    )
    add_words_flow = AddWordsFlowState(
        flow_id="flow123",
        editor_user_id=42,
        raw_text="Fairy Tales\nDragon — дракон",
        draft_result=ImportLessonResult(draft=draft, validation=ValidationResult(errors=[])),
    )
    candidate_a_path = tmp_path / "dragon-a.png"
    candidate_b_path = tmp_path / "dragon-b.png"
    candidate_c_path = tmp_path / "dragon-c.png"
    candidate_a_path.write_bytes(b"a")
    candidate_b_path.write_bytes(b"b")
    candidate_c_path.write_bytes(b"c")
    image_review_flow = ImageReviewFlowState(
        flow_id="review123",
        editor_user_id=42,
        content_pack={
            "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
            "vocabulary_items": [],
        },
        items=[
            ImageReviewItem(
                item_id="dragon",
                english_word="Dragon",
                translation="дракон",
                prompt="Prompt for Dragon",
                candidates=[
                    ImageCandidate(
                        model_name="dreamshaper",
                        image_ref="assets/fairy-tales/review/dragon--dreamshaper.png",
                        output_path=candidate_a_path,
                        prompt="Prompt for Dragon",
                    ),
                    ImageCandidate(
                        model_name="realistic-vision",
                        image_ref="assets/fairy-tales/review/dragon--realistic-vision.png",
                        output_path=candidate_b_path,
                        prompt="Prompt for Dragon",
                    ),
                    ImageCandidate(
                        model_name="sd15",
                        image_ref="assets/fairy-tales/review/dragon--sd15.png",
                        output_path=candidate_c_path,
                        prompt="Prompt for Dragon",
                    ),
                ],
            )
        ],
    )
    message = _FakeCallbackMessage(tmp_path)
    query = _FakeQuery("words:start_image_review:flow123", message)
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=42))
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "add_words_get_active_use_case": _FakeGetActiveFlowUseCase(add_words_flow),
                "add_words_cancel_use_case": _FakeCancelAddWordsUseCase(),
                "add_words_save_approved_draft_use_case": _FakeSaveApprovedDraftUseCase(
                    add_words_flow
                ),
                "add_words_generate_image_prompts_use_case": (
                    _FakeGenerateAddWordsImagePromptsUseCase(add_words_flow)
                ),
                "add_words_mark_image_review_started_use_case": (
                    _FakeMarkImageReviewStartedUseCase()
                ),
                "image_review_start_use_case": _FakeStartImageReviewUseCase(image_review_flow),
                "image_review_generate_use_case": _FakeGenerateImageReviewCandidatesUseCase(
                    image_review_flow
                ),
                "word_import_preview_message_ids": {},
            }
        ),
    )

    await add_words_approve_draft_handler(update, context)  # type: ignore[arg-type]

    assert query.edits[0] == "Saving approved draft... 0/1"
    assert "Approved draft saved." in query.edits[1]
    assert "Generating image prompts... 0/1" in query.edits[1]
    assert "Image prompts generated." in query.edits[2]
    assert "Starting image review..." in query.edits[2]
    assert any(
        text == "Generating image candidates 1/1..." for text in message.reply_text_calls
    )
    assert any("Image candidates ready 1/1" in edit for edit in message.replies[0].edits)
    review_index = next(
        index
        for index, text in enumerate(message.reply_text_calls)
        if "Reviewing images 1/1" in text
    )
    assert message.reply_text_markups[review_index] is not None
    assert "A. Dreamshaper" in message.reply_photo_captions
    assert "B. Realistic Vision" in message.reply_photo_captions
    assert "C. SD 1.5" in message.reply_photo_captions


@pytest.mark.anyio
async def test_image_review_edit_prompt_flow_accepts_new_prompt_and_regenerates_candidates(
    tmp_path: Path,
) -> None:
    candidate_a_path = tmp_path / "dragon-a.png"
    candidate_b_path = tmp_path / "dragon-b.png"
    candidate_a_path.write_bytes(b"a")
    candidate_b_path.write_bytes(b"b")
    prepared_flow = ImageReviewFlowState(
        flow_id="review123",
        editor_user_id=42,
        content_pack={"topic": {"id": "fairy-tales", "title": "Fairy Tales"}},
        items=[
            ImageReviewItem(
                item_id="dragon",
                english_word="Dragon",
                translation="дракон",
                prompt="Prompt for Dragon",
                candidates=[
                    ImageCandidate(
                        model_name="dreamshaper",
                        image_ref="assets/fairy-tales/review/dragon--dreamshaper.png",
                        output_path=candidate_a_path,
                        prompt="new prompt",
                    ),
                    ImageCandidate(
                        model_name="realistic-vision",
                        image_ref="assets/fairy-tales/review/dragon--realistic-vision.png",
                        output_path=candidate_b_path,
                        prompt="new prompt",
                    ),
                ],
            )
        ],
    )
    initial_flow = ImageReviewFlowState(
        flow_id="review123",
        editor_user_id=42,
        content_pack={"topic": {"id": "fairy-tales", "title": "Fairy Tales"}},
        items=[
            ImageReviewItem(
                item_id="dragon",
                english_word="Dragon",
                translation="дракон",
                prompt="Prompt for Dragon",
                candidates=[],
            )
        ],
    )
    prompt_message = _FakeCallbackMessage(tmp_path)
    prompt_query = _FakeQuery("words:image_edit_prompt:review123:dragon", prompt_message)
    prompt_update = SimpleNamespace(
        callback_query=prompt_query,
        effective_user=SimpleNamespace(id=42),
    )
    text_message = _FakeCallbackMessage(tmp_path)
    text_message.text = "new prompt"
    text_message.chat_id = 1
    update_prompt_use_case = _FakeUpdateImageReviewPromptUseCase(initial_flow)
    text_update = SimpleNamespace(
        effective_message=text_message,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "editor_user_ids": {42},
                "image_review_get_active_use_case": _FakeGetActiveImageReviewUseCase(initial_flow),
                "image_review_update_prompt_use_case": update_prompt_use_case,
                "image_review_generate_use_case": _FakeGenerateImageReviewCandidatesUseCase(
                    prepared_flow
                ),
            }
        ),
    )

    await image_review_edit_prompt_handler(prompt_update, context)  # type: ignore[arg-type]

    assert context.user_data["words_flow_mode"] == "awaiting_image_review_prompt_text"
    assert context.user_data["image_review_flow_id"] == "review123"
    assert context.user_data["image_review_item_id"] == "dragon"
    assert "Current prompt:\nPrompt for Dragon" in prompt_message.reply_text_calls[-1]

    await add_words_text_handler(text_update, context)  # type: ignore[arg-type]

    assert context.user_data.get("words_flow_mode") is None
    assert update_prompt_use_case.updated_prompt == "new prompt"
    assert any(
        "Prompt updated. Regenerating image candidates..." in edit
        for edit in text_message.replies[0].edits
    )
    assert any("Reviewing images 1/1" in text for text in text_message.reply_text_calls)


@pytest.mark.anyio
async def test_image_review_attach_photo_flow_saves_user_image_and_publishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("englishbot.bot.build_training_service", lambda: "training-service")
    flow = ImageReviewFlowState(
        flow_id="review123",
        editor_user_id=42,
        content_pack={
            "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
            "vocabulary_items": [{"id": "dragon", "image_ref": None}],
        },
        items=[
            ImageReviewItem(
                item_id="dragon",
                english_word="Dragon",
                translation="дракон",
                prompt="Prompt for Dragon",
                candidates=[],
            )
        ],
    )
    attach_use_case = _FakeAttachUploadedImageUseCase(flow)
    callback_message = _FakeCallbackMessage(tmp_path)
    callback_query = _FakeQuery("words:image_attach_photo:review123:dragon", callback_message)
    callback_update = SimpleNamespace(
        callback_query=callback_query,
        effective_user=SimpleNamespace(id=42),
    )
    photo_message = _FakeCallbackMessage(tmp_path)
    photo_message.photo = [_FakePhotoSize(b"jpg-bytes")]
    photo_message.chat_id = 1
    photo_update = SimpleNamespace(
        effective_message=photo_message,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "editor_user_ids": {42},
                "image_review_get_active_use_case": _FakeGetActiveImageReviewUseCase(flow),
                "image_review_attach_uploaded_image_use_case": attach_use_case,
                "image_review_publish_use_case": _FakePublishImageReviewUseCase(),
                "add_words_cancel_use_case": _FakeCancelAddWordsUseCase(),
                "word_import_preview_message_ids": {},
                "image_review_assets_dir": tmp_path / "assets",
            }
        ),
    )

    await image_review_attach_photo_handler(callback_update, context)  # type: ignore[arg-type]

    assert context.user_data["words_flow_mode"] == "awaiting_image_review_photo"
    assert context.user_data["image_review_flow_id"] == "review123"
    assert context.user_data["image_review_item_id"] == "dragon"

    await image_review_photo_handler(photo_update, context)  # type: ignore[arg-type]

    assert context.user_data.get("words_flow_mode") is None
    assert attach_use_case.image_ref is not None
    assert attach_use_case.image_ref.endswith("dragon--user-upload.jpg")
    assert (tmp_path / "assets" / "fairy-tales" / "review" / "dragon--user-upload.jpg").exists()
    assert any("Uploaded photo attached." in edit for edit in photo_message.replies[0].edits)
    assert any(
        "Image review completed and content pack published." in text
        for text in photo_message.reply_text_calls
    )
