"""Unit tests for config loading."""

from config.settings import Settings


def test_settings_load():
    s = Settings()
    assert s.whisper_mode in ("local", "remote")
    assert s.max_clips_per_video > 0
    assert s.clip_min_seconds < s.clip_max_seconds


def test_dirs_resolve_absolute():
    s = Settings()
    assert s.work_dir.is_absolute()
    assert s.music_library_dir.is_absolute()
