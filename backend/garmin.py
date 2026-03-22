"""
Garmin Connect integration using the garth library.
Uses email/password auth (Garmin does not expose a public OAuth API).
Tokens are persisted in garth_tokens/ directory next to this file.
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import garth
from analytics import clear_all_caches
from db import _db

GARMIN_CONFIG_PATH = Path(__file__).parent.parent / "garmin_config.json"
GARMIN_TOKEN_DIR   = Path(__file__).parent.parent / "garth_tokens"

# In-memory sync job state
_garmin_sync_job: dict = {"status": "idle", "added": 0, "skipped": 0, "error": None}

# Garmin typeKey → our workout_type label
GARMIN_TYPE_MAP = {
    "cycling":              "Cycling",
    "road_biking":          "Cycling",
    "mountain_biking":      "Cycling",
    "gravel_cycling":       "Cycling",
    "indoor_cycling":       "Cycling",
    "virtual_ride":         "Cycling",
    "running":              "Running",
    "trail_running":        "Running",
    "treadmill_running":    "Running",
    "track_running":        "Running",
    "walking":              "Walking",
    "hiking":               "Hiking",
    "swimming":             "Swimming",
    "open_water_swimming":  "Swimming",
    "lap_swimming":         "Swimming",
    "strength_training":    "TraditionalStrengthTraining",
    "cardio_training":      "FunctionalStrengthTraining",
    "yoga":                 "Yoga",
    "elliptical":           "Elliptical",
    "rowing":               "Rowing",
    "skiing":               "DownhillSkiing",
    "backcountry_skiing":   "CrossCountrySkiing",
    "snowboarding":         "Snowboarding",
    "tennis":               "Tennis",
    "padel":                "Padel",
    "soccer":               "Soccer",
    "basketball":           "Basketball",
    "other":                "Other",
}


# ─── config ──────────────────────────────────────────────────────────────────

def _load_garmin_config() -> dict:
    if not GARMIN_CONFIG_PATH.exists():
        return {}
    with open(GARMIN_CONFIG_PATH) as f:
        return json.load(f)


def _save_garmin_config(cfg: dict) -> None:
    with open(GARMIN_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ─── auth ─────────────────────────────────────────────────────────────────────

def _resume_session() -> bool:
    """Try to resume a saved garth session. Returns True if successful."""
    if GARMIN_TOKEN_DIR.exists():
        try:
            garth.resume(str(GARMIN_TOKEN_DIR))
            # Quick test to verify token is still valid
            garth.connectapi("/userprofile-service/userprofile/user-settings")
            return True
        except Exception:
            pass
    return False


def _login(email: str, password: str) -> None:
    """Authenticate with Garmin Connect and save tokens to disk."""
    garth.login(email, password)
    GARMIN_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    garth.save(str(GARMIN_TOKEN_DIR))


def is_connected() -> bool:
    cfg = _load_garmin_config()
    if not cfg.get("email"):
        return False
    return _resume_session()


# ─── data ingestion ───────────────────────────────────────────────────────────

def _append_garmin_activities(activities: list) -> tuple:
    """Insert Garmin activities into SQLite (workouts + metrics tables)."""
    conn = _db()
    _90min_s = 90 * 60

    existing_ts = [
        r[0] for r in conn.execute(
            "SELECT start_ts FROM workouts WHERE source='Garmin'"
        ).fetchall()
    ]

    def _near_existing(ts: float) -> bool:
        return any(abs(e - ts) < _90min_s for e in existing_ts)

    wo_rows  = []
    met_rows = []
    added = skipped = 0

    for act in activities:
        # Parse start time
        start_str = act.get("startTimeLocal") or act.get("startTimeGMT", "")
        try:
            dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            skipped += 1
            continue

        start_ts = dt.timestamp()
        if _near_existing(start_ts):
            skipped += 1
            continue

        # Activity type
        type_info    = act.get("activityType") or {}
        type_key     = type_info.get("typeKey", "other") if isinstance(type_info, dict) else "other"
        workout_type = GARMIN_TYPE_MAP.get(type_key, type_key)

        # Duration / distance
        duration_sec = act.get("duration") or 0
        moving_sec   = act.get("movingDuration") or duration_sec
        end_ts       = start_ts + duration_sec
        duration_min = round(duration_sec / 60, 4)
        distance_m   = act.get("distance") or 0
        distance_km  = round(distance_m / 1000, 4) if distance_m else None

        # Speed
        avg_speed_ms = act.get("averageSpeed")
        avg_speed_kmh = round(avg_speed_ms * 3.6, 3) if avg_speed_ms else None

        # Cadence — Garmin uses different keys depending on sport
        cadence = act.get("averageCadence") or act.get("avgBikeCadence")

        wo_rows.append((
            workout_type, start_ts, end_ts, duration_min, distance_km,
            act.get("calories"),
            "Garmin", None,
            round(moving_sec / 60, 4),
            act.get("elevationGain"),
            act.get("averageHR"),
            act.get("maxHR"),
            None,   # suffer_score — Garmin uses trainingEffect instead
            cadence,
            act.get("averagePower"),
            avg_speed_kmh,
            act.get("activityName", ""),
            type_key,
            0,      # trainer flag — default off
        ))
        existing_ts.append(start_ts)
        added += 1

        # Mirror distance into metrics table (same pattern as Strava)
        if type_key in ("running", "trail_running", "treadmill_running", "track_running") and distance_km:
            met_rows.append(("DistanceWalkingRunning", start_ts, end_ts, distance_km, "km", "Garmin", None))
        elif "cycling" in type_key or type_key in ("virtual_ride", "gravel_cycling", "mountain_biking") and distance_km:
            met_rows.append(("DistanceCycling", start_ts, end_ts, distance_km, "km", "Garmin", None))

    if wo_rows:
        conn.executemany("""
            INSERT OR IGNORE INTO workouts
            (workout_type,start_ts,end_ts,duration_min,distance_km,active_energy_kcal,
             source,device,moving_time_min,elevation_m,avg_hr,max_hr,suffer_score,
             avg_cadence,avg_watts,avg_speed_kmh,activity_name,workout_subtype,trainer)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, wo_rows)
    if met_rows:
        conn.executemany(
            "INSERT OR IGNORE INTO metrics(metric_name,start_ts,end_ts,value,unit,source,device) VALUES(?,?,?,?,?,?,?)",
            met_rows,
        )
    conn.commit()
    return added, skipped


