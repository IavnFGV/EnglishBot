from pathlib import Path
from types import SimpleNamespace

import pytest

from englishbot.bot import (
    add_words_approve_auto_images_handler,
    add_words_approve_draft_handler,
    add_words_text_handler,
    image_review_attach_photo_handler,
    image_review_edit_search_query_handler,
    image_review_edit_prompt_handler,
    image_review_generate_handler,
    image_review_next_handler,
    image_review_pick_handler,
    image_review_photo_handler,
    image_review_search_handler,
    published_image_item_handler,
    published_images_menu_handler,
)
from englishbot.domain.add_words_models import AddWordsApprovalResult, AddWordsFlowState
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


def _write_test_image(path: Path, *, size: tuple[int, int] = (32, 16)) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (255, 0, 0)).save(path)


class _FakeCallbackMessage:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.chat_id = 1
        self.message_id = 999
        self.reply_text_calls: list[str] = []
        self.reply_text_markups: list[object] = []
        self.reply_photo_captions: list[str] = []
        self.replies: list[SimpleNamespace] = []

    async def reply_text(self, text: str, reply_markup=None):  # noqa: ARG002
        self.reply_text_calls.append(text)
        self.reply_text_markups.append(reply_markup)
        sent = _FakeSentMessage(text=text, message_id=len(self.reply_text_calls), chat_id=self.chat_id)
        self.replies.append(sent)
        return sent

    async def reply_photo(self, photo, caption=None, reply_markup=None):  # noqa: ARG002
        self.reply_photo_captions.append(caption or "")
        photo.read()
        return SimpleNamespace(
            message_id=100 + len(self.reply_photo_captions),
            chat_id=self.chat_id,
        )


class _FakeSentMessage(SimpleNamespace):
    def __init__(self, text: str, message_id: int, chat_id: int = 1) -> None:
        super().__init__(text=text, message_id=message_id, chat_id=chat_id)
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


class _FakeTelegramFlowMessageRepository:
    def __init__(self) -> None:
        self.messages: list[SimpleNamespace] = []

    def track(self, *, flow_id: str, chat_id: int, message_id: int, tag: str) -> None:
        self.messages = [
            item
            for item in self.messages
            if not (
                item.flow_id == flow_id
                and item.chat_id == chat_id
                and item.message_id == message_id
            )
        ]
        self.messages.append(
            SimpleNamespace(
                flow_id=flow_id,
                chat_id=chat_id,
                message_id=message_id,
                tag=tag,
            )
        )

    def list(self, *, flow_id: str, tag: str | None = None):
        return [
            item
            for item in self.messages
            if item.flow_id == flow_id and (tag is None or item.tag == tag)
        ]

    def remove(self, *, flow_id: str, chat_id: int, message_id: int) -> None:
        self.messages = [
            item
            for item in self.messages
            if not (
                item.flow_id == flow_id
                and item.chat_id == chat_id
                and item.message_id == message_id
            )
        ]

    def clear(self, *, flow_id: str, tag: str | None = None) -> None:
        self.messages = [
            item
            for item in self.messages
            if not (item.flow_id == flow_id and (tag is None or item.tag == tag))
        ]


class _FakeBot:
    def __init__(self) -> None:
        self.deleted_messages: list[tuple[int, int]] = []

    async def delete_message(self, *, chat_id: int, message_id: int) -> None:
        self.deleted_messages.append((chat_id, message_id))


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


class _FakeSearchImageReviewCandidatesUseCase:
    def __init__(self, flow: ImageReviewFlowState) -> None:
        self._flow = flow
        self.query: str | None = None

    def execute(self, *, user_id: int, flow_id: str, query=None):  # noqa: ARG002
        assert flow_id == self._flow.flow_id
        self.query = query
        return self._flow


class _FakeLoadNextImageReviewCandidatesUseCase:
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
            output_path=self._flow.output_path,
        )


class _FakePublishImageReviewUseCase:
    def __init__(self) -> None:
        self.output_path: Path | None = None

    def execute(self, *, user_id: int, flow_id: str, output_path: Path | None = None):  # noqa: ARG002
        self.output_path = output_path
        return output_path


