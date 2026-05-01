"""
Central path config. Set DATA_ROOT env var to override (e.g. /data on Render).
Defaults to the repo root so local dev works with no config changes.
"""
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
DATA_ROOT = Path(os.environ.get("DATA_ROOT", str(_REPO_ROOT)))

DB_PATH               = DATA_ROOT / "health.db"
DATA_DIR              = DATA_ROOT / "health_csvs" / "cleaned"
STRAVA_CONFIG_PATH    = DATA_ROOT / "strava_config.json"
GDRIVE_CONFIG_PATH    = DATA_ROOT / "gdrive_config.json"
GARMIN_CONFIG_PATH    = DATA_ROOT / "garmin_config.json"
GARMIN_TOKEN_DIR      = DATA_ROOT / "garth_tokens"
HEALTH_INGEST_CONFIG  = DATA_ROOT / "health_ingest_config.json"
BIOMARKERS_CONFIG_PATH = DATA_ROOT / "biomarkers_config.json"
