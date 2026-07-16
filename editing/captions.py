"""Animated captions from Whisper word timestamps → ASS subtitles → FFmpeg burn-in.

Styles:
  bold      — big white bold text, black outline
  outline   — white text, heavy outline, slight shadow
  highlight — karaoke-style: the spoken word pops in yellow
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from utils.ffmpeg_utils import run_ffmpeg

_STYLES = {
    "bold": (
        "Style: Default,Arial Black,64,&H00FFFFFF,&H00FFFF00,&H00000000,&H7F000000,"
        "-1,0,0,0,100,100,0,0,1,4,1,2,60,60,320,1"
    ),
    "outline": (
        "Style: Default,Arial,60,&H00FFFFFF,&H00FFFF00,&H00000000,&H7F000000,"
        "-1,0,0,0,100,100,0,0,1,6,2,2,60,60,320,1"
    ),
    "highlight": (
        "Style: Default,Arial Black,62,&H00FFFFFF,&H0000FFFF,&H00000000,&H7F000000,"
        "-1,0,0,0,100,100,0,0,1,4,1,2,60,60,320,1"
    ),
}

_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _clip_words(transcript: dict, clip_start: float, clip_end: float) -> list[dict]:
    """Words inside the clip window, times shifted so clip starts at 0."""
    words: list[dict] = []
    for seg in transcript["segments"]:
        for w in seg.get("words", []):
            if w["end"] <= clip_start or w["start"] >= clip_end:
                continue
            words.append(
                {
                    "start": max(0.0, w["start"] - clip_start),
                    "end": min(clip_end - clip_start, w["end"] - clip_start),
                    "word": w["word"],
                }
            )
    return words


def _group_words(words: list[dict], max_words: int = 4) -> list[list[dict]]:
    groups, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or w["word"].rstrip().endswith((".", "!", "?", ",")):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def build_ass(transcript: dict, clip_start: float, clip_end: float, style: str = "bold") -> str:
    style_line = _STYLES.get(style, _STYLES["bold"])
    lines = [_HEADER.format(style=style_line)]
    words = _clip_words(transcript, clip_start, clip_end)

    for group in _group_words(words):
        g_start, g_end = group[0]["start"], group[-1]["end"]
        if style == "highlight":
            # one dialogue event per word: current word yellow, rest white
            for i, w in enumerate(group):
                parts = []
                for j, w2 in enumerate(group):
                    txt = w2["word"].replace("{", "").replace("}", "")
                    if i == j:
                        parts.append(r"{\c&H00FFFF&}" + txt + r"{\c&HFFFFFF&}")
                    else:
                        parts.append(txt)
                end = group[i + 1]["start"] if i + 1 < len(group) else g_end
                lines.append(
                    f"Dialogue: 0,{_ts(w['start'])},{_ts(end)},Default,,0,0,0,,"
                    + r"{\fad(80,0)}" + " ".join(parts)
                )
        else:
            text = " ".join(w["word"].replace("{", "").replace("}", "") for w in group)
            lines.append(
                f"Dialogue: 0,{_ts(g_start)},{_ts(g_end)},Default,,0,0,0,,"
                + r"{\fad(100,60)}" + text
            )
    return "\n".join(lines) + "\n"


async def burn_captions(
    video: Path,
    transcript: dict,
    clip_start: float,
    clip_end: float,
    dest: Path,
    style: str = "bold",
) -> Path:
    """Render animated captions onto `video`. Returns dest (or copies video if no words)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    ass_text = build_ass(transcript, clip_start, clip_end, style)
    ass_path = dest.with_suffix(".ass")
    ass_path.write_text(ass_text, encoding="utf-8")

    # FFmpeg subtitles filter needs escaped path on Windows
    sub_arg = str(ass_path).replace("\\", "/").replace(":", "\\:")
    args = [
        "-i", str(video),
        "-vf", f"subtitles='{sub_arg}'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy",
        str(dest),
    ]
    await asyncio.to_thread(run_ffmpeg, args, "burn-captions")
    return dest
