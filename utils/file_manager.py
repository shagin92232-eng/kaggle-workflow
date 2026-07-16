"""Per-job temp directory management with per-user isolation.

Layout:  WORK_DIR/<user_id>/<job_id>/
             source/    downloaded or received input video
             clips/     intermediate per-clip artifacts
             output/    final exported shorts
             state.json pipeline state (see revision/state_manager.py)
"""

from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path

from config.settings import settings


class JobWorkspace:
    def __init__(self, user_id: int | str, job_id: str | None = None):
        self.user_id = str(user_id)
        self.job_id = job_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.root = settings.work_dir / self.user_id / self.job_id
        self.source_dir = self.root / "source"
        self.clips_dir = self.root / "clips"
        self.output_dir = self.root / "output"
        for d in (self.source_dir, self.clips_dir, self.output_dir):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    def clip_dir(self, clip_index: int) -> Path:
        d = self.clips_dir / f"clip_{clip_index:02d}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def cleanup_intermediates(self) -> None:
        """Remove bulky intermediates, keep outputs + state for revisions."""
        shutil.rmtree(self.source_dir, ignore_errors=True)
        shutil.rmtree(self.clips_dir, ignore_errors=True)

    def destroy(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    @classmethod
    def load(cls, user_id: int | str, job_id: str) -> "JobWorkspace":
        """Reattach to an existing job (used by the revision loop)."""
        ws = cls.__new__(cls)
        ws.user_id = str(user_id)
        ws.job_id = job_id
        ws.root = settings.work_dir / ws.user_id / job_id
        ws.source_dir = ws.root / "source"
        ws.clips_dir = ws.root / "clips"
        ws.output_dir = ws.root / "output"
        for d in (ws.source_dir, ws.clips_dir, ws.output_dir):
            d.mkdir(parents=True, exist_ok=True)
        return ws

    @classmethod
    def latest_for_user(cls, user_id: int | str) -> "JobWorkspace | None":
        user_root = settings.work_dir / str(user_id)
        if not user_root.exists():
            return None
        jobs = sorted((p for p in user_root.iterdir() if p.is_dir()), key=lambda p: p.name)
        if not jobs:
            return None
        return cls.load(user_id, jobs[-1].name)
