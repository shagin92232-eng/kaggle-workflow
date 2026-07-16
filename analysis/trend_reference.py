"""Conditional multi-platform trend reference.

YouTube Data API is used whenever a key is present (free quota).
TikTok / Facebook / Instagram are only queried when their keys exist in
.env — otherwise silently skipped. Style/pattern reference only; content
is never copied.
"""

from __future__ import annotations

import httpx

from config.settings import settings
from utils.logger import get_logger

log = get_logger(__name__)

_YT_SEARCH = "https://www.googleapis.com/youtube/v3/search"
_YT_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"


async def _youtube_trends(topic: str) -> list[str]:
    if not settings.youtube_data_api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                _YT_SEARCH,
                params={
                    "part": "snippet",
                    "q": f"{topic} #shorts",
                    "type": "video",
                    "videoDuration": "short",
                    "order": "viewCount",
                    "maxResults": 8,
                    "key": settings.youtube_data_api_key,
                },
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            ids = [i["id"]["videoId"] for i in items if i.get("id", {}).get("videoId")]
            titles = [i["snippet"]["title"] for i in items]
            stats = {}
            if ids:
                r2 = await client.get(
                    _YT_VIDEOS,
                    params={
                        "part": "statistics",
                        "id": ",".join(ids),
                        "key": settings.youtube_data_api_key,
                    },
                )
                if r2.status_code == 200:
                    stats = {
                        v["id"]: v.get("statistics", {}).get("viewCount", "?")
                        for v in r2.json().get("items", [])
                    }
            lines = []
            for i, title in zip(items, titles):
                vid = i["id"]["videoId"]
                lines.append(f"- \"{title}\" ({stats.get(vid, '?')} views)")
            return lines
    except Exception as exc:  # noqa: BLE001 — trends are optional context
        log.warning(f"YouTube trend lookup failed, skipping: {exc}")
        return []


async def _tiktok_trends(topic: str) -> list[str]:
    if not settings.tiktok_api_key:
        return []
    # TikTok Research API requires app approval; endpoint left as integration
    # point — implement once access is granted.
    log.info("TikTok key present but Research API integration not configured — skipping")
    return []


async def _meta_trends(topic: str, platform: str, key: str) -> list[str]:
    if not key:
        return []
    log.info(f"{platform} key present but Graph API integration not configured — skipping")
    return []


async def build_trend_summary(topic: str) -> str:
    """Return a short textual style reference for the LLM ('' if nothing found)."""
    sections: list[str] = []

    yt = await _youtube_trends(topic)
    if yt:
        sections.append("Top viral YouTube Shorts in this niche:\n" + "\n".join(yt))

    for fetch in (
        _tiktok_trends(topic),
        _meta_trends(topic, "Facebook", settings.facebook_api_key),
        _meta_trends(topic, "Instagram", settings.instagram_api_key),
    ):
        rows = await fetch
        if rows:
            sections.append("\n".join(rows))

    summary = "\n\n".join(sections)
    if summary:
        summary += (
            "\n\nUse these ONLY to understand what style/hook patterns are currently "
            "popular. Do not copy any content."
        )
    return summary
