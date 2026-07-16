"""Telegram message handlers.

- /start                → welcome
- video file / video URL → run the full pipeline
- other text            → treated as a revision request for the user's last job
Per-user job lock keeps one pipeline per user at a time (multi-user isolation
comes from JobWorkspace's per-user directories).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from agent.orchestrator import run_pipeline
from bot.telegram_utils import make_callbacks, send_text, send_welcome
from revision.revision_handler import handle_revision
from utils.file_manager import JobWorkspace
from utils.logger import get_logger
from utils.video_downloader import extract_url

log = get_logger(__name__)

# Telegram bots can download files up to 20 MB via get_file
MAX_TG_DOWNLOAD = 20 * 1024 * 1024

_user_locks: dict[int, asyncio.Lock] = {}


def _lock_for(user_id: int) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_welcome(update)


async def on_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User sent a video file directly."""
    user_id = update.effective_user.id
    video = update.message.video or update.message.document
    if video is None:
        return
    if (video.file_size or 0) > MAX_TG_DOWNLOAD:
        await send_text(
            update,
            "📦 That file is over Telegram's 20 MB bot-download limit.\n"
            "Please send a link instead (YouTube/Drive/direct URL) — links have no size limit.",
        )
        return

    lock = _lock_for(user_id)
    if lock.locked():
        await send_text(update, "⏳ I'm still working on your previous video — please wait.")
        return

    async with lock:
        ws_tmp = JobWorkspace(user_id)  # temp workspace just to receive the file
        dest = ws_tmp.source_dir / (getattr(video, "file_name", None) or "input.mp4")
        tg_file = await context.bot.get_file(video.file_id)
        await tg_file.download_to_drive(custom_path=str(dest))

        notify, send_clip = make_callbacks(update)
        instruction = (update.message.caption or "").strip()
        await run_pipeline(user_id, dest, instruction, notify, send_clip)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """URL → new pipeline job. Anything else → revision request."""
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    url = extract_url(text)

    lock = _lock_for(user_id)
    if lock.locked():
        await send_text(update, "⏳ I'm still working on your previous request — please wait.")
        return

    async with lock:
        notify, send_clip = make_callbacks(update)
        if url:
            instruction = text.replace(url, "").strip()
            await run_pipeline(user_id, url, instruction, notify, send_clip)
        else:
            handled = await handle_revision(user_id, text, notify, send_clip)
            if not handled:
                await send_text(
                    update,
                    "🎥 Send me a long video (file or link) first — then you can ask for "
                    "changes like “clip 2: change the music”.",
                )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reserved for future inline buttons."""
    if update.callback_query:
        await update.callback_query.answer()


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error(f"Unhandled bot error: {context.error}")
    if isinstance(update, Update) and update.effective_chat:
        try:
            await update.effective_chat.send_message(
                f"⚠️ Unexpected error: {context.error}\nPlease try again."
            )
        except Exception:  # noqa: BLE001
            pass