class _FakeContentStore:
    def __init__(self, content_pack=None) -> None:
        self.db_path = Path("data/test.db")
        self._content_pack = content_pack or {
            "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
            "vocabulary_items": [],
        }

    def get_content_pack(self, topic_id: str) -> dict[str, object]:
        assert topic_id == "fairy-tales"
        return self._content_pack


class _FakeSelectImageCandidateUseCase:
    def __init__(self, flow: ImageReviewFlowState) -> None:
        self._flow = flow

    def execute(
        self,
        *,
        user_id: int,  # noqa: ARG002
        flow_id: str,
        item_id: str,
        candidate_index: int,
    ) -> ImageReviewFlowState:
        assert flow_id == self._flow.flow_id
        assert item_id == self._flow.current_item.item_id
        assert candidate_index == 0
        return ImageReviewFlowState(
            flow_id=self._flow.flow_id,
            editor_user_id=self._flow.editor_user_id,
            content_pack={
                "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
                "vocabulary_items": [
                    {
                        "id": "dragon",
                        "image_ref": "assets/fairy-tales/review/dragon--dreamshaper.png",
                    }
                ],
            },
            items=self._flow.items,
            current_index=1,
            output_path=self._flow.output_path,
        )


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


class _FakeApproveAddWordsDraftUseCase:
    def execute(self, *, user_id: int, flow_id: str, output_path=None):  # noqa: ARG002
        draft = LessonExtractionDraft(
            topic_title="Fairy Tales",
            vocabulary_items=[
                ExtractedVocabularyItemDraft(
                    item_id="dragon",
                    english_word="Dragon",
                    translation="дракон",
                    source_fragment="Dragon — дракон",
                    image_prompt="a green dragon",
                ),
                ExtractedVocabularyItemDraft(
                    item_id="fairy",
                    english_word="Fairy",
                    translation="фея",
                    source_fragment="Fairy — фея",
                    image_prompt="a tiny fairy",
                ),
            ],
        )
        return AddWordsApprovalResult(
            import_result=ImportLessonResult(
                draft=draft,
                validation=ValidationResult(errors=[]),
            ),
            published_topic_id="fairy-tales",
            output_path=Path("content/custom/fairy-tales.json"),
        )


class _FakeGenerateContentPackImagesUseCase:
    def execute(
        self,
        *,
        topic_id: str,
        assets_dir: Path,
        force: bool = False,
        progress_callback=None,
    ):  # noqa: ARG002
        assert topic_id == "fairy-tales"
        assert assets_dir == Path("assets")
        if progress_callback is not None:
            progress_callback(1, 2)
            progress_callback(2, 2)
        return {
            "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
            "vocabulary_items": [
                {
                    "id": "dragon",
                    "english_word": "Dragon",
                    "translation": "дракон",
                    "image_ref": "assets/fairy-tales/dragon.png",
                },
                {
                    "id": "fairy",
                    "english_word": "Fairy",
                    "translation": "фея",
                    "image_ref": "assets/fairy-tales/fairy.png",
                },
            ],
        }


class _FakeStartPublishedWordImageEditUseCase:
    def __init__(self, flow: ImageReviewFlowState) -> None:
        self._flow = flow

    def execute(self, *, user_id: int, topic_id: str, item_id: str, model_names=None):  # noqa: ARG002
        assert topic_id == "fairy-tales"
        assert item_id == "dragon"
        return self._flow


