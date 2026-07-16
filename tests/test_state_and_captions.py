"""Unit tests for state persistence and caption ASS generation."""

from pathlib import Path

from editing.captions import build_ass
from revision.state_manager import ClipState, JobState

TRANSCRIPT = {
    "language": "en",
    "segments": [
        {
            "start": 10.0,
            "end": 13.0,
            "text": "Hello world this is a test.",
            "words": [
                {"start": 10.0, "end": 10.4, "word": "Hello"},
                {"start": 10.5, "end": 10.9, "word": "world"},
                {"start": 11.0, "end": 11.3, "word": "this"},
                {"start": 11.4, "end": 11.6, "word": "is"},
                {"start": 11.7, "end": 11.9, "word": "a"},
                {"start": 12.0, "end": 12.5, "word": "test."},
            ],
        }
    ],
}


def test_state_roundtrip(tmp_path: Path):
    state = JobState(job_id="j1", user_id="u1", source_url="http://x")
    state.clips = [ClipState(index=1, start_s=10, end_s=40, title="T1", hashtags=["#a"])]
    p = tmp_path / "state.json"
    state.save(p)

    loaded = JobState.load(p)
    assert loaded.job_id == "j1"
    assert loaded.clips[0].title == "T1"
    assert loaded.clip(1).hashtags == ["#a"]
    assert loaded.clip(99) is None


def test_build_ass_contains_words():
    ass = build_ass(TRANSCRIPT, clip_start=10.0, clip_end=13.0, style="bold")
    assert "[Script Info]" in ass
    assert "Hello" in ass
    assert "Dialogue:" in ass
    # word times shifted to clip-relative (starts near 0:00:00.00)
    assert "0:00:00.00" in ass


def test_build_ass_highlight_style():
    ass = build_ass(TRANSCRIPT, clip_start=10.0, clip_end=13.0, style="highlight")
    # highlight style emits per-word color overrides
    assert r"\c&H00FFFF&" in ass


def test_build_ass_outside_window_empty():
    ass = build_ass(TRANSCRIPT, clip_start=100.0, clip_end=120.0)
    assert "Dialogue:" not in ass
