"""Final composition/export — normalize to a delivery-ready 9:16 MP4."""

from __future__ import annotations

import asyncio
from pathlib import Path

from utils.ffmpeg_utils import run_ffmpeg


async def final_export(video: Path, dest: Path) -> Path:
    """Re-encode to a clean 1080x1920 H.264/AAC MP4 with faststart for streaming."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-i", str(video),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "21",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
        "-movflags", "+faststart",
        str(dest),
    ]
    await asyncio.to_thread(run_ffmpeg, args, "final-export")
    return dest
