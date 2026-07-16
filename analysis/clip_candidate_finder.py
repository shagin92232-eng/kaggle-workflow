"""Find all viral-potential clip candidates using Qwen3."""

from __future__ import annotations

from config.settings import settings
from agent import llm_client, system_prompt
from analysis.scene_detect import scenes_as_text
from analysis.transcribe import transcript_as_text
from utils.logger import get_logger

log = get_logger(__name__)

# Keep prompts within a safe context budget
_MAX_TRANSCRIPT_CHARS = 60_000


async def find_candidates(
    transcript: dict,
    scenes: list[tuple[float, float]],
    trend_summary: str = "",
    user_instruction: str = "",
) -> list[dict]:
    """Return ranked candidate list:
    [{"start", "end", "hook", "virality_score", "suggested_effects"}, ...]
    capped at MAX_CLIPS_PER_VIDEO and clamped to CLIP_MIN/MAX_SECONDS.
    """
    text = transcript_as_text(transcript)
    if len(text) > _MAX_TRANSCRIPT_CHARS:
        log.warning("Transcript truncated for LLM prompt")
        text = text[:_MAX_TRANSCRIPT_CHARS] + "\n[...transcript truncated...]"

    user = (
        f"TRANSCRIPT (with [start-end] second timestamps):\n{text}\n\n"
        f"SCENE CUTS:\n{scenes_as_text(scenes)}\n"
    )
    if trend_summary:
        user += f"\nCURRENT TREND STYLE REFERENCE (for style, do NOT copy content):\n{trend_summary}\n"
    if user_instruction:
        user += f"\nUSER INSTRUCTION (obey where possible):\n{user_instruction}\n"
    user += "\nReturn the JSON array of viral clip candidates now."

    raw = await llm_client.chat_json(
        system_prompt.clip_selection_prompt(settings.clip_min_seconds, settings.clip_max_seconds),
        user,
        temperature=0.4,
        max_tokens=4000,
    )

    if isinstance(raw, dict):  # model wrapped the array in an object
        raw = raw.get("clips") or raw.get("candidates") or []

    candidates: list[dict] = []
    for item in raw:
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        # Clamp duration to configured bounds
        if end - start > settings.clip_max_seconds:
            end = start + settings.clip_max_seconds
        if end - start < settings.clip_min_seconds:
            end = start + settings.clip_min_seconds
        candidates.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "hook": str(item.get("hook", "")),
                "virality_score": float(item.get("virality_score", 0)),
                "suggested_effects": list(item.get("suggested_effects", [])),
            }
        )

    candidates.sort(key=lambda c: c["virality_score"], reverse=True)
    capped = candidates[: settings.max_clips_per_video]
    log.info(f"LLM proposed {len(candidates)} candidates, keeping {len(capped)}")
    return capped