@pytest.mark.anyio
async def test_approve_draft_handler_starts_image_review_without_auto_generation(
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
                candidates=[],
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
    assert "Image prompts generated and saved." in query.edits[3]
    assert "Everything is saved. Continue image review in the messages below." in query.edits[3]
    review_index = next(index for index, text in enumerate(message.reply_text_calls) if "Reviewing images 1/1" in text)
    assert message.reply_text_markups[review_index] is not None
    assert "Prompt is used for local AI generation." in message.reply_text_calls[review_index]
    assert "Pixabay search: word only by default." in message.reply_text_calls[review_index]
    assert "No candidates loaded yet." in message.reply_text_calls[review_index]
    assert message.reply_photo_captions == []


@pytest.mark.anyio
async def test_approve_auto_images_handler_generates_images_and_offers_word_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("englishbot.bot.build_training_service", lambda db_path=None: "training-service")
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
    message = _FakeCallbackMessage(tmp_path)
    query = _FakeQuery("words:approve_auto_images:flow123", message)
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=42))
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "content_store": _FakeContentStore(),
                "add_words_get_active_use_case": _FakeGetActiveFlowUseCase(add_words_flow),
                "add_words_cancel_use_case": _FakeCancelAddWordsUseCase(),
                "add_words_save_approved_draft_use_case": _FakeSaveApprovedDraftUseCase(
                    add_words_flow
                ),
                "add_words_generate_image_prompts_use_case": (
                    _FakeGenerateAddWordsImagePromptsUseCase(add_words_flow)
                ),
                "add_words_approve_use_case": _FakeApproveAddWordsDraftUseCase(),
                "content_pack_generate_images_use_case": _FakeGenerateContentPackImagesUseCase(),
                "word_import_preview_message_ids": {},
            }
        ),
    )

    await add_words_approve_auto_images_handler(update, context)  # type: ignore[arg-type]

    assert query.edits[0] == "Saving approved draft... 0/1"
    assert "Publishing content pack... 0/1" in query.edits[2]
    assert "Generating images... 0/2" in query.edits[3]
    assert "Generating images... 1/2" in query.edits[4]
    assert "Generating images... 2/2" in query.edits[5]
    assert "Draft approved and images generated." in query.edits[6]


@pytest.mark.anyio
async def test_published_image_menu_and_item_handlers_show_current_image_and_wait_for_source_action(
    tmp_path: Path,
) -> None:
    content_dir = tmp_path / "content" / "custom"
    content_dir.mkdir(parents=True)
    current_image_path = tmp_path / "assets" / "fairy-tales" / "dragon.png"
    current_image_path.parent.mkdir(parents=True, exist_ok=True)
    _write_test_image(current_image_path)
    (content_dir / "fairy-tales.json").write_text(
        '{\n'
        '  "topic": {"id": "fairy-tales", "title": "Fairy Tales"},\n'
        '  "lessons": [],\n'
        '  "vocabulary_items": [\n'
        '    {"id": "dragon", "english_word": "Dragon", "translation": "дракон", '
        '"image_ref": "assets/fairy-tales/dragon.png"},\n'
        '    {"id": "fairy", "english_word": "Fairy", "translation": "фея"}\n'
        "  ]\n"
        "}\n",
        encoding="utf-8",
    )
    candidate_path = tmp_path / "dragon-a.png"
    _write_test_image(candidate_path)
    review_flow = ImageReviewFlowState(
        flow_id="review123",
        editor_user_id=42,
        content_pack={
            "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
            "vocabulary_items": [
                {
                    "id": "dragon",
                    "english_word": "Dragon",
                    "translation": "дракон",
                    "image_ref": "assets/fairy-tales/dragon.png",
                }
            ],
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
                        output_path=candidate_path,
                        prompt="Prompt for Dragon",
                    )
                ],
            )
        ],
    )
    menu_message = _FakeCallbackMessage(tmp_path)
    menu_query = _FakeQuery("words:edit_images_menu:fairy-tales", menu_message)
    menu_update = SimpleNamespace(callback_query=menu_query, effective_user=SimpleNamespace(id=42))
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "content_store": _FakeContentStore(review_flow.content_pack),
                "image_review_start_published_word_use_case": (
                    _FakeStartPublishedWordImageEditUseCase(review_flow)
                ),
                "image_review_generate_use_case": _FakeGenerateImageReviewCandidatesUseCase(
                    review_flow
                ),
            }
        ),
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(tmp_path)
    try:
        await published_images_menu_handler(menu_update, context)  # type: ignore[arg-type]
        assert menu_query.edits[-1] == "Choose a word to edit its image."

        item_message = _FakeCallbackMessage(tmp_path)
        item_query = _FakeQuery(
            "words:edit_published_image:fairy-tales:0",
            item_message,
        )
        item_update = SimpleNamespace(
            callback_query=item_query,
            effective_user=SimpleNamespace(id=42),
        )
        await published_image_item_handler(item_update, context)  # type: ignore[arg-type]

        assert any(
            caption.startswith("Current image.")
            for caption in item_message.reply_photo_captions
        )
        assert any("Reviewing images 1/1" in text for text in item_message.reply_text_calls)
        assert not any(
            "Generating local image candidates 1/1..." in text
            for text in item_message.reply_text_calls
        )

        generate_query = _FakeQuery(
            "words:image_generate:review123",
            item_message,
        )
        generate_update = SimpleNamespace(
            callback_query=generate_query,
            effective_user=SimpleNamespace(id=42),
        )
        context.application.bot_data["image_review_get_active_use_case"] = (
            _FakeGetActiveImageReviewUseCase(review_flow)
        )
        await image_review_generate_handler(generate_update, context)  # type: ignore[arg-type]

        assert any(
            "Generating local image candidates 1/1..." in text
            for text in item_message.reply_text_calls
        )
        assert any("Reviewing images 1/1" in text for text in item_message.reply_text_calls)
    finally:
        monkeypatch.undo()


