"""Optional LTX-2 B-roll / motion-graphics generation via a cloud endpoint.

The model is hosted remotely (Kaggle / Lightning AI / HF Space — see
cloud/README.md). The endpoint downloads its weights ONCE, persists them,
and reloads from the persisted copy on every restart — no re-downloading.

If LTX2_REMOTE_URL is empty this module is a graceful no-op: the pipeline
simply skips B-roll generation.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from config.settings import settings
from utils.logger import get_logger

log = get_logger(__name__)


def ltx2_available() -> bool:
    return bool(settings.ltx2_remote_url)


async def generate_broll(prompt: str, dest: Path, duration_s: int = 4) -> Path | None:
    """Ask the remote LTX-2 endpoint for a short generated clip.

    Returns the local file path, or None when disabled/unavailable
    (callers must treat None as 'skip B-roll').
    """
    if not ltx2_available():
        return None
    url = settings.ltx2_remote_url.rstrip("/") + "/generate"
    try:
        async with httpx.AsyncClient(timeout=900) as client:
            resp = await client.post(url, json={"prompt": prompt, "duration": duration_s})
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            log.info(f"LTX-2 B-roll generated -> {dest}")
            return dest
    except Exception as exc:  # noqa: BLE001 — B-roll is optional, never fatal
        log.warning(f"LTX-2 generation skipped ({exc})")
        return None
