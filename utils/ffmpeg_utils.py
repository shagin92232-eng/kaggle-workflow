"""FFmpeg helpers shared by all editing modules."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from utils.logger import get_logger

log = get_logger(__name__)


class FFmpegError(RuntimeError):
    pass


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FFmpegError("ffmpeg not found on PATH — install FFmpeg first")
    return path


def ffprobe_bin() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise FFmpegError("ffprobe not found on PATH — install FFmpeg first")
    return path


def run_ffmpeg(args: list[str], desc: str = "ffmpeg") -> None:
    cmd = [ffmpeg_bin(), "-hide_banner", "-y", *args]
    log.info(f"{desc}: {' '.join(cmd[:12])} ...")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-2000:]
        raise FFmpegError(f"{desc} failed (exit {proc.returncode}):\n{tail}")


def probe(path: Path | str) -> dict:
    cmd = [
        ffprobe_bin(), "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed for {path}: {proc.stderr[-500:]}")
    return json.loads(proc.stdout)


def duration_of(path: Path | str) -> float:
    info = probe(path)
    return float(info["format"]["duration"])


def video_dimensions(path: Path | str) -> tuple[int, int]:
    info = probe(path)
    for s in info["streams"]:
        if s.get("codec_type") == "video":
            return int(s["width"]), int(s["height"])
    raise FFmpegError(f"No video stream in {path}")


def has_audio(path: Path | str) -> bool:
    info = probe(path)
    return any(s.get("codec_type") == "audio" for s in info["streams"])
