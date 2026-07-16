"""FFmpeg-based clip trimming."""

from __future__ import annotations

import asyncio
from pathlib import Path

from utils.ffmpeg_utils import run_ffmpeg


async def extract_clip(source: Path, start: float, end: float, dest: Path) -> Path:
    """Cut [start, end] from source, re-encoding for accurate cuts."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-i", str(source),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-avoid_negative_ts", "make_zero",
        str(dest),
    ]
    await asyncio.to_thread(run_ffmpeg, args, "clip-extract")
    return dest
