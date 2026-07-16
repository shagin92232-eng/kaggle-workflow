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
       # optional:
       os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"] = ""

  4. SECOND CELL — paste this whole file, run it. The bot starts polling;
     go to Telegram and send your bot a video link. Leave the cell running.

The Whisper model loads from the attached dataset — nothing re-downloads.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = os.environ.get("GITHUB_REPO", "").strip()
if not REPO:
    raise SystemExit(
        '❌ Set os.environ["GITHUB_REPO"] in a cell above first '
        "(your GitHub repo URL for this project)."
    )

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
model_path = ""
for cand in [Path("/kaggle/input/whisper-models/large-v3"),
             *Path("/kaggle/input").glob("*/large-v3"),
             *Path("/kaggle/input").glob("*/medium"),
             *Path("/kaggle/input").glob("*/small")]:
    if cand.exists():
        model_path = str(cand)
        break
if model_path:
    print(f"✅ Using persisted Whisper model: {model_path} (no download)")
else:
    model_path = "small"
    print("⚠️ whisper-models dataset not attached — will download 'small' once. "
          "Attach the dataset next time for instant start.")

# ---- 4. write .env ----
env_lines = [
    f"TELEGRAM_BOT_TOKEN={os.environ['TELEGRAM_BOT_TOKEN']}",
    f"OPENROUTER_API_KEY={os.environ['OPENROUTER_API_KEY']}",
    f"YOUTUBE_DATA_API_KEY={os.environ.get('YOUTUBE_DATA_API_KEY', '')}",
    f"GOOGLE_SHEETS_SPREADSHEET_ID={os.environ.get('GOOGLE_SHEETS_SPREADSHEET_ID', '')}",
    "GOOGLE_SHEETS_CREDENTIALS_JSON=credentials/google_sheets_credentials.json",
    f"OPENROUTER_MODEL={os.environ.get('OPENROUTER_MODEL', 'qwen/qwen3-235b-a22b:free')}",
    "WHISPER_MODE=local",
    f"WHISPER_MODEL={model_path}",
    "MAX_CLIPS_PER_VIDEO=8",
    "CLIP_MIN_SECONDS=15",
    "CLIP_MAX_SECONDS=60",
    "WORK_DIR=data/jobs",
    "MUSIC_LIBRARY_DIR=music/library",
    "OVERLAY_LIBRARY_DIR=assets/overlays",
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

# ---- 5. run the bot (blocks; stop the cell to stop the bot) ----
print("🚀 Starting Telegram bot — go send it a video link!")
os.chdir(APP)
subprocess.run([sys.executable, "-m", "bot.main"], check=True)
