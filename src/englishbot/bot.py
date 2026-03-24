from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    await update.effective_message.reply_text(
        "Hello! I am a bot starter skeleton. I will become useful as soon as logic is added."
    )


def build_application(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_handler))
    return app
