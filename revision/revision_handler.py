"""Revision loop — re-edit a specific clip from saved state without a full re-run.

Flow: user text → Qwen3 parses (clip index + change type + params) →
only the affected editing stages re-run using intermediates saved in the
clip's working dir → new version delivered.
"""

from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

from agent import llm_client, system_prompt
from editing import captions, clip_extract, final_merge, music_sfx, title_generator, visual_effects
from editing.vertical_reframe import reframe_vertical
from analysis import transcribe
from revision.state_manager import JobState
from sheets.google_sheets import sheets_logger
from utils.file_manager import JobWorkspace
from utils.logger import get_logger

log = get_logger(__name__)

Notify = Callable[[str], Awaitable[None]]
SendClip = Callable[[Path, str], Awaitable[None]]


async def parse_revision_request(text: str, state: JobState) -> dict:
    clip_list = "\n".join(
        f"clip {c.index}: \"{c.title or c.hook}\" [{c.status}]" for c in state.clips
    )
    user = f"AVAILABLE CLIPS:\n{clip_list}\n\nUSER REQUEST:\n{text}\n\nReturn the JSON now."
    return await llm_client.chat_json(system_prompt.REVISION_SYSTEM, user, temperature=0.2)


async def handle_revision(
    user_id: int,
    text: str,
    notify: Notify,
    send_clip: SendClip,
) -> bool:
    """Returns True if the text was handled as a revision, False if there is
    no previous job (caller should tell the user to send a video first)."""
    ws = JobWorkspace.latest_for_user(user_id)
    if ws is None or not ws.state_path.exists():
        return False

    state = JobState.load(ws.state_path)
    if not state.clips:
        return False

    try:
        parsed = await parse_revision_request(text, state)
    except Exception as exc:  # noqa: BLE001 — LLM outage must not crash the bot
        log.error(f"Revision request parsing failed: {exc}")
        await notify(f"⚠️ I couldn't process that request right now ({exc}). Please try again.")
        return True
    if not isinstance(parsed, dict):
        parsed = {}
    change = str(parsed.get("change_type", "unknown"))
    try:
        idx = int(parsed.get("clip_index") or -1)
    except (TypeError, ValueError):
        idx = -1
    params = parsed.get("params", {}) or {}
    note = str(parsed.get("note", ""))

    if change == "unknown" or idx == -1 or state.clip(idx) is None:
        await notify(
            "🤔 I couldn't map that request to a clip. "
            + (note + " " if note else "")
            + "Try e.g.: “clip 2: change the music” or “clip 1: bigger captions”."
        )
        return True

    clip = state.clip(idx)
    cdir = ws.clip_dir(idx)
    transcript = None
    if state.transcript_file and Path(state.transcript_file).exists():
        transcript = transcribe.load_transcript(state.transcript_file)

    await notify(f"🔁 Revising clip {idx} ({change})…")

    try:
        # ---- apply the change to clip state ----
        rebuild_from = None  # earliest stage that must re-run
        if change == "trim":
            clip.start_s = float(params.get("start", clip.start_s))
            clip.end_s = float(params.get("end", clip.end_s))
            rebuild_from = "cut"
        elif change in ("captions", "no_captions"):
            clip.caption_style = str(params.get("style", clip.caption_style))
            rebuild_from = "captions"
        elif change == "music":
            hint = str(params.get("track_hint", "")) or text
            track = music_sfx.pick_track(hint)
            clip.music_track = track.name if track else ""
            rebuild_from = "music"
        elif change == "music_volume":
            clip.music_volume = float(params.get("volume", clip.music_volume))
            rebuild_from = "music"
        elif change == "effects":
            clip.effects = [
                e for e in params.get("effects", []) if e in visual_effects.SAFE_EFFECTS
            ] or clip.effects
            rebuild_from = "effects"
        elif change == "title":
            rebuild_from = "title"

        # ---- re-run only what's needed ----
        source = Path(state.source_file)
        stages = ["cut", "captions", "music", "effects", "title"]
        start_at = stages.index(rebuild_from)

        cut = cdir / "01_cut.mp4"
        vertical = cdir / "02_vertical.mp4"
        captioned = cdir / "03_captions.mp4"
        mixed = cdir / "04_music.mp4"
        fx = cdir / "05_effects.mp4"

        if start_at <= 0:
            if not source.exists():
                await notify(
                    "⚠️ The original video is no longer stored, so trims need a re-send "
                    "of the video. Other changes (music/captions/effects) still work."
                )
                return True
            await clip_extract.extract_clip(source, clip.start_s, clip.end_s, cut)
            await reframe_vertical(cut, vertical)

        if start_at <= 1:
            if transcript is None or change == "no_captions":
                # no captions: pass the vertical video straight through
                import shutil

                shutil.copyfile(vertical, captioned)
            else:
                await captions.burn_captions(
                    vertical, transcript, clip.start_s, clip.end_s,
                    captioned, style=clip.caption_style,
                )

        if start_at <= 2:
            lib_track = None
            if clip.music_track:
                cand = music_sfx.list_tracks()
                lib_track = next((t for t in cand if t.name == clip.music_track), None)
            await music_sfx.mix_music(captioned, mixed, lib_track, clip.music_volume)

        if start_at <= 3:
            _, applied = await visual_effects.apply_effects(mixed, fx, clip.effects)
            clip.effects = applied

        if start_at <= 4 and change == "title" and transcript is not None:
            from agent.orchestrator import _clip_transcript_text

            meta = await title_generator.generate_title(
                _clip_transcript_text(transcript, clip.start_s, clip.end_s),
                clip.hook,
                state.trend_summary,
                existing_titles=[c.title for c in state.clips if c.title and c.index != idx],
            )
            clip.title, clip.caption, clip.hashtags = (
                meta["title"], meta["caption"], meta["hashtags"],
            )

        final_src = fx if fx.exists() else (mixed if mixed.exists() else captioned)
        final = await final_merge.final_export(final_src, ws.output_dir / f"clip_{idx:02d}.mp4")
        clip.output_file = str(final)
        clip.status = "done"
        state.save(ws.state_path)

        from agent.orchestrator import format_delivery_caption

        await send_clip(final, "🔁 Revised!\n\n" + format_delivery_caption(clip))
        await sheets_logger.log_clip(
            user_id=state.user_id, job_id=state.job_id, source_url=state.source_url,
            clip_index=idx, clip_title=clip.title,
            start_s=clip.start_s, end_s=clip.end_s,
            music_track=clip.music_track, output_file=clip.output_file,
            status=f"revised:{change}",
        )
    except Exception as exc:  # noqa: BLE001
        log.error(f"Revision failed: {exc}")
        await notify(f"⚠️ Revision failed: {exc}\nTry a different request.")
    return True
