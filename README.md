# Long Video → Viral Shorts Automation 🎬

A Telegram-triggered AI pipeline: send a long video (file or link) → Qwen3
finds **every** viral-potential moment → each becomes a polished 9:16 short
with animated captions, copyright-free music, face-safe effects, and its own
AI-generated title/caption/hashtags → delivered back on Telegram. Reply with
a text prompt to revise any clip.

- **Multi-clip**: as many clips as the video deserves (capped by `MAX_CLIPS_PER_VIDEO`)
- **Face-safe**: zoom/pan, transitions, color grade, grain, overlays — faces are **never** altered (no face-swap/deepfake anywhere)
- **Multi-user isolation**: every user gets separate job directories
- **Error-resilient**: any stage failure → Telegram report (stage + cause + suggestion + partial progress); one failed clip never stops the others
- **Google Sheets logging**: one row per clip (optional)
- **Cloud-friendly**: Whisper (and optional LTX-2) run on Kaggle free GPU — models download **once**, persist as a Kaggle Dataset, and never re-download

## Project layout

```
bot/            Telegram bot (entry: python -m bot.main)
agent/          Orchestrator + OpenRouter/Qwen3 client + system prompts
analysis/       Whisper transcribe, PySceneDetect, candidate finder, trends
editing/        FFmpeg trim, MediaPipe 9:16 reframe, captions, music, effects, titles, export
video_gen/      Optional LTX-2 B-roll (remote endpoint)
revision/       Revision loop + saved pipeline state
sheets/         Google Sheets logging
errors/         Stage-level error handling + Telegram reporting
utils/          Downloader (yt-dlp), file manager, FFmpeg helpers, logging
cloud/          Kaggle scripts: one-time model setup + full cloud hosting
config/         Settings loader (.env)
tests/          pytest units
```

## Option A — run everything in the cloud (Kaggle, recommended)

**No installation on your PC needed.** Full guide: [`cloud/README.md`](cloud/README.md)

1. **One time:** run `cloud/kaggle/setup_whisper_dataset.py` in a Kaggle
   notebook → creates the private dataset `<you>/whisper-models`.
   Models are now persisted forever — never downloaded again.
2. Push this project to GitHub (below).
3. **Each session:** run `cloud/kaggle/run_bot_kaggle.py` in a GPU notebook
   with the dataset attached → bot goes live, test from Telegram.

## Option B — run locally

Requirements: Python 3.10+, FFmpeg on PATH.

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in your keys
python -m bot.main
```

`WHISPER_MODE=local` downloads the Whisper model **once** into the local
cache; later runs reuse it. Set `WHISPER_MODE=remote` +
`WHISPER_REMOTE_URL` to use the Kaggle GPU server
(`cloud/kaggle/whisper_server.py`) instead.

### Docker

```bash
docker compose up --build -d
```

## Configuration (.env)

| Key | Required | Notes |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | from @BotFather |
| `OPENROUTER_API_KEY` | ✅ | Qwen3 access |
| `YOUTUBE_DATA_API_KEY` | recommended | trend reference (free quota) |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | optional | share the sheet with the service-account email first |
| `TIKTOK/FACEBOOK/INSTAGRAM_API_KEY` | optional | skipped automatically when empty |
| `WHISPER_MODE` | | `local` or `remote` |
| `LTX2_REMOTE_URL` | optional | B-roll generation endpoint; skipped when empty |

## Music & overlay libraries

Pre-populate before running (bot works without them, clips just get no music/overlays):

- `music/library/` — tracks from YouTube Audio Library, Facebook Sound
  Collection, Pixabay Music, Mixkit. Name files descriptively
  (`upbeat-energetic-pop.mp3`) — selection matches keywords against filenames.
- `assets/overlays/` — light-leak/particle/dust MP4s from Pexels/Videvo.

Check each track's license terms (some need attribution).

## Push to GitHub

```bash
cd video-to-shorts-automation
git init && git add . && git commit -m "Initial commit"
# create an empty repo on github.com first, then:
git remote add origin https://github.com/<you>/video-to-shorts-automation.git
git push -u origin main
```

`.gitignore` already excludes `.env`, `credentials/`, and all media — your
keys never reach GitHub.

## Testing

```bash
pytest tests/ -v          # unit tests (no network/FFmpeg needed)
```

End-to-end (manual):
1. `/start` → welcome message
2. Send a YouTube URL → progress messages → clips delivered with titles
3. Send an invalid URL → error report with suggestion
4. Reply `clip 1: change the music` → only that clip re-renders
5. Remove optional keys from `.env` → those platforms skip silently

## Using it (Telegram)

```
/start
https://youtu.be/XXXX focus on the funny moments, 30-60s clips
→ ... clips arrive ...
clip 2: change the music
clip 1: bigger captions
```

## Face-safety policy

No face-swap, deepfake, or face-altering code exists in this project, and the
LLM system prompts forbid it. Face *detection* is used only to decide where
to crop for 9:16 reframing. Do not add libraries like Roop/DeepFaceLab/SimSwap.