@pytest.mark.anyio
async def test_image_review_search_and_next_handlers_show_pixabay_candidates(
    tmp_path: Path,
) -> None:
    candidate_a_path = tmp_path / "pixabay-a.jpg"
    candidate_b_path = tmp_path / "pixabay-b.jpg"
    _write_test_image(candidate_a_path)
    _write_test_image(candidate_b_path)
    search_flow = ImageReviewFlowState(
        flow_id="review123",
        editor_user_id=42,
        content_pack={"topic": {"id": "fairy-tales", "title": "Fairy Tales"}},
        items=[
            ImageReviewItem(
                item_id="dragon",
                english_word="Dragon",
                translation="дракон",
                prompt="Prompt for Dragon",
                search_query="Dragon",
                search_page=1,
                candidate_source_type="pixabay",
                candidates=[
                    ImageCandidate(
                        model_name="pixabay",
                        image_ref="assets/fairy-tales/review/dragon--pixabay-1.jpg",
                        output_path=candidate_a_path,
                        prompt="Prompt for Dragon",
                        source_type="pixabay",
                        source_id="1",
                        width=640,
                        height=480,
                    )
                ],
            )
        ],
    )
    next_flow = ImageReviewFlowState(
        flow_id="review123",
        editor_user_id=42,
        content_pack=search_flow.content_pack,
        items=[
            ImageReviewItem(
                item_id="dragon",
                english_word="Dragon",
                translation="дракон",
                prompt="Prompt for Dragon",
                search_query="Dragon",
                search_page=2,
                candidate_source_type="pixabay",
                candidates=[
                    ImageCandidate(
                        model_name="pixabay",
                        image_ref="assets/fairy-tales/review/dragon--pixabay-2.jpg",
                        output_path=candidate_b_path,
                        prompt="Prompt for Dragon",
                        source_type="pixabay",
                        source_id="2",
                        width=800,
                        height=600,
                    )
                ],
            )
        ],
    )
    message = _FakeCallbackMessage(tmp_path)
    search_query = _FakeQuery("words:image_search:review123", message)
    search_update = SimpleNamespace(
        callback_query=search_query,
        effective_user=SimpleNamespace(id=42),
    )
    next_query = _FakeQuery("words:image_next:review123", message)
    next_update = SimpleNamespace(
        callback_query=next_query,
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(
        bot=_FakeBot(),
        application=SimpleNamespace(
            bot_data={
                "image_review_get_active_use_case": _FakeGetActiveImageReviewUseCase(search_flow),
                "image_review_search_use_case": _FakeSearchImageReviewCandidatesUseCase(search_flow),
                "image_review_next_use_case": _FakeLoadNextImageReviewCandidatesUseCase(next_flow),
                "telegram_flow_message_repository": _FakeTelegramFlowMessageRepository(),
            }
        ),
    )

    await image_review_search_handler(search_update, context)  # type: ignore[arg-type]
    assert search_query.edits[0] == "Searching Pixabay 1/1..."
    assert search_query.edits[1] == "Pixabay candidates ready 1/1"
    assert any("Pixabay candidates page 1" in text for text in message.reply_text_calls)
    assert any("Pixabay search query: Dragon" in text for text in message.reply_text_calls)
    assert "A. Pixabay | ID 1 | 640x480" in message.reply_photo_captions

    context.application.bot_data["image_review_get_active_use_case"] = _FakeGetActiveImageReviewUseCase(
        next_flow
    )
    await image_review_next_handler(next_update, context)  # type: ignore[arg-type]
    assert next_query.edits[0] == "Loading next Pixabay candidates 1/1..."
    assert next_query.edits[1] == "Pixabay candidates ready 1/1"
    assert any("Pixabay candidates page 2" in text for text in message.reply_text_calls)
    assert any("Pixabay search query: Dragon" in text for text in message.reply_text_calls)
    assert "A. Pixabay | ID 2 | 800x600" in message.reply_photo_captions
    assert context.bot.deleted_messages == [(1, 1), (1, 101)]


@pytest.mark.anyio
async def test_image_review_edit_search_query_flow_runs_search_with_custom_text(
    tmp_path: Path,
) -> None:
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
                search_query=None,
                candidates=[],
            )
        ],
    )
    candidate_path = tmp_path / "pixabay-a.jpg"
    _write_test_image(candidate_path)
    searched_flow = ImageReviewFlowState(
        flow_id="review123",
        editor_user_id=42,
        content_pack=initial_flow.content_pack,
        items=[
            ImageReviewItem(
                item_id="dragon",
                english_word="Dragon",
                translation="дракон",
                prompt="Prompt for Dragon",
                search_query="dragon scissors clipart",
                search_page=1,
                candidate_source_type="pixabay",
                candidates=[
                    ImageCandidate(
                        model_name="pixabay",
                        image_ref="assets/fairy-tales/review/dragon--pixabay-1.jpg",
                        output_path=candidate_path,
                        prompt="Prompt for Dragon",
                        source_type="pixabay",
                        source_id="1",
                        width=640,
                        height=480,
                    )
                ],
            )
        ],
    )
    search_use_case = _FakeSearchImageReviewCandidatesUseCase(searched_flow)
    prompt_message = _FakeCallbackMessage(tmp_path)
    prompt_query = _FakeQuery("words:image_edit_search_query:review123", prompt_message)
    prompt_update = SimpleNamespace(
        callback_query=prompt_query,
        effective_user=SimpleNamespace(id=42),
    )
    text_message = _FakeCallbackMessage(tmp_path)
    text_message.text = "dragon scissors clipart"
    text_message.chat_id = 1
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
                "image_review_search_use_case": search_use_case,
            }
        ),
    )

    await image_review_edit_search_query_handler(prompt_update, context)  # type: ignore[arg-type]

    assert context.user_data["words_flow_mode"] == "awaiting_image_review_search_query_text"
    assert context.user_data["image_review_flow_id"] == "review123"
    assert context.user_data["image_review_item_id"] == "dragon"
    assert "Current query:\nDragon" in prompt_message.reply_text_calls[-1]

    await add_words_text_handler(text_update, context)  # type: ignore[arg-type]

    assert context.user_data.get("words_flow_mode") is None
    assert search_use_case.query == "dragon scissors clipart"
    assert any("Pixabay candidates updated." in edit for edit in text_message.replies[0].edits)
    assert any(
        "Pixabay search query: dragon scissors clipart" in text
        for text in text_message.reply_text_calls
    )


