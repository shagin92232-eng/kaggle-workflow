# Cloud model hosting — download ONCE, reuse forever

Heavy models (Whisper transcription, optional LTX-2 video generation) run on
free cloud GPUs. The rule everywhere: **models are downloaded exactly once,
persisted, and every later start loads them from the persisted copy — never
re-downloaded.**

## Kaggle (recommended, free GPU ~30h/week)

### One-time setup (do this ONCE)
1. Go to kaggle.com → **Create → New Notebook**
2. Notebook settings: **Internet ON** (GPU not needed for this step)
3. **First cell** — your Kaggle API credentials (kaggle.com → Settings →
   API → *Create New Token*):
   ```python
   import os
   os.environ["KAGGLE_USERNAME"] = "your_username"
   os.environ["KAGGLE_KEY"] = "your_api_key"
   ```
4. **Second cell** — paste `kaggle/setup_whisper_dataset.py` → Run
5. It downloads faster-whisper (`large-v3` by default) and publishes it as a
   **private Kaggle Dataset**: `<your-username>/whisper-models`

That dataset is permanent storage. This step never has to be repeated
(unless you want a different model size).

### Every time you start the server (fast, no downloads)
1. New Notebook → settings: **GPU T4 ON, Internet ON**
2. **Add Input** → *Your Datasets* → `whisper-models`
3. Paste `kaggle/whisper_server.py` into a cell → Run
4. The model loads instantly from `/kaggle/input/whisper-models/` —
   **no re-download** — and a public `https://…trycloudflare.com` URL is printed
5. Put that URL into the bot's `.env`:
   ```
   WHISPER_MODE=remote
   WHISPER_REMOTE_URL=https://xxxx.trycloudflare.com
   ```

If the remote endpoint is down, the bot automatically falls back to local
CPU transcription — the pipeline never blocks.

### Notes
- Kaggle sessions stop after ~12h / idle timeout. Just re-run
  `whisper_server.py` — startup is quick because nothing downloads.
- The tunnel URL changes per session; update `.env` accordingly.
- Local mode also caches: with `WHISPER_MODE=local`, faster-whisper downloads
  the model into the local Hugging Face cache on first run only.

## Run the WHOLE bot on Kaggle (full cloud hosting)

You don't need to run anything on your PC — the entire bot can live in a
Kaggle GPU notebook using `kaggle/run_bot_kaggle.py`:

1. Push this project to a GitHub repo (see main README)
2. New Notebook → **GPU T4 ON, Internet ON**
3. **Add Input** → *Your Datasets* → `whisper-models`
4. First cell — secrets:
   ```python
   import os
   os.environ["GITHUB_REPO"] = "https://github.com/<you>/video-to-shorts-automation.git"
   os.environ["TELEGRAM_BOT_TOKEN"] = "..."
   os.environ["OPENROUTER_API_KEY"] = "..."
   os.environ["YOUTUBE_DATA_API_KEY"] = "..."
   ```
5. Second cell — paste `kaggle/run_bot_kaggle.py` → Run
6. The bot starts polling. Open Telegram, send your bot `/start`, then a
   YouTube link. Clips come back in the same chat. Leave the cell running.

Kaggle sessions stop after ~12h; just re-run the notebook — the model loads
from the dataset instantly, nothing re-downloads.

## LTX-2 (optional B-roll)

Same pattern: host the LTX-2/ComfyUI checkpoint on Kaggle/Lightning AI/HF
Space, persist the checkpoint as a dataset/volume the same way, expose a
FastAPI endpoint with `POST /generate {prompt, duration}` returning MP4
bytes, and set `LTX2_REMOTE_URL` in `.env`. When unset, the pipeline simply
skips B-roll generation.
