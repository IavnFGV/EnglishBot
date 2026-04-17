from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import NamedTemporaryFile

from telegram import Update
from telegram.ext import ContextTypes

from englishbot.presentation.telegram_editor_ui import (
    catalog_workbook_import_keyboard,
    catalog_workbook_menu_keyboard,
)
from englishbot.telegram import runtime as tg_runtime
from englishbot.telegram.interaction import (
    clear_catalog_image_saver_interaction,
    clear_catalog_workbook_import_interaction,
    edit_expected_user_input_prompt,
    is_catalog_image_saver_interaction,
    is_catalog_workbook_import_interaction,
    start_catalog_image_saver_interaction,
    start_catalog_workbook_import_interaction,
)


def _catalog_use_case(context: ContextTypes.DEFAULT_TYPE, key: str):
    use_case = tg_runtime.optional_bot_data(context, key)
    if use_case is None:
        raise RuntimeError(f"Missing bot_data use case: {key}")
    return use_case


def _catalog_menu_markup(context: ContextTypes.DEFAULT_TYPE, user):
    return catalog_workbook_menu_keyboard(
        tg=tg_runtime.tg,
        language=tg_runtime.telegram_ui_language(context, user),
    )


def _catalog_import_markup(context: ContextTypes.DEFAULT_TYPE, user):
    return catalog_workbook_import_keyboard(
        tg=tg_runtime.tg,
        language=tg_runtime.telegram_ui_language(context, user),
    )


async def words_catalog_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    await query.answer()
    if not tg_runtime.is_admin(user.id, context):
        await query.edit_message_text(
            tg_runtime.tg("admin_only", context=context, user=user)
        )
        return
    clear_catalog_workbook_import_interaction(context)
    clear_catalog_image_saver_interaction(context)
    await query.edit_message_text(
        tg_runtime.tg("catalog_workbook_menu", context=context, user=user),
        reply_markup=_catalog_menu_markup(context, user),
    )


async def words_catalog_image_saver_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.message is None:
        return
    await query.answer()
    if not tg_runtime.is_admin(user.id, context):
        await query.edit_message_text(
            tg_runtime.tg("admin_only", context=context, user=user)
        )
        return
    clear_catalog_workbook_import_interaction(context)
    clear_catalog_image_saver_interaction(context)
    start_catalog_image_saver_interaction(
        context,
        chat_id=tg_runtime.message_chat_id(query.message),
        message_id=query.message.message_id,
    )
    await query.edit_message_text(
        tg_runtime.tg("catalog_image_saver_prompt", context=context, user=user),
        reply_markup=_catalog_import_markup(context, user),
    )