@pytest.mark.anyio
async def test_image_review_edit_prompt_flow_accepts_new_prompt_without_auto_generation(
    tmp_path: Path,
) -> None:
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
    prompt_query = _FakeQuery("words:image_edit_prompt:review123", prompt_message)
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
    assert any("Prompt updated." in edit for edit in text_message.replies[0].edits)
    assert any("Reviewing images 1/1" in text for text in text_message.reply_text_calls)
    assert not any("Generating local image candidates" in text for text in text_message.reply_text_calls)


@pytest.mark.anyio
async def test_image_review_attach_photo_flow_saves_user_image_and_publishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("englishbot.bot.build_training_service", lambda db_path=None: "training-service")
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
    callback_query = _FakeQuery("words:image_attach_photo:review123", callback_message)
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
                "content_store": _FakeContentStore(flow.content_pack),
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


@pytest.mark.anyio
async def test_published_image_pick_flow_overwrites_existing_topic_file_instead_of_creating_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("englishbot.bot.build_training_service", lambda db_path=None: "training-service")
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
                candidates=[
                    ImageCandidate(
                        model_name="dreamshaper",
                        image_ref="assets/fairy-tales/review/dragon--dreamshaper.png",
                        output_path=tmp_path / "dragon-a.png",
                        prompt="Prompt for Dragon",
                    )
                ],
            )
        ],
    )
    publish_use_case = _FakePublishImageReviewUseCase()
    query_message = _FakeCallbackMessage(tmp_path)
    query = _FakeQuery("words:image_pick:review123:0", query_message)
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=42))
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "content_store": _FakeContentStore(flow.content_pack),
                "image_review_get_active_use_case": _FakeGetActiveImageReviewUseCase(flow),
                "image_review_select_use_case": _FakeSelectImageCandidateUseCase(flow),
                "image_review_publish_use_case": publish_use_case,
                "add_words_cancel_use_case": _FakeCancelAddWordsUseCase(),
                "word_import_preview_message_ids": {},
            }
        ),
    )

    await image_review_pick_handler(update, context)  # type: ignore[arg-type]

    assert publish_use_case.output_path is None


