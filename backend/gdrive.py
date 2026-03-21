"""
Google Drive integration and HAE file parsing helpers.
"""
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd

from db import _db
from analytics import clear_all_caches

GDRIVE_CONFIG_PATH   = Path(__file__).parent.parent / "gdrive_config.json"
GDRIVE_AUTH_URL      = "https://accounts.google.com/o/oauth2/v2/auth"
GDRIVE_TOKEN_URL     = "https://oauth2.googleapis.com/token"
GDRIVE_REDIRECT_URI  = "http://localhost:8000/api/gdrive/callback"
GDRIVE_SCOPES        = "https://www.googleapis.com/auth/drive.readonly"
GDRIVE_FILES_API     = "https://www.googleapis.com/drive/v3/files"

# In-memory sync job state
_gdrive_sync_job: dict = {"status": "idle", "added": 0, "skipped": 0, "error": None, "files_processed": 0}


def _load_gdrive_config() -> dict:
    if GDRIVE_CONFIG_PATH.exists():
        with open(GDRIVE_CONFIG_PATH) as f:
            return json.load(f)
    return {}


def _save_gdrive_config(cfg: dict):
    with open(GDRIVE_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def _ensure_gdrive_token(cfg: dict) -> dict:
    """Refresh Google access token if expired."""
    if time.time() < cfg.get("token_expires_at", 0) - 60:
        return cfg
    if not cfg.get("refresh_token"):
        raise RuntimeError("Google Drive not connected — please re-authorize")
    resp = httpx.post(GDRIVE_TOKEN_URL, data={
        "client_id":     cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "refresh_token": cfg["refresh_token"],
        "grant_type":    "refresh_token",
    })
    resp.raise_for_status()
    tok = resp.json()
    cfg["access_token"]    = tok["access_token"]
    cfg["token_expires_at"] = time.time() + tok.get("expires_in", 3600)
    _save_gdrive_config(cfg)
    return cfg


def _gdrive_folder_id(headers: dict, folder_path: str) -> Optional[str]:
    """Resolve 'AutoExport/HealthMetrics' → Google Drive folder ID."""
    parts = [p for p in folder_path.split("/") if p]
    parent_id = "root"
    for part in parts:
        r = httpx.get(GDRIVE_FILES_API, headers=headers, params={
            "q": f"name='{part}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false",
            "fields": "files(id,name)",
        })
        r.raise_for_status()
        files = r.json().get("files", [])
        if not files:
            return None
        parent_id = files[0]["id"]
    return parent_id


def _parse_hae_stage(stage_str: str) -> str:
    """Map Apple Health sleep stage string to short name."""
    s = (stage_str or "").lower()
    if "asleeprem"    in s or "rem"   in s: return "REM"
    if "asleepdeep"   in s or "deep"  in s: return "Deep"
    if "asleepcore"   in s or "core"  in s: return "Core"
    if "inbed"        in s:                  return "InBed"
    if "awake"        in s:                  return "Awake"
    return "Core"


def _ingest_hae_file(content: bytes) -> tuple:
    """Parse a HAE (Health Auto Export JSON) file and insert into SQLite. Returns (added, skipped)."""
    try:
        payload = json.loads(content)
    except Exception:
        return 0, 0

    data = payload.get("data", payload)
    metrics_list = data.get("metrics", [])
    workouts_list = data.get("workouts", [])

    conn = _db()
    added = skipped = 0

    HAE_METRIC_MAP = {
        "heart_rate_variability_sdnn": "HeartRateVariabilitySDNN",
        "heart_rate_variability":      "HeartRateVariabilitySDNN",
        "heartRateVariabilitySDNN":    "HeartRateVariabilitySDNN",
        "weight_body_mass":            "BodyMass",
        "lean_body_mass":              "LeanBodyMass",
        "dietary_water":               "DietaryWater",
        "headphone_audio_exposure":    "HeadphoneAudioExposure",
        "walking_asymmetry_percentage":      "WalkingAsymmetryPercentage",
        "walking_double_support_percentage": "WalkingDoubleSupportPercentage",
        "walking_step_length":               "WalkingStepLength",
        "walking_running_distance":          "DistanceWalkingRunning",
        "walking_speed":                     "WalkingSpeed",
        "distance_cycling":                  "DistanceCycling",
        "body_mass_index":                   "BodyMassIndex",
        "blood_pressure_systolic":           "BloodPressureSystolic",
        "blood_pressure_diastolic":          "BloodPressureDiastolic",
        "oxygen_saturation":                 "OxygenSaturation",
        "resting_heart_rate":          "RestingHeartRate",
        "restingHeartRate":            "RestingHeartRate",
        "step_count":                  "StepCount",
        "stepCount":                   "StepCount",
        "active_energy":               "ActiveEnergyBurned",
        "activeEnergy":                "ActiveEnergyBurned",
        "basal_energy_burned":         "BasalEnergyBurned",
        "basalEnergyBurned":           "BasalEnergyBurned",
        "heart_rate":                  "HeartRate",
        "heartRate":                   "HeartRate",
        "body_mass":                   "BodyMass",
        "bodyMass":                    "BodyMass",
        "body_fat_percentage":         "BodyFatPercentage",
        "bodyFatPercentage":           "BodyFatPercentage",
        "vo2_max":                     "VO2Max",
        "vo2Max":                      "VO2Max",
        "blood_glucose":               "BloodGlucose",
        "bloodGlucose":                "BloodGlucose",
        "distance_walking_running":    "DistanceWalkingRunning",
        "distanceWalkingRunning":      "DistanceWalkingRunning",
        "flights_climbed":             "FlightsClimbed",
        "flightsClimbed":              "FlightsClimbed",
        "sleep_analysis":              "SleepAnalysis",
        "sleepAnalysis":               "SleepAnalysis",
        "respiratory_rate":            "RespiratoryRate",
        "respiratoryRate":             "RespiratoryRate",
        "oxygenSaturation":            "OxygenSaturation",
        "leanBodyMass":                "LeanBodyMass",
        "apple_exercise_time":         "AppleExerciseTime",
        "appleExerciseTime":           "AppleExerciseTime",
        "mindful_session":             "MindfulSession",
        "mindfulSession":              "MindfulSession",
    }

    def safe_ts(s):
        if not s: return None
        try:
            return pd.Timestamp(str(s)).timestamp()
        except: return None

    def safe_f(v):
        if v is None: return None
        try:
            f = float(v)
            return None if (math.isnan(f) or math.isinf(f)) else f
        except: return None

    metric_rows = []
    sleep_rows  = []
    SLEEP_METRIC_NAMES = {"sleep_analysis", "sleepAnalysis", "SleepAnalysis"}

    for m in metrics_list:
        raw_name  = m.get("name", "")
        db_name   = HAE_METRIC_MAP.get(raw_name, raw_name)
        unit      = m.get("units", "")

        if raw_name in SLEEP_METRIC_NAMES or db_name == "SleepAnalysis":
            for entry in m.get("data", []):
                start_ts = safe_ts(entry.get("sleepStart") or entry.get("startDate") or entry.get("date"))
                if start_ts is None: continue
                src = str(entry.get("source", "HealthAutoExport") or "HealthAutoExport")
                date_ts = safe_ts(entry.get("date"))
                if date_ts:
                    night = datetime.fromtimestamp(date_ts).strftime("%Y-%m-%d")
                else:
                    night = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d")
                stage_fields = [
                    ("rem",   "REM"),
                    ("deep",  "Deep"),
                    ("core",  "Core"),
                    ("awake", "Awake"),
                    ("inBed", "InBed"),
                ]
                for field, stage in stage_fields:
                    hours = safe_f(entry.get(field))
                    if hours is None or hours <= 0: continue
                    dur_min = hours * 60.0
                    end_ts = start_ts + dur_min * 60
                    sleep_rows.append((night, stage, start_ts, end_ts, dur_min, src))
            continue

        for entry in m.get("data", []):
            ts = safe_ts(entry.get("date") or entry.get("startDate"))
            if ts is None: continue
            val = safe_f(entry.get("qty") or entry.get("value") or entry.get("Avg"))
            src = str(entry.get("source", "") or "")
            metric_rows.append((db_name, ts, None, val, unit, src, None))

    if sleep_rows:
        cur = conn.cursor()
        cur.executemany(
            "INSERT OR IGNORE INTO sleep(date,stage,start_ts,end_ts,duration_min,source) VALUES(?,?,?,?,?,?)",
            sleep_rows
        )
        conn.commit()
        added   += cur.rowcount
        skipped += len(sleep_rows) - cur.rowcount

    if metric_rows:
        cur = conn.cursor()
        cur.executemany(
            "INSERT OR IGNORE INTO metrics(metric_name,start_ts,end_ts,value,unit,source,device) VALUES(?,?,?,?,?,?,?)",
            metric_rows
        )
        conn.commit()
        added   += cur.rowcount
        skipped += len(metric_rows) - cur.rowcount

    WORKOUT_TYPE_MAP_HAE = {
        "Run": "Running", "Ride": "Cycling", "VirtualRide": "Cycling",
        "Walk": "Walking", "Swim": "Swimming", "Running": "Running",
        "Cycling": "Cycling", "Walking": "Walking",
    }
    wo_rows = []
    for w in workouts_list:
        name     = w.get("name", "")
        wtype    = WORKOUT_TYPE_MAP_HAE.get(name, name)
        start_ts = safe_ts(w.get("start") or w.get("startDate"))
        end_ts   = safe_ts(w.get("end")   or w.get("endDate"))
        if start_ts is None: continue
        dur = safe_f(w.get("duration"))
        dist_raw = safe_f(w.get("distance"))
        dist_unit = str(w.get("distance_unit", "") or "")
        dist_km = None
        if dist_raw:
            dist_km = dist_raw if "km" in dist_unit.lower() else round(dist_raw * 1.60934, 4)
        kcal = safe_f(w.get("active_energy") or w.get("activeEnergy"))
        wo_rows.append((wtype, start_ts, end_ts, dur, dist_km, kcal, "HealthAutoExport",
                        None, None, None, None, None, None, None, None, None, None, None, None, 0))

    if wo_rows:
        cur = conn.cursor()
        cur.executemany("""
            INSERT OR IGNORE INTO workouts
            (workout_type,start_ts,end_ts,duration_min,distance_km,active_energy_kcal,
             source,device,moving_time_min,elevation_m,avg_hr,max_hr,suffer_score,
             avg_cadence,avg_watts,avg_speed_kmh,activity_name,workout_subtype,trainer)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, wo_rows)
        conn.commit()
        added   += cur.rowcount
        skipped += len(wo_rows) - cur.rowcount

    # Clear all caches so charts refresh
    clear_all_caches()

    return added, skipped


def _run_gdrive_sync():
    global _gdrive_sync_job
    _gdrive_sync_job = {"status": "running", "added": 0, "skipped": 0, "error": None, "files_processed": 0}
    try:
        cfg = _load_gdrive_config()
        cfg = _ensure_gdrive_token(cfg)
        headers = {"Authorization": f"Bearer {cfg['access_token']}"}

        folder_id = cfg.get("folder_id") or _gdrive_folder_id(headers, cfg.get("folder_path", "Health Auto Export/HealthMetrics"))
        if not folder_id:
            _gdrive_sync_job["error"] = f"Folder '{cfg.get('folder_path')}' not found in Google Drive"
            _gdrive_sync_job["status"] = "error"
            return
        if not cfg.get("folder_id"):
            cfg["folder_id"] = folder_id
            _save_gdrive_config(cfg)

        conn = _db()
        processed = {r[0] for r in conn.execute("SELECT file_id FROM gdrive_files").fetchall()}

        page_token = None
        all_files = []
        while True:
            params = {
                "q": f"'{folder_id}' in parents and trashed=false",
                "fields": "nextPageToken,files(id,name,modifiedTime,size)",
                "pageSize": 100,
            }
            if page_token:
                params["pageToken"] = page_token
            r = httpx.get(GDRIVE_FILES_API, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
            all_files.extend(data.get("files", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        new_files = [f for f in all_files if f["id"] not in processed]
        total_added = total_skipped = 0

        for file in new_files:
            try:
                r = httpx.get(f"{GDRIVE_FILES_API}/{file['id']}", headers=headers,
                              params={"alt": "media"}, timeout=60)
                r.raise_for_status()
                added, skipped = _ingest_hae_file(r.content)
                total_added   += added
                total_skipped += skipped
                conn.execute(
                    "INSERT OR REPLACE INTO gdrive_files(file_id,file_name,modified_time,processed_at,records_added) VALUES(?,?,?,?,?)",
                    (file["id"], file["name"], file.get("modifiedTime"), time.time(), added)
                )
                conn.commit()
                _gdrive_sync_job["files_processed"] += 1
                _gdrive_sync_job["added"]   = total_added
                _gdrive_sync_job["skipped"] = total_skipped
            except Exception as e:
                print(f"[gdrive] error processing {file['name']}: {e}")

        conn.execute(
            "INSERT INTO sync_log(source,synced_at,added,skipped,note) VALUES(?,?,?,?,?)",
            ("gdrive", time.time(), total_added, total_skipped, f"{len(new_files)} files")
        )
        conn.commit()

        _gdrive_sync_job["status"] = "done"

    except Exception as e:
        _gdrive_sync_job["status"] = "error"
        _gdrive_sync_job["error"]  = str(e)
