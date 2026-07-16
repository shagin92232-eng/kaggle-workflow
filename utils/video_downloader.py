"""Download source videos.

- YouTube / TikTok / Instagram / Facebook / etc. → yt-dlp
- Direct file URLs (.mp4 ...) → plain HTTP download
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import yt_dlp

from utils.logger import get_logger

log = get_logger(__name__)

_DIRECT_EXTS = (".mp4", ".mov", ".mkv", ".webm", ".avi")

URL_RE = re.compile(r"https?://\S+")


def extract_url(text: str) -> str | None:
    m = URL_RE.search(text or "")
    return m.group(0) if m else None


def download_video(url: str, dest_dir: Path) -> Path:
    """Download `url` into `dest_dir`, return the local file path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    if url.lower().split("?")[0].endswith(_DIRECT_EXTS):
        return _download_direct(url, dest_dir)
    return _download_ytdlp(url, dest_dir)


def _download_direct(url: str, dest_dir: Path) -> Path:
    name = url.split("?")[0].rstrip("/").split("/")[-1] or "video.mp4"
    out = dest_dir / name
    log.info(f"Direct download: {url} -> {out}")
    with httpx.stream("GET", url, follow_redirects=True, timeout=600) as r:
        r.raise_for_status()
        with open(out, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1 << 20):
                f.write(chunk)
    return out


def _download_ytdlp(url: str, dest_dir: Path) -> Path:
    log.info(f"yt-dlp download: {url}")
    opts = {
        "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
        # Cap at 1080p — plenty for 9:16 crops, keeps downloads fast
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
    # merge_output_format may change the extension
    if not path.exists():
        path = path.with_suffix(".mp4")
    if not path.exists():
        raise FileNotFoundError(f"yt-dlp reported success but file not found for {url}")
    return path