@pytest.mark.anyio
async def test_image_review_pick_completion_keeps_callback_message_for_final_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("englishbot.bot.build_training_service", lambda db_path=None: "training-service")
    flow = ImageReviewFlowState(
        flow_id="review123",
        editor_user_id=42,
        content_pack={
            "topic": {"id": "fairy-tales", "title": "Fairy Tales"},
            "vocabulary_items": [{"id": "castle", "image_ref": None}],
        },
        items=[
            ImageReviewItem(
                item_id="castle",
                english_word="Castle",
                translation="замок",
                prompt="Prompt for Castle",
                candidates=[
                    ImageCandidate(
                        model_name="pixabay",
                        image_ref="assets/fairy-tales/review/castle--pixabay-1.jpg",
                        output_path=tmp_path / "castle-a.png",
                        prompt="Prompt for Castle",
                        source_type="pixabay",
                    )
                ],
            )
        ],
    )
    _write_test_image(flow.items[0].candidates[0].output_path)
    publish_use_case = _FakePublishImageReviewUseCase()
    registry = _FakeTelegramFlowMessageRepository()
    registry.track(flow_id="review123", chat_id=1, message_id=999, tag="image_review_step")
    registry.track(flow_id="review123", chat_id=1, message_id=1001, tag="image_review_step")
    fake_bot = _FakeBot()
    query_message = _FakeCallbackMessage(tmp_path)
    query = _FakeQuery("words:image_pick:review123:0", query_message)
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=42))
    context = SimpleNamespace(
        bot=fake_bot,
        application=SimpleNamespace(
            bot_data={
                "content_store": _FakeContentStore(flow.content_pack),
                "image_review_get_active_use_case": _FakeGetActiveImageReviewUseCase(flow),
                "image_review_select_use_case": _FakeSelectImageCandidateUseCase(flow),
                "image_review_publish_use_case": publish_use_case,
                "add_words_cancel_use_case": _FakeCancelAddWordsUseCase(),
                "word_import_preview_message_ids": {},
                "telegram_flow_message_repository": registry,
            }
        ),
    )

    await image_review_pick_handler(update, context)  # type: ignore[arg-type]

    assert fake_bot.deleted_messages == [(1, 1001)]
    assert "Image review completed and content pack published." in query.edits[-1]
    assert registry.list(flow_id="review123") == []
