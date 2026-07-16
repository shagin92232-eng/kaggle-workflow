"""Google Sheets logging — one row per generated clip.

Disabled automatically (no-op) when GOOGLE_SHEETS_SPREADSHEET_ID is empty
or the credentials file is missing, so the pipeline never blocks on it.
"""

from __future__ import annotations

import asyncio
import datetime as _dt

from config.settings import settings
from utils.logger import get_logger

log = get_logger(__name__)

HEADER = [
    "timestamp", "user_id", "job_id", "source_url",
    "clip_index", "clip_title", "start_s", "end_s",
    "music_track", "output_file", "status",
]


class SheetsLogger:
    def __init__(self) -> None:
        self._ws = None
        if not settings.sheets_enabled:
            log.info("Google Sheets logging disabled (no spreadsheet ID or credentials).")
            return
        try:
            import gspread

            client = gspread.service_account(filename=str(settings.sheets_credentials_path))
            sheet = client.open_by_key(settings.google_sheets_spreadsheet_id)
            self._ws = sheet.sheet1
            if not self._ws.row_values(1):
                self._ws.append_row(HEADER)
        except Exception as exc:  # noqa: BLE001 — sheets must never break the pipeline
            log.warning(f"Google Sheets init failed, logging disabled: {exc}")
            self._ws = None

    @property
    def enabled(self) -> bool:
        return self._ws is not None

    def _append(self, row: list) -> None:
        if self._ws is None:
            return
        try:
            self._ws.append_row([str(x) for x in row], value_input_option="RAW")
        except Exception as exc:  # noqa: BLE001
            log.warning(f"Google Sheets append failed: {exc}")

    async def log_clip(
        self,
        user_id: int | str,
        job_id: str,
        source_url: str,
        clip_index: int,
        clip_title: str,
        start_s: float,
        end_s: float,
        music_track: str,
        output_file: str,
        status: str,
    ) -> None:
        row = [
            _dt.datetime.now().isoformat(timespec="seconds"),
            user_id, job_id, source_url,
            clip_index, clip_title, round(start_s, 2), round(end_s, 2),
            music_track, output_file, status,
        ]
        # gspread is sync — keep the event loop free
        await asyncio.to_thread(self._append, row)


sheets_logger = SheetsLogger()
