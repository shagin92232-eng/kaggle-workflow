"""Background music selection + mixing.

Tracks live in MUSIC_LIBRARY_DIR (pre-downloaded from YouTube Audio Library,
Facebook Sound Collection, Pixabay, Mixkit — see README). Selection is by
filename keyword match against a mood hint, else random. Music is ducked
under speech at a configurable volume and looped/trimmed to clip length.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

from config.settings import settings
from utils.ffmpeg_utils import duration_of, has_audio, run_ffmpeg
from utils.logger import get_logger

log = get_logger(__name__)

_AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")


def list_tracks() -> list[Path]:
    lib = settings.music_library_dir
    if not lib.exists():
        return []
    return sorted(p for p in lib.rglob("*") if p.suffix.lower() in _AUDIO_EXTS)


def pick_track(mood_hint: str = "") -> Path | None:
    """Keyword-match mood hint against filenames; random fallback; None if library empty."""
    tracks = list_tracks()
    if not tracks:
        log.warning("Music library is empty — skipping background music")
        return None
    hint_words = [w.lower() for w in mood_hint.split() if len(w) > 2]
    if hint_words:
        scored = [
            (sum(w in t.stem.lower() for w in hint_words), t) for t in tracks
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored[0][0] > 0:
            return scored[0][1]
    return random.choice(tracks)


async def mix_music(
    video: Path,
    dest: Path,
    track: Path | None,
    music_volume: float = 0.18,
) -> Path:
    """Mix `track` under the video's speech. If no track, pass video through."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if track is None or not track.exists():
        # passthrough copy keeps the pipeline uniform
        args = ["-i", str(video), "-c", "copy", str(dest)]
        await asyncio.to_thread(run_ffmpeg, args, "music-passthrough")
        return dest

    clip_len = duration_of(video)
    vol = max(0.0, min(1.0, music_volume))

    if has_audio(video):
        filter_complex = (
            f"[1:a]aloop=loop=-1:size=2e9,atrim=0:{clip_len:.2f},"
            f"volume={vol},afade=t=in:d=1,afade=t=out:st={max(0, clip_len-1.5):.2f}:d=1.5[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        maps = ["-map", "0:v", "-map", "[aout]"]
    else:
        filter_complex = (
            f"[1:a]aloop=loop=-1:size=2e9,atrim=0:{clip_len:.2f},"
            f"volume={vol},afade=t=in:d=1,afade=t=out:st={max(0, clip_len-1.5):.2f}:d=1.5[aout]"
        )
        maps = ["-map", "0:v", "-map", "[aout]"]

    args = [
        "-i", str(video),
        "-i", str(track),
        "-filter_complex", filter_complex,
        *maps,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(dest),
    ]
    await asyncio.to_thread(run_ffmpeg, args, "music-mix")
    return dest
