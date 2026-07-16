"""Pipeline state persistence — enables revisions without a full re-run.

State is stored per job as JSON (workspace/state.json) and captures every
knob used to produce each clip, so the revision handler can re-run only the
stages that a change request touches.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ClipState:
    index: int
    start_s: float
    end_s: float
    hook: str = ""
    virality_score: float = 0.0
    title: str = ""
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    caption_style: str = "bold"          # bold | outline | highlight
    music_track: str = ""                # filename inside music library ("" = none)
    music_volume: float = 0.18           # relative to speech
    effects: list[str] = field(default_factory=list)  # applied face-safe effects
    output_file: str = ""                # final mp4 path
    status: str = "pending"              # pending | done | failed


@dataclass
class JobState:
    job_id: str
    user_id: str
    source_url: str = ""
    source_file: str = ""
    transcript_file: str = ""            # word-level whisper JSON
    scenes: list[list[float]] = field(default_factory=list)
    trend_summary: str = ""
    user_instruction: str = ""
    clips: list[ClipState] = field(default_factory=list)

    # ---------- persistence ----------

    def save(self, path: Path) -> None:
        data = asdict(self)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "JobState":
        data = json.loads(path.read_text(encoding="utf-8"))
        clips = [ClipState(**c) for c in data.pop("clips", [])]
        state = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__ and k != "clips"})
        state.clips = clips
        return state

    # ---------- helpers ----------

    def clip(self, index: int) -> ClipState | None:
        for c in self.clips:
            if c.index == index:
                return c
        return None
