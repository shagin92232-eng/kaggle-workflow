"""Run the FULL bot in a Kaggle notebook — whole project in the cloud.

Prerequisites (one time):
  - You already created the dataset <username>/whisper-models
    (via setup_whisper_dataset.py)
  - Your project is on GitHub (public repo, or private + token)

Every run:
  1. New Notebook → Settings: GPU T4 ON, Internet ON, Persistence: none needed
  2. Add Input → Your Datasets → whisper-models
  3. FIRST CELL — your secrets:

       import os
       os.environ["GITHUB_REPO"] = "https://github.com/shagin92232-eng/kaggle-workflow.git"
       os.environ["TELEGRAM_BOT_TOKEN"] = "..."
       os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-..."
       os.environ["YOUTUBE_DATA_API_KEY"] = "..."
       # Gemini fallback (recommended) — https://aistudio.google.com/apikey
       os.environ["GEMINI_API_KEY"] = "AQ...."
       # YouTube cookies — REQUIRED on Kaggle, or downloads fail with
       # "Sign in to confirm you're not a bot". Paste the full content of
       # your Netscape-format cookies.txt between the triple quotes:
       os.environ["YTDLP_COOKIES_CONTENT"] = '''
       # Netscape HTTP Cookie File
       ...paste all lines from cookies.txt here...
       '''
       # optional:
       os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"] = ""

  4. SECOND CELL — paste this whole file, run it. The bot starts polling;
     go to Telegram and send your bot a video link. Leave the cell running.

The Whisper model loads from the attached dataset — nothing re-downloads.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = os.environ.get("GITHUB_REPO", "").strip()
if not REPO:
    raise SystemExit(
        '❌ Set os.environ["GITHUB_REPO"] in a cell above first '
        "(your GitHub repo URL for this project)."
    )

# Private repo support: inject token into the clone URL
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
if GH_TOKEN and REPO.startswith("https://github.com/"):
    REPO = REPO.replace("https://github.com/", f"https://{GH_TOKEN}@github.com/")

for var in ("TELEGRAM_BOT_TOKEN", "OPENROUTER_API_KEY"):
    if not os.environ.get(var, "").strip():
        raise SystemExit(f'❌ Set os.environ["{var}"] in a cell above first.')

APP = Path("/kaggle/working/app")

# ---- 1. get the code ----
if APP.exists():
    subprocess.run(["git", "-C", str(APP), "pull"], check=False)
else:
    subprocess.run(["git", "clone", "--depth", "1", REPO, str(APP)], check=True)

# ---- 2. system + python deps ----
subprocess.run(["apt-get", "install", "-y", "-qq", "ffmpeg"], check=False)
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q", "-r", str(APP / "requirements.txt")],
    check=True,
)

# ---- 3. find the persisted whisper model (no download) ----
# Priority: attached dataset → notebook-persistent /kaggle/working copy →
# one-time download into /kaggle/working (persists if Persistence=Files only)
PERSIST_DIR = Path("/kaggle/working/whisper-models/large-v3")
# A stopped cell can persist a half-written model.bin; the marker is only
# created after a fully finished download, so wipe anything without it
MARKER = PERSIST_DIR / ".download-complete"
if PERSIST_DIR.exists() and not MARKER.exists():
    print("🧹 Removing incomplete Whisper model left by an interrupted download…")
    shutil.rmtree(PERSIST_DIR, ignore_errors=True)
model_path = ""
for cand in [Path("/kaggle/input/whisper-models/large-v3"),
             *Path("/kaggle/input").glob("*/large-v3"),
             *Path("/kaggle/input").glob("*/medium"),
             *Path("/kaggle/input").glob("*/small"),
             PERSIST_DIR]:
    if cand.exists() and any(cand.iterdir()):
        model_path = str(cand)
        break
if model_path:
    print(f"✅ Using persisted Whisper model: {model_path} (no download)")
else:
    print("⚠️ No persisted model found — downloading large-v3 ONCE into /kaggle/working…")
    print("   (Enable notebook Settings → Persistence → 'Files only' so this survives restarts)")
    from faster_whisper import download_model  # installed via requirements

    PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    download_model("large-v3", output_dir=str(PERSIST_DIR))
    MARKER.touch()
    model_path = str(PERSIST_DIR)
    print(f"✅ Model saved to {model_path}")

# ---- 4. YouTube cookies (required, or yt-dlp gets bot-blocked on Kaggle) ----
# Source priority: pasted YTDLP_COOKIES_CONTENT → a *cookies*.txt file in any
# attached input dataset. Written into the app so .env can point at it.
cookies_path = ""
cookies_content = os.environ.get("YTDLP_COOKIES_CONTENT", "").strip()
if cookies_content:
    cred_dir = APP / "credentials"
    cred_dir.mkdir(exist_ok=True)
    dest = cred_dir / "youtube_cookies.txt"
    # De-indent pasted lines; cookie fields are TAB-separated so this is safe
    dest.write_text("\n".join(l.strip() for l in cookies_content.splitlines()) + "\n")
    cookies_path = str(dest)
    print("✅ YouTube cookies written from YTDLP_COOKIES_CONTENT")
else:
    for cand in Path("/kaggle/input").glob("*/*cookies*.txt"):
        cookies_path = str(cand)
        print(f"✅ Using YouTube cookies from dataset: {cand}")
        break
if not cookies_path:
    print("⚠️ No YouTube cookies configured — downloads WILL fail with "
          "'Sign in to confirm you're not a bot'. Set YTDLP_COOKIES_CONTENT "
          "in the secrets cell or attach a dataset containing cookies.txt.")

# ---- 5. write .env ----
env_lines = [
    f"TELEGRAM_BOT_TOKEN={os.environ['TELEGRAM_BOT_TOKEN']}",
    f"OPENROUTER_API_KEY={os.environ['OPENROUTER_API_KEY']}",
    f"YOUTUBE_DATA_API_KEY={os.environ.get('YOUTUBE_DATA_API_KEY', '')}",
    f"GOOGLE_SHEETS_SPREADSHEET_ID={os.environ.get('GOOGLE_SHEETS_SPREADSHEET_ID', '')}",
    "GOOGLE_SHEETS_CREDENTIALS_JSON=credentials/google_sheets_credentials.json",
    "OPENROUTER_MODEL=" + os.environ.get(
        "OPENROUTER_MODEL",
        "qwen/qwen3-next-80b-a3b-instruct:free,"
        "meta-llama/llama-3.3-70b-instruct:free,"
        "nvidia/nemotron-3-super-120b-a12b:free",
    ),
    "WHISPER_MODE=local",
    f"WHISPER_MODEL={model_path}",
    "MAX_CLIPS_PER_VIDEO=8",
    "CLIP_MIN_SECONDS=15",
    "CLIP_MAX_SECONDS=60",
    "WORK_DIR=data/jobs",
    "MUSIC_LIBRARY_DIR=music/library",
    "OVERLAY_LIBRARY_DIR=assets/overlays",
    f"YTDLP_COOKIES_FILE={cookies_path}",
    f"GEMINI_API_KEY={os.environ.get('GEMINI_API_KEY', '')}",
    f"GEMINI_MODEL={os.environ.get('GEMINI_MODEL', 'gemini-3-flash-preview')}",
]
(APP / ".env").write_text("\n".join(env_lines))
print("✅ .env written")

# Optional: Google Sheets service-account JSON via env var (paste full JSON)
sheets_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_CONTENT", "").strip()
if sheets_json:
    cred_dir = APP / "credentials"
    cred_dir.mkdir(exist_ok=True)
    (cred_dir / "google_sheets_credentials.json").write_text(sheets_json)
    print("✅ Google Sheets credentials written")

# ---- 6. run the bot (blocks; stop the cell to stop the bot) ----
print("🚀 Starting Telegram bot — go send it a video link!")
os.chdir(APP)
subprocess.run([sys.executable, "-m", "bot.main"], check=True)
