"""Central configuration loader.

Reads .env, validates required keys, exposes a typed `settings` object.
Optional keys (TikTok/Facebook/Instagram, LTX-2, remote Whisper) may be
empty — dependent features are skipped automatically.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

REQUIRED_KEYS = [
    "TELEGRAM_BOT_TOKEN",
    "OPENROUTER_API_KEY",
]


class ConfigError(RuntimeError):
    """Raised when a required configuration value is missing."""


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _get_int(key: str, default: int) -> int:
    raw = _get(key)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _resolve_path(raw: str) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else PROJECT_ROOT / p


@dataclass(frozen=True)
class Settings:
    # Required
    telegram_bot_token: str = field(default_factory=lambda: _get("TELEGRAM_BOT_TOKEN"))
    openrouter_api_key: str = field(default_factory=lambda: _get("OPENROUTER_API_KEY"))

    # LLM — comma-separated fallback list; the client tries each in order
    # when a model is unavailable (free models come and go on OpenRouter)
    openrouter_model: str = field(
        default_factory=lambda: _get(
            "OPENROUTER_MODEL",
            "qwen/qwen3-next-80b-a3b-instruct:free,"
            "meta-llama/llama-3.3-70b-instruct:free",
        )
    )

    # Gemini (Google AI Studio) — used as the final LLM fallback when all
    # OpenRouter models fail. Empty = disabled.
    gemini_api_key: str = field(default_factory=lambda: _get("GEMINI_API_KEY"))
    gemini_model: str = field(
        default_factory=lambda: _get("GEMINI_MODEL", "gemini-3-flash-preview")
    )

    # Trend reference (YouTube always used if key present; others optional)
    youtube_data_api_key: str = field(default_factory=lambda: _get("YOUTUBE_DATA_API_KEY"))
    tiktok_api_key: str = field(default_factory=lambda: _get("TIKTOK_API_KEY"))
    facebook_api_key: str = field(default_factory=lambda: _get("FACEBOOK_API_KEY"))
    instagram_api_key: str = field(default_factory=lambda: _get("INSTAGRAM_API_KEY"))

    # Google Sheets
    google_sheets_credentials_json: str = field(
        default_factory=lambda: _get(
            "GOOGLE_SHEETS_CREDENTIALS_JSON", "credentials/google_sheets_credentials.json"
        )
    )
    google_sheets_spreadsheet_id: str = field(
        default_factory=lambda: _get("GOOGLE_SHEETS_SPREADSHEET_ID")
    )

    # Whisper
    whisper_mode: str = field(default_factory=lambda: _get("WHISPER_MODE", "local").lower())
    whisper_model: str = field(default_factory=lambda: _get("WHISPER_MODEL", "small"))
    whisper_remote_url: str = field(default_factory=lambda: _get("WHISPER_REMOTE_URL"))

    # LTX-2 (optional, remote only)
    ltx2_remote_url: str = field(default_factory=lambda: _get("LTX2_REMOTE_URL"))

    # Kaggle (used by cloud/ setup scripts, not by the bot directly)
    kaggle_username: str = field(default_factory=lambda: _get("KAGGLE_USERNAME"))
    kaggle_key: str = field(default_factory=lambda: _get("KAGGLE_KEY"))

    # Pipeline tuning
    max_clips_per_video: int = field(default_factory=lambda: _get_int("MAX_CLIPS_PER_VIDEO", 8))
    clip_min_seconds: int = field(default_factory=lambda: _get_int("CLIP_MIN_SECONDS", 15))
    clip_max_seconds: int = field(default_factory=lambda: _get_int("CLIP_MAX_SECONDS", 60))

    # Directories
    work_dir: Path = field(default_factory=lambda: _resolve_path(_get("WORK_DIR", "data/jobs")))
    music_library_dir: Path = field(
        default_factory=lambda: _resolve_path(_get("MUSIC_LIBRARY_DIR", "music/library"))
    )
    overlay_library_dir: Path = field(
        default_factory=lambda: _resolve_path(_get("OVERLAY_LIBRARY_DIR", "assets/overlays"))
    )

    def validate(self) -> None:
        missing = [k for k in REQUIRED_KEYS if not _get(k)]
        if missing:
            raise ConfigError(
                "Missing required environment variables: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill them in."
            )
        if self.whisper_mode not in ("local", "remote"):
            raise ConfigError("WHISPER_MODE must be 'local' or 'remote'")
        if self.whisper_mode == "remote" and not self.whisper_remote_url:
            raise ConfigError("WHISPER_MODE=remote requires WHISPER_REMOTE_URL")

    @property
    def openrouter_models(self) -> list[str]:
        return [m.strip() for m in self.openrouter_model.split(",") if m.strip()]

    @property
    def sheets_enabled(self) -> bool:
        return bool(
            self.google_sheets_spreadsheet_id
            and _resolve_path(self.google_sheets_credentials_json).exists()
        )

    @property
    def sheets_credentials_path(self) -> Path:
        return _resolve_path(self.google_sheets_credentials_json)

    def ensure_dirs(self) -> None:
        for d in (self.work_dir, self.music_library_dir, self.overlay_library_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
