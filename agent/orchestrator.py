"""Main pipeline orchestrator.

Coordinates: download → transcribe → scene-detect → trend reference →
candidate finding → per-clip edit loop → delivery + Sheets logging.

Per-clip failures are non-fatal: each clip is wrapped independently so one
broken clip never stops the others (errors/error_handler.stage).
"""

from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from analysis import clip_candidate_finder, scene_detect, transcribe
from analysis.trend_reference import build_trend_summary
from config.settings import settings
from editing import captions, clip_extract, final_merge, music_sfx, title_generator, visual_effects
from editing.vertical_reframe import reframe_vertical
from errors.error_handler import ErrorReporter, StageError, stage
from revision.state_manager import ClipState, JobState
from sheets.google_sheets import sheets_logger
from utils.file_manager import JobWorkspace
from utils.logger import JobLogger
from utils.video_downloader import download_video

# Callbacks the bot layer provides
Notify = Callable[[str], Awaitable[None]]
SendClip = Callable[[Path, str], Awaitable[None]]  # (file, caption_text)


def _clip_transcript_text(transcript: dict, start: float, end: float) -> str:
    parts = [
        seg["text"]
        for seg in transcript["segments"]
        if seg["end"] > start and seg["start"] < end
    ]
    return " ".join(parts)


def format_delivery_caption(clip: ClipState) -> str:
    tags = " ".join(clip.hashtags)
    return f"🎬 {clip.title}\n\n{clip.caption}\n\n{tags}".strip()


async def run_pipeline(
    user_id: int,
    source: str | Path,
    user_instruction: str,
    notify: Notify,
    send_clip: SendClip,
) -> JobState | None:
    """Full pipeline for one long video. `source` is a URL or a local file path."""
    ws = JobWorkspace(user_id)
    log = JobLogger(ws.job_id)
    reporter = ErrorReporter(notify=notify, log=log)

    state = JobState(job_id=ws.job_id, user_id=str(user_id))
    state.user_instruction = user_instruction or ""

    try:
        # ---------- 1. acquire the video ----------
        if isinstance(source, Path):
            state.source_file = str(source)
            state.source_url = "(telegram upload)"
            video = source
        else:
            state.source_url = source
            await notify("⬇️ Downloading video…")
            video = await stage(
                "video-download",
                lambda: _download(source, ws),
                reporter,
            )
            state.source_file = str(video)
        state.save(ws.state_path)

        # ---------- 2. analysis ----------
        await notify("🎧 Transcribing (Whisper)…")
        transcript_path = await stage(
            "transcription",
            lambda: transcribe.transcribe(video, ws.root),
            reporter,
        )
        state.transcript_file = str(transcript_path)
        transcript = transcribe.load_transcript(transcript_path)

        await notify("🎬 Detecting scenes…")
        scenes = await stage(
            "scene-detection",
            lambda: scene_detect.detect_scenes(video),
            reporter,
            fatal=False,
        ) or []
        state.scenes = [[s, e] for s, e in scenes]

        # trend reference is optional context — never fatal
        trend = await stage(
            "trend-reference",
            lambda: build_trend_summary(_clip_transcript_text(transcript, 0, 120)[:200]),
            reporter,
            fatal=False,
        ) or ""
        state.trend_summary = trend

        await notify("🧠 Finding viral moments (Qwen3)…")
        candidates = await stage(
            "clip-candidate-finding",
            lambda: clip_candidate_finder.find_candidates(
                transcript, scenes, trend, user_instruction
            ),
            reporter,
        )
        if not candidates:
            await notify(
                "😕 No viral-potential moments were found in this video. "
                "Try a video with clearer speech or send an instruction "
                "(e.g. 'focus on funny moments')."
            )
            return state

        await notify(f"✂️ {len(candidates)} viral moment(s) found — producing clips…")
        state.clips = [
            ClipState(
                index=i + 1,
                start_s=c["start"],
                end_s=c["end"],
                hook=c["hook"],
                virality_score=c["virality_score"],
                effects=c.get("suggested_effects", []),
            )
            for i, c in enumerate(candidates)
        ]
        state.save(ws.state_path)

        # ---------- 3. per-clip loop (independent failures) ----------
        for clip in state.clips:
            ok = await _produce_clip(ws, state, transcript, clip, reporter, notify, send_clip)
            clip.status = "done" if ok else "failed"
            state.save(ws.state_path)

        done = sum(1 for c in state.clips if c.status == "done")
        failed = len(state.clips) - done
        summary = f"✅ Finished: {done}/{len(state.clips)} clips delivered."
        if failed:
            summary += f" ({failed} failed — see errors above.)"
        summary += "\n💬 To revise a clip, just reply e.g.: “clip 2: change the music”."
        await notify(summary)
        return state

    except StageError:
        # already reported to the user by ErrorReporter
        state.save(ws.state_path)
        return state


async def _download(source: str, ws: JobWorkspace) -> Path:
    import asyncio

    return await asyncio.to_thread(download_video, source, ws.source_dir)


async def _produce_clip(
    ws: JobWorkspace,
    state: JobState,
    transcript: dict,
    clip: ClipState,
    reporter: ErrorReporter,
    notify: Notify,
    send_clip: SendClip,
) -> bool:
    """Run the full edit chain for a single clip. Returns True on success."""
    i = clip.index
    cdir = ws.clip_dir(i)
    video = Path(state.source_file)

    async def chain() -> None:
        await notify(f"🎞 Clip {i}: cutting {clip.start_s:.0f}s → {clip.end_s:.0f}s…")
        cut = await clip_extract.extract_clip(video, clip.start_s, clip.end_s, cdir / "01_cut.mp4")
        reframed = await reframe_vertical(cut, cdir / "02_vertical.mp4")
        captioned = await captions.burn_captions(
            reframed, transcript, clip.start_s, clip.end_s,
            cdir / "03_captions.mp4", style=clip.caption_style,
        )

        track = music_sfx.pick_track(clip.hook)
        clip.music_track = track.name if track else ""
        mixed = await music_sfx.mix_music(
            captioned, cdir / "04_music.mp4", track, clip.music_volume
        )

        fx_out, applied = await visual_effects.apply_effects(
            mixed, cdir / "05_effects.mp4", clip.effects
        )
        clip.effects = applied

        meta = await title_generator.generate_title(
            _clip_transcript_text(transcript, clip.start_s, clip.end_s),
            clip.hook,
            state.trend_summary,
            existing_titles=[c.title for c in state.clips if c.title],
        )
        clip.title, clip.caption, clip.hashtags = meta["title"], meta["caption"], meta["hashtags"]

        final = await final_merge.final_export(fx_out, ws.output_dir / f"clip_{i:02d}.mp4")
        clip.output_file = str(final)

        await send_clip(final, format_delivery_caption(clip))
        reporter.record_completed_clip(f"Clip {i}: {clip.title}")

        await sheets_logger.log_clip(
            user_id=state.user_id, job_id=state.job_id, source_url=state.source_url,
            clip_index=i, clip_title=clip.title,
            start_s=clip.start_s, end_s=clip.end_s,
            music_track=clip.music_track, output_file=clip.output_file, status="done",
        )

    result = await stage(f"clip-{i}", chain, reporter, fatal=False)
    if result is None and not clip.output_file:
        await sheets_logger.log_clip(
            user_id=state.user_id, job_id=state.job_id, source_url=state.source_url,
            clip_index=i, clip_title=clip.title or clip.hook,
            start_s=clip.start_s, end_s=clip.end_s,
            music_track=clip.music_track, output_file="", status="failed",
        )
        return False
    return True
