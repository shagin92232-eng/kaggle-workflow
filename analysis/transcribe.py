"""Transcription via faster-whisper.

Two modes (WHISPER_MODE in .env):
  local  — run faster-whisper on this machine (CPU works, slower).
           The model downloads once into the local HF cache and is
           reused on every later run.
  remote — POST the audio to a FastAPI endpoint hosted on Kaggle /
           Lightning AI / HF Space (see cloud/). The cloud side also
           loads its model from a persisted dataset, so nothing is
           re-downloaded there either.

Output: word-level timestamp JSON:
{
  "language": "en",
  "segments": [{"start": 0.0, "end": 4.2, "text": "..",
                "words": [{"start": 0.0, "end": 0.4, "word": "So"}, ...]}]
}
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from config.settings import settings
from utils.ffmpeg_utils import run_ffmpeg
from utils.logger import get_logger

log = get_logger(__name__)

_local_model = None  # cached across jobs


def _extract_audio(video: Path, dest: Path) -> Path:
    """16 kHz mono WAV — smallest payload whisper accepts happily."""
    run_ffmpeg(
        ["-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)],
        desc="extract-audio",
    )
    return dest


def _load_local_model():
    """Load the model; if a local model directory is corrupted (e.g. an
    interrupted download left a half-written model.bin), wipe it and
    re-download once, then retry."""
    from faster_whisper import WhisperModel

    try:
        return WhisperModel(settings.whisper_model, device="auto", compute_type="auto")
    except (RuntimeError, OSError, ValueError) as exc:
        model_dir = Path(settings.whisper_model)
        if not model_dir.is_dir():
            raise  # a size name like "small" — nothing on disk to repair
        import shutil

        from faster_whisper import download_model

        log.warning(f"Model at {model_dir} failed to load ({exc}) — re-downloading it once…")
        shutil.rmtree(model_dir, ignore_errors=True)
        model_dir.mkdir(parents=True, exist_ok=True)
        download_model(model_dir.name, output_dir=str(model_dir))
        (model_dir / ".download-complete").touch()
        log.info(f"Model re-downloaded to {model_dir}")
        return WhisperModel(str(model_dir), device="auto", compute_type="auto")


def _transcribe_local_sync(audio: Path) -> dict:
    global _local_model

    if _local_model is None:
        log.info(f"Loading faster-whisper model '{settings.whisper_model}' (one-time per process)")
        _local_model = _load_local_model()

    segments, info = _local_model.transcribe(str(audio), word_timestamps=True)
    out = {"language": info.language, "segments": []}
    for seg in segments:
        out["segments"].append(
            {
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text.strip(),
                "words": [
                    {"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word.strip()}
                    for w in (seg.words or [])
                ],
            }
        )
    return out


async def _transcribe_remote(audio: Path) -> dict:
    url = settings.whisper_remote_url.rstrip("/") + "/transcribe"
    log.info(f"Remote transcription via {url}")
    async with httpx.AsyncClient(timeout=1800) as client:
        with open(audio, "rb") as f:
            resp = await client.post(url, files={"file": (audio.name, f, "audio/wav")})
        resp.raise_for_status()
        return resp.json()


async def transcribe(video: Path, workdir: Path) -> Path:
    """Transcribe `video`; returns path to the transcript JSON file."""
    audio = _extract_audio(video, workdir / "audio.wav")

    if settings.whisper_mode == "remote" and settings.whisper_remote_url:
        try:
            result = await _transcribe_remote(audio)
        except Exception as exc:  # noqa: BLE001 — fall back to local rather than dying
            log.warning(f"Remote whisper failed ({exc}); falling back to local model")
            result = await asyncio.to_thread(_transcribe_local_sync, audio)
    else:
        result = await asyncio.to_thread(_transcribe_local_sync, audio)

    out = workdir / "transcript.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info(f"Transcript saved: {out} ({len(result['segments'])} segments)")
    return out


def load_transcript(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def transcript_as_text(transcript: dict, with_timestamps: bool = True) -> str:
    """Flatten transcript for LLM prompts."""
    lines = []
    for seg in transcript["segments"]:
        if with_timestamps:
            lines.append(f"[{seg['start']:.1f}-{seg['end']:.1f}] {seg['text']}")
        else:
            lines.append(seg["text"])
    return "\n".join(lines)
