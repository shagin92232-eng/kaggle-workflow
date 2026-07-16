"""Per-clip title/caption/hashtags generation via Qwen3."""

from __future__ import annotations

from agent import llm_client, system_prompt
from utils.logger import get_logger

log = get_logger(__name__)


async def generate_title(
    clip_text: str,
    hook: str,
    trend_summary: str = "",
    existing_titles: list[str] | None = None,
) -> dict:
    """Returns {"title": str, "caption": str, "hashtags": [str, ...]}."""
    user = (
        f"CLIP TRANSCRIPT:\n{clip_text[:4000]}\n\n"
        f"WHY THIS CLIP WAS CHOSEN (hook): {hook}\n"
    )
    if trend_summary:
        user += f"\nTREND STYLE REFERENCE:\n{trend_summary[:2000]}\n"
    if existing_titles:
        user += (
            "\nTitles already used for other clips of this video "
            f"(yours must be different): {existing_titles}\n"
        )
    user += "\nGenerate the JSON now."

    result = await llm_client.chat_json(
        system_prompt.TITLE_GENERATION_SYSTEM, user, temperature=0.8, max_tokens=800
    )
    if isinstance(result, list):  # model occasionally wraps the object in an array
        result = next((x for x in result if isinstance(x, dict)), {})
    if not isinstance(result, dict):
        result = {}
    title = str(result.get("title", "")).strip() or "Viral Moment 🔥"
    caption = str(result.get("caption", "")).strip()
    hashtags = [str(h).strip() for h in result.get("hashtags", []) if str(h).strip()]
    hashtags = [h if h.startswith("#") else f"#{h}" for h in hashtags][:15]
    return {"title": title, "caption": caption, "hashtags": hashtags}
