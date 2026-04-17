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
    clear_catalog_workbook_import_interaction,
    edit_expected_user_input_prompt,
    is_catalog_workbook_import_interaction,
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
    await query.edit_message_text(
        tg_runtime.tg("catalog_workbook_menu", context=context, user=user),
        reply_markup=_catalog_menu_markup(context, user),
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
