"""Whisper transcription server for Kaggle — loads the model from the
persisted dataset (NO downloading at startup).

Run this in a Kaggle notebook EVERY time you want the transcription API up:
  1. New Notebook → Settings: GPU T4 ON, Internet ON
  2. Add Input → your dataset  <username>/whisper-models  (created once by
     setup_whisper_dataset.py)
  3. Paste this file into a cell, run it.
  4. It prints a public URL (cloudflare tunnel). Put that URL into your
     bot's .env as:
         WHISPER_MODE=remote
         WHISPER_REMOTE_URL=https://<printed-url>

Model load order:
  /kaggle/input/whisper-models/<size>   ← persisted dataset (instant, offline)
  fallback: download (only if you skipped the one-time setup)
"""

import os
import subprocess
import threading
import time
from pathlib import Path

subprocess.run(
    ["pip", "install", "-q", "faster-whisper", "fastapi", "uvicorn", "python-multipart"],
    check=True,
)

MODEL_SIZE = os.environ.get("WHISPER_MODEL", "large-v3")

# ---- find the persisted model (no download) ----
candidates = [
    Path(f"/kaggle/input/whisper-models/{MODEL_SIZE}"),
    *Path("/kaggle/input").glob(f"*/{MODEL_SIZE}"),
]
model_path = next((p for p in candidates if p.exists()), None)

from faster_whisper import WhisperModel  # noqa: E402

if model_path:
    print(f"✅ Loading persisted model from {model_path} — no download needed")
    model = WhisperModel(str(model_path), device="cuda", compute_type="float16")
else:
    print("⚠️ Persisted dataset not attached — downloading once (attach the dataset next time!)")
    model = WhisperModel(MODEL_SIZE, device="cuda", compute_type="float16")

# ---- FastAPI app ----
from fastapi import FastAPI, File, UploadFile  # noqa: E402

app = FastAPI(title="whisper-server")


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_SIZE, "persisted": bool(model_path)}


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    tmp = Path("/tmp") / (file.filename or "audio.wav")
    tmp.write_bytes(await file.read())
    segments, info = model.transcribe(str(tmp), word_timestamps=True)
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
    tmp.unlink(missing_ok=True)
    return out


# ---- run server + public tunnel ----
def _serve():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


threading.Thread(target=_serve, daemon=True).start()
time.sleep(3)

# Cloudflare quick tunnel — free, no account needed
subprocess.run(
    ["wget", "-q",
     "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
     "-O", "/tmp/cloudflared"],
    check=True,
)
os.chmod("/tmp/cloudflared", 0o755)
print("Starting public tunnel — copy the https://…trycloudflare.com URL below into your .env:")
subprocess.run(["/tmp/cloudflared", "tunnel", "--url", "http://localhost:8000"])
