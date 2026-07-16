"""Scene boundary detection via PySceneDetect."""

from __future__ import annotations

import asyncio
from pathlib import Path

from utils.logger import get_logger

log = get_logger(__name__)


def _detect_sync(video: Path, threshold: float) -> list[tuple[float, float]]:
    from scenedetect import ContentDetector, detect

    scene_list = detect(str(video), ContentDetector(threshold=threshold))
    scenes = [(s.get_seconds(), e.get_seconds()) for s, e in scene_list]
    return scenes


async def detect_scenes(video: Path, threshold: float = 27.0) -> list[tuple[float, float]]:
    """Return list of (start_s, end_s) scene tuples. Empty list on single-shot video."""
    scenes = await asyncio.to_thread(_detect_sync, video, threshold)
    log.info(f"Detected {len(scenes)} scenes in {video.name}")
    return scenes


def scenes_as_text(scenes: list[tuple[float, float]], limit: int = 200) -> str:
    lines = [f"scene {i+1}: {s:.1f}s → {e:.1f}s" for i, (s, e) in enumerate(scenes[:limit])]
    return "\n".join(lines) if lines else "(no scene cuts detected — single continuous shot)"