async def words_catalog_export_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.message is None:
        return
    await query.answer()
    if not tg_runtime.is_admin(user.id, context):
        await query.edit_message_text(
            tg_runtime.tg("admin_only", context=context, user=user)
        )
        return
    clear_catalog_workbook_import_interaction(context)
    clear_catalog_image_saver_interaction(context)
    await query.edit_message_text(
        tg_runtime.tg("catalog_workbook_exporting", context=context, user=user),
        reply_markup=_catalog_menu_markup(context, user),
    )
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(suffix=".xlsx", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        await asyncio.to_thread(
            _catalog_use_case(context, "export_media_catalog_use_case").execute,
            output_path=temp_path,
        )
        with temp_path.open("rb") as document:
            await query.message.reply_document(
                document=document,
                filename="englishbot-catalog.xlsx",
                caption=tg_runtime.tg("catalog_workbook_export_ready", context=context, user=user),
            )
        await query.edit_message_text(
            tg_runtime.tg("catalog_workbook_menu", context=context, user=user),
            reply_markup=_catalog_menu_markup(context, user),
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


async def words_catalog_import_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.message is None:
        return
    await query.answer()
    if not tg_runtime.is_admin(user.id, context):
        await query.edit_message_text(
            tg_runtime.tg("admin_only", context=context, user=user)
        )
        return
    start_catalog_workbook_import_interaction(
        context,
        chat_id=tg_runtime.message_chat_id(query.message),
        message_id=query.message.message_id,
    )
    await query.edit_message_text(
        tg_runtime.tg("catalog_workbook_import_prompt", context=context, user=user),
        reply_markup=_catalog_import_markup(context, user),
    )


async def words_catalog_document_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    user = update.effective_user
    document = getattr(message, "document", None)
    if message is None or user is None or document is None:
        return
    if is_catalog_image_saver_interaction(context):
        if not _is_image_document(document):
            await message.reply_text(tg_runtime.tg("catalog_image_saver_invalid_file", context=context, user=user))
            return
        await _save_catalog_uploaded_media(
            context=context,
            user=user,
            message=message,
            get_telegram_file=document.get_file,
            original_file_name=str(getattr(document, "file_name", "") or ""),
            mime_type=str(getattr(document, "mime_type", "") or ""),
        )
        return
    if not is_catalog_workbook_import_interaction(context):
        return
    if not tg_runtime.is_admin(user.id, context):
        clear_catalog_workbook_import_interaction(context)
        await message.reply_text(tg_runtime.tg("admin_only", context=context, user=user))
        return
    file_name = str(getattr(document, "file_name", "") or "")
    if not file_name.lower().endswith(".xlsx"):
        await message.reply_text(tg_runtime.tg("catalog_workbook_invalid_file", context=context, user=user))
        return
    await edit_expected_user_input_prompt(
        context,
        text=tg_runtime.tg("catalog_workbook_importing", context=context, user=user),
        reply_markup=_catalog_import_markup(context, user),
    )
    status_message = await message.reply_text(
        tg_runtime.tg("catalog_workbook_importing", context=context, user=user)
    )
    temp_path: Path | None = None
    try:
        telegram_file = await document.get_file()
        with NamedTemporaryFile(suffix=".xlsx", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        await telegram_file.download_to_drive(custom_path=str(temp_path))
        result = await asyncio.to_thread(
            _catalog_use_case(context, "import_media_catalog_use_case").execute,
            input_path=temp_path,
        )
    except Exception as error:  # noqa: BLE001
        await status_message.edit_text(
            tg_runtime.tg(
                "catalog_workbook_import_failed",
                context=context,
                user=user,
                error=str(error),
            )
        )
        await edit_expected_user_input_prompt(
            context,
            text=tg_runtime.tg("catalog_workbook_import_prompt", context=context, user=user),
            reply_markup=_catalog_import_markup(context, user),
        )
        return
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    await status_message.edit_text(
        tg_runtime.tg(
            "catalog_workbook_import_success",
            context=context,
            user=user,
            updated_count=result.updated_count,
            topic_count=result.topic_count,
        )
    )
    await edit_expected_user_input_prompt(
        context,
        text=tg_runtime.tg("catalog_workbook_menu", context=context, user=user),
        reply_markup=_catalog_menu_markup(context, user),
    )
    clear_catalog_workbook_import_interaction(context)


async def words_catalog_photo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    user = update.effective_user
    photos = getattr(message, "photo", None)
    if message is None or user is None or not photos:
        return
    if not is_catalog_image_saver_interaction(context):
        return
    if not tg_runtime.is_admin(user.id, context):
        clear_catalog_image_saver_interaction(context)
        await message.reply_text(tg_runtime.tg("admin_only", context=context, user=user))
        return
    photo = photos[-1]
    await _save_catalog_uploaded_media(
        context=context,
        user=user,
        message=message,
        get_telegram_file=photo.get_file,
        original_file_name="telegram-photo.jpg",
        mime_type="image/jpeg",
    )


async def _save_catalog_uploaded_media(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    message,
    get_telegram_file,
    original_file_name: str,
    mime_type: str,
) -> None:
    await edit_expected_user_input_prompt(
        context,
        text=tg_runtime.tg("catalog_image_saver_saving", context=context, user=user),
        reply_markup=_catalog_import_markup(context, user),
    )
    status_message = await message.reply_text(
        tg_runtime.tg("catalog_image_saver_saving", context=context, user=user)
    )
    temp_path: Path | None = None
    try:
        telegram_file = await get_telegram_file()
        suffix = Path(original_file_name).suffix or ".jpg"
        with NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        await telegram_file.download_to_drive(custom_path=str(temp_path))
        result = await asyncio.to_thread(
            _catalog_use_case(context, "save_catalog_uploaded_image_use_case").execute,
            input_path=temp_path,
            original_file_name=original_file_name,
            mime_type=mime_type,
        )
    except Exception as error:  # noqa: BLE001
        await status_message.edit_text(
            tg_runtime.tg(
                "catalog_image_saver_failed",
                context=context,
                user=user,
                error=str(error),
            )
        )
        await edit_expected_user_input_prompt(
            context,
            text=tg_runtime.tg("catalog_image_saver_prompt", context=context, user=user),
            reply_markup=_catalog_import_markup(context, user),
        )
        return
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    await status_message.edit_text(
        tg_runtime.tg(
            "catalog_image_saver_success",
            context=context,
            user=user,
            url=result.public_url,
        )
    )
    await edit_expected_user_input_prompt(
        context,
        text=tg_runtime.tg("catalog_image_saver_prompt", context=context, user=user),
        reply_markup=_catalog_import_markup(context, user),
    )


def _is_image_document(document) -> bool:
    mime_type = str(getattr(document, "mime_type", "") or "").strip().lower()
    if mime_type.startswith("image/"):
        return True
    file_name = str(getattr(document, "file_name", "") or "").strip().lower()
    return file_name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
