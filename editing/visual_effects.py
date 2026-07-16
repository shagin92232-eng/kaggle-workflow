"""Face-safe visual effects — FFmpeg filter chains only.

Every effect here operates on frame/color/motion level. There is NO
face-detection, face-modification, face-swap or deepfake code in this
module, and none may ever be added (see agent/system_prompt.FACE_SAFETY_NOTE).

Available effects (composable):
  ken_burns    — slow zoom-in (Ken Burns)
  zoom_punch   — quick punch-in at the start for emphasis
  color_grade  — punchy contrast/saturation grade
  film_grain   — subtle noise + vignette
  vignette     — vignette only
  glitch_vhs   — RGB shift + noise VHS look
  speed_ramp   — 0.85x first 20%, then normal (subtle emphasis)
  freeze_frame — hold the first frame 0.7s
  light_leak   — overlay a random light-leak/particle video from assets/overlays
  camera_shake — slight periodic translate wobble
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

from config.settings import settings
from utils.ffmpeg_utils import duration_of, run_ffmpeg
from utils.logger import get_logger

log = get_logger(__name__)

SAFE_EFFECTS = [
    "ken_burns", "zoom_punch", "color_grade", "film_grain", "vignette",
    "glitch_vhs", "speed_ramp", "freeze_frame", "light_leak", "camera_shake",
]

# effects that make sense together by default
DEFAULT_COMBO = ["zoom_punch", "color_grade", "film_grain"]


def _vf_for(effect: str, clip_len: float) -> str | None:
    if effect == "ken_burns":
        frames = int(clip_len * 30)
        return (
            f"zoompan=z='min(1.0+0.10*on/{max(frames,1)},1.10)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30"
        )
    if effect == "zoom_punch":
        # punch to 1.15x for the first 0.5s, snap back
        return (
            "scale=1080:1920,zoompan=z='if(lte(in_time,0.5),1.15,1.0)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30"
        )
    if effect == "color_grade":
        return "eq=contrast=1.08:saturation=1.25:brightness=0.02"
    if effect == "film_grain":
        return "noise=alls=8:allf=t,vignette=PI/5"
    if effect == "vignette":
        return "vignette=PI/5"
    if effect == "glitch_vhs":
        return "chromashift=cbh=4:crh=-4,noise=alls=12:allf=t"
    if effect == "camera_shake":
        return (
            "crop=iw-16:ih-16:x='8+6*sin(2*PI*t*1.3)':y='8+6*cos(2*PI*t*1.7)',"
            "scale=1080:1920"
        )
    return None


def _pick_overlay() -> Path | None:
    lib = settings.overlay_library_dir
    if not lib.exists():
        return None
    vids = [p for p in lib.rglob("*") if p.suffix.lower() in (".mp4", ".mov", ".webm")]
    return random.choice(vids) if vids else None


async def apply_effects(video: Path, dest: Path, effects: list[str]) -> tuple[Path, list[str]]:
    """Apply the requested face-safe effects. Returns (output, actually_applied)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    effects = [e for e in effects if e in SAFE_EFFECTS] or list(DEFAULT_COMBO)
    clip_len = duration_of(video)
    applied: list[str] = []

    vf_parts: list[str] = []
    speed_ramp = "speed_ramp" in effects
    freeze = "freeze_frame" in effects
    overlay = _pick_overlay() if "light_leak" in effects else None

    for e in effects:
        if e in ("speed_ramp", "freeze_frame", "light_leak"):
            continue  # handled separately
        vf = _vf_for(e, clip_len)
        if vf:
            vf_parts.append(vf)
            applied.append(e)

    if freeze:
        vf_parts.append("tpad=start_mode=clone:start_duration=0.7")
        applied.append("freeze_frame")

    current = video
    if vf_parts:
        step1 = dest.with_name(dest.stem + "_fx.mp4")
        args = ["-i", str(current), "-vf", ",".join(vf_parts),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "copy", str(step1)]
        await asyncio.to_thread(run_ffmpeg, args, "visual-effects")
        current = step1

    if overlay is not None:
        step2 = dest.with_name(dest.stem + "_ovl.mp4")
        fc = (
            "[1:v]scale=1080:1920,loop=-1:size=9999,setpts=N/FRAME_RATE/TB[ov];"
            "[0:v][ov]blend=all_mode=screen:all_opacity=0.35[v]"
        )
        args = ["-i", str(current), "-i", str(overlay),
                "-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "copy", "-t", f"{clip_len:.2f}", str(step2)]
        await asyncio.to_thread(run_ffmpeg, args, "light-leak-overlay")
        current = step2
        applied.append("light_leak")

    if speed_ramp:
        step3 = dest.with_name(dest.stem + "_ramp.mp4")
        ramp_end = clip_len * 0.2
        fc = (
            f"[0:v]trim=0:{ramp_end:.2f},setpts=PTS/0.85[v1];"
            f"[0:v]trim={ramp_end:.2f},setpts=PTS-STARTPTS[v2];"
            f"[0:a]atrim=0:{ramp_end:.2f},atempo=0.85[a1];"
            f"[0:a]atrim={ramp_end:.2f},asetpts=PTS-STARTPTS[a2];"
            "[v1][a1][v2][a2]concat=n=2:v=1:a=1[v][a]"
        )
        args = ["-i", str(current), "-filter_complex", fc,
                "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", str(step3)]
        try:
            await asyncio.to_thread(run_ffmpeg, args, "speed-ramp")
            current = step3
            applied.append("speed_ramp")
        except Exception as exc:  # noqa: BLE001 — ramp is cosmetic; audio-less clips can fail here
            log.warning(f"speed_ramp skipped: {exc}")

    if current == video:
        args = ["-i", str(video), "-c", "copy", str(dest)]
        await asyncio.to_thread(run_ffmpeg, args, "effects-passthrough")
    else:
        current.replace(dest)
    return dest, applied
