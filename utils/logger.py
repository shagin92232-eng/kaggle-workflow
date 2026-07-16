"""Structured logging with timestamps, job IDs, and stage names."""

from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"

logging.basicConfig(level=logging.INFO, format=_FORMAT, stream=sys.stdout)
# Silence noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class JobLogger:
    """Logger adapter that prefixes every line with job/stage context."""

    def __init__(self, job_id: str, stage: str = "-"):
        self._log = logging.getLogger("pipeline")
        self.job_id = job_id
        self.stage = stage

    def with_stage(self, stage: str) -> "JobLogger":
        return JobLogger(self.job_id, stage)

    def _fmt(self, msg: str) -> str:
        return f"[job={self.job_id}] [stage={self.stage}] {msg}"

    def info(self, msg: str) -> None:
        self._log.info(self._fmt(msg))

    def warning(self, msg: str) -> None:
        self._log.warning(self._fmt(msg))

    def error(self, msg: str) -> None:
        self._log.error(self._fmt(msg))
