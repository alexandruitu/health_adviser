"""
Central path config. Set DATA_ROOT env var to override (e.g. /data on Render).
Defaults to the repo root so local dev works with no config changes.
"""
import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).parent
_REPO_ROOT   = _BACKEND_DIR.parent

# DB defaults to backend/ (original location); override with DB_ROOT in production
_DB_ROOT = Path(os.environ.get("DB_ROOT", str(_BACKEND_DIR)))
DB_PATH  = _DB_ROOT / "health.db"

# Everything else defaults to repo root; override with DATA_ROOT in production
DATA_ROOT = Path(os.environ.get("DATA_ROOT", str(_REPO_ROOT)))
DATA_DIR  = DATA_ROOT / "health_csvs" / "cleaned"
STRAVA_CONFIG_PATH    = DATA_ROOT / "strava_config.json"
GDRIVE_CONFIG_PATH    = DATA_ROOT / "gdrive_config.json"
GARMIN_CONFIG_PATH    = DATA_ROOT / "garmin_config.json"
GARMIN_TOKEN_DIR      = DATA_ROOT / "garth_tokens"
HEALTH_INGEST_CONFIG  = DATA_ROOT / "health_ingest_config.json"
BIOMARKERS_CONFIG_PATH = DATA_ROOT / "biomarkers_config.json"
