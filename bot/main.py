"""Entry point — python -m bot.main"""

from __future__ import annotations

from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot import handlers
from config.settings import settings
from utils.logger import get_logger

log = get_logger(__name__)


def main() -> None:
    settings.validate()
    settings.ensure_dirs()

    app = ApplicationBuilder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_start))
    app.add_handler(
        MessageHandler(filters.VIDEO | filters.Document.VIDEO, handlers.on_video)
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
    app.add_handler(CallbackQueryHandler(handlers.on_callback))
    app.add_error_handler(handlers.on_error)

    log.info("Bot starting (long polling)…")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
