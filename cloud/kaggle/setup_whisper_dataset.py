"""ONE-TIME Kaggle setup — run this in a Kaggle notebook ONCE.

Downloads the faster-whisper model and saves it as a private Kaggle
Dataset. After this, the runtime server (whisper_server.py) loads the
model from /kaggle/input/... on every start — NOTHING is ever
re-downloaded again.

How to run (once):
  1. kaggle.com → Create → New Notebook
  2. Settings: Internet ON  (GPU not needed for the download)
  3. FIRST CELL — set your Kaggle credentials (kaggle.com → Settings →
     API → Create New Token shows these values):

        import os
        os.environ["KAGGLE_USERNAME"] = "your_username"
        os.environ["KAGGLE_KEY"] = "your_api_key"

  4. SECOND CELL — paste this whole file and run it
  5. When it finishes it creates the dataset  <username>/whisper-models
  6. Done forever — future notebooks just attach that dataset as input.

Safe to re-run: if the model is already in /kaggle/working it is NOT
downloaded again, and if the dataset already exists a new version is
pushed instead.
"""

import json
import os
import subprocess
from pathlib import Path

# ------------- configuration -------------
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "large-v3")  # or "medium", "small"
DATASET_SLUG = "whisper-models"          # becomes <username>/whisper-models
WORK = Path("/kaggle/working/whisper-models")
# ------------------------------------------

subprocess.run(["pip", "install", "-q", "faster-whisper", "kaggle"], check=True)

# ---- 0. resolve Kaggle credentials (env → Kaggle Secrets) ----
username = os.environ.get("KAGGLE_USERNAME", "").strip()
key = os.environ.get("KAGGLE_KEY", "").strip()

if not (username and key):
    # Kaggle "Add-ons → Secrets" fallback: add secrets named
    # KAGGLE_USERNAME and KAGGLE_KEY, then enable them for this notebook.
    try:
        from kaggle_secrets import UserSecretsClient

        secrets = UserSecretsClient()
        username = username or secrets.get_secret("KAGGLE_USERNAME")
        key = key or secrets.get_secret("KAGGLE_KEY")
    except Exception:  # noqa: BLE001
        pass

if not (username and key):
    raise SystemExit(
        "\n❌ Kaggle credentials not set!\n"
        "Add a cell ABOVE this one and run it first:\n\n"
        '    import os\n'
        '    os.environ["KAGGLE_USERNAME"] = "your_username"\n'
        '    os.environ["KAGGLE_KEY"] = "your_api_key"\n\n'
        "(Get the key at kaggle.com → Settings → API → Create New Token)"
    )

# Write kaggle.json so the kaggle CLI can authenticate
kaggle_dir = Path(os.path.expanduser("~/.kaggle"))
kaggle_dir.mkdir(parents=True, exist_ok=True)
(kaggle_dir / "kaggle.json").write_text(json.dumps({"username": username, "key": key}))
os.chmod(kaggle_dir / "kaggle.json", 0o600)
print(f"✅ Kaggle credentials configured for user: {username}")

# ---- 1. download the model (skipped if already present) ----
model_dir = WORK / MODEL_SIZE
if model_dir.exists() and any(model_dir.iterdir()):
    print(f"✅ Model already present at {model_dir} — skipping download")
else:
    from faster_whisper import download_model

    print(f"Downloading faster-whisper '{MODEL_SIZE}' (one time only)…")
    model_dir.mkdir(parents=True, exist_ok=True)
    download_model(MODEL_SIZE, output_dir=str(model_dir))
    print(f"Model saved to {model_dir}")

# ---- 2. publish as a private Kaggle Dataset so it persists forever ----
meta = {
    "title": "whisper-models",
    "id": f"{username}/{DATASET_SLUG}",
    "licenses": [{"name": "CC0-1.0"}],
}
(WORK / "dataset-metadata.json").write_text(json.dumps(meta))

print("Creating Kaggle dataset (private)… this uploads ~3 GB, please wait")
result = subprocess.run(
    ["kaggle", "datasets", "create", "-p", str(WORK), "--dir-mode", "zip"],
    capture_output=True, text=True,
)
print(result.stdout, result.stderr)

combined = (result.stdout + result.stderr).lower()
if "already exists" in combined or "409" in combined:
    print("Dataset exists — pushing a new version instead…")
    v = subprocess.run(
        ["kaggle", "datasets", "version", "-p", str(WORK), "-m", "update model",
         "--dir-mode", "zip"],
        capture_output=True, text=True,
    )
    print(v.stdout, v.stderr)

print(
    "\n✅ DONE — one-time setup complete.\n"
    f"   Dataset: https://www.kaggle.com/datasets/{username}/{DATASET_SLUG}\n"
    "   From now on: in any Kaggle notebook click 'Add Input' → Your Datasets\n"
    "   → whisper-models → the model is available at /kaggle/input/whisper-models/\n"
    "   instantly, with NO re-downloading, every time you start the server."
)