def _fetch_activities(after_ts: float) -> list:
    """Fetch all activities from Garmin Connect since after_ts."""
    activities = []
    start = 0
    limit = 100

    while True:
        params: dict = {"start": start, "limit": limit}
        if after_ts:
            # Garmin API accepts startDate as "YYYY-MM-DD"
            after_dt = datetime.fromtimestamp(after_ts)
            params["startDate"] = after_dt.strftime("%Y-%m-%d")

        try:
            batch = garth.connectapi(
                "/activitylist-service/activities/search/activities",
                params=params,
            )
        except Exception:
            break

        if not batch:
            break

        activities.extend(batch)

        # If we got fewer than limit, we've hit the end
        if len(batch) < limit:
            break
        start += limit

    return activities


# ─── sync job ─────────────────────────────────────────────────────────────────

def _run_garmin_sync(force: bool = False) -> None:
    global _garmin_sync_job
    _garmin_sync_job = {"status": "running", "added": 0, "skipped": 0, "error": None}
    try:
        if not _resume_session():
            raise ValueError("Not connected to Garmin. Please log in first.")

        cfg = _load_garmin_config()

        if force:
            conn = _db()
            conn.execute("DELETE FROM workouts WHERE source='Garmin'")
            conn.execute("DELETE FROM metrics WHERE source='Garmin'")
            conn.commit()
            after_ts = 0.0
        else:
            after_ts = float(cfg.get("last_sync_timestamp") or 0)

        activities = _fetch_activities(after_ts)
        added, skipped = _append_garmin_activities(activities)

        cfg["last_sync_timestamp"] = int(time.time())
        _save_garmin_config(cfg)

        clear_all_caches()

        _garmin_sync_job = {"status": "done", "added": added, "skipped": skipped, "error": None}

    except Exception as e:
        _garmin_sync_job = {"status": "error", "added": 0, "skipped": 0, "error": str(e)}
