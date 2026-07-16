"""Pipeline stage error handling.

Every pipeline stage runs inside `stage()` — on failure it logs, notifies
the user on Telegram (stage name + likely cause + suggestion + partial
progress), and either aborts the job (fatal stages) or lets the caller
continue (per-clip stages), so one broken clip never kills the others.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from utils.logger import JobLogger

# Maps exception-text fragments to human suggestions
_SUGGESTIONS = [
    ("quota", "API quota may be exhausted — wait a while and try again."),
    ("rate", "Rate limit hit — wait a few minutes and try again."),
    ("401", "An API key looks invalid — check your .env values."),
    ("402", "OpenRouter credit/quota exhausted — use a ':free' model or wait for the daily reset."),
    ("403", "Access denied — check API key permissions / app approval."),
    ("ffmpeg", "FFmpeg processing failed — the video format may be unsupported."),
    ("not found", "A required file/tool was not found — check installation."),
    ("timed out", "The operation timed out — the file may be too large; try a shorter video."),
    ("unsupported", "This video format is not supported — try re-uploading as MP4."),
    ("download", "Video download failed — check that the link is public and valid."),
]


def suggest_fix(exc: Exception) -> str:
    text = f"{type(exc).__name__} {exc}".lower()
    for needle, suggestion in _SUGGESTIONS:
        if needle in text:
            return suggestion
    return "Check the logs for details, then retry. If it repeats, report this error message."


@dataclass
class StageError(Exception):
    stage: str
    original: Exception
    fatal: bool = True

    def __str__(self) -> str:
        return f"stage '{self.stage}' failed: {self.original}"


@dataclass
class ErrorReporter:
    """Sends failure reports to the user via a notify callback."""

    notify: Callable[[str], Awaitable[None]]
    log: JobLogger
    completed_clips: list[str] = field(default_factory=list)

    def record_completed_clip(self, title: str) -> None:
        self.completed_clips.append(title)

    async def report(self, stage: str, exc: Exception) -> None:
        self.log.with_stage(stage).error(
            f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        )
        progress = ""
        if self.completed_clips:
            done = "\n".join(f"  ✅ {t}" for t in self.completed_clips)
            progress = f"\n\nCompleted so far:\n{done}"
        await self.notify(
            f"⚠️ Error at stage: {stage}\n"
            f"Reason: {type(exc).__name__}: {exc}\n"
            f"Suggestion: {suggest_fix(exc)}"
            f"{progress}"
        )


async def stage(
    name: str,
    coro_fn: Callable[[], Awaitable],
    reporter: ErrorReporter,
    fatal: bool = True,
):
    """Run one pipeline stage with unified error handling.

    fatal=True  → raises StageError so the orchestrator aborts the job.
    fatal=False → reports + returns None so remaining clips keep processing.
    """
    try:
        return await coro_fn()
    except Exception as exc:  # noqa: BLE001 — deliberate catch-all boundary
        await reporter.report(name, exc)
        if fatal:
            raise StageError(stage=name, original=exc, fatal=True) from exc
        return None
