"""Telegram helper functions."""

from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode

from utils.logger import get_logger

log = get_logger(__name__)

# Telegram bot API upload limit
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


async def send_text(update: Update, text: str) -> None:
    try:
        await update.effective_chat.send_message(text[:4000])
    except Exception as exc:  # noqa: BLE001
        log.warning(f"send_text failed: {exc}")


async def send_video_file(update: Update, path: Path, caption: str) -> None:
    size = path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        await send_text(
            update,
            f"📦 Clip is {size / 1e6:.0f} MB — larger than Telegram's 50 MB bot limit.\n"
            f"Find it on the server at: {path}",
        )
        return
    with open(path, "rb") as f:
        await update.effective_chat.send_video(
            video=f,
            caption=caption[:1024],
            supports_streaming=True,
            width=1080,
            height=1920,
            read_timeout=300,
            write_timeout=300,
        )


def make_callbacks(update: Update):
    """Bind (notify, send_clip) coroutines for the orchestrator."""

    async def notify(text: str) -> None:
        await send_text(update, text)

    async def send_clip(path: Path, caption: str) -> None:
        await send_video_file(update, path, caption)

    return notify, send_clip


WELCOME = (
    "👋 Send me a *long video* (file or YouTube/social link) and I'll find every "
    "viral-potential moment and turn each one into a polished 9:16 short — with "
    "animated captions, music, effects, and its own title & hashtags.\n\n"
    "You can add an instruction with the link, e.g.:\n"
    "`https://youtu.be/... focus on the funny moments, 30-60s clips`\n\n"
    "After delivery, revise any clip by replying, e.g.:\n"
    "`clip 2: change the music` · `clip 1: bigger captions`"
)


async def send_welcome(update: Update) -> None:
    await update.effective_chat.send_message(WELCOME, parse_mode=ParseMode.MARKDOWN)
