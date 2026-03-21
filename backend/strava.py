"""
Strava integration helpers.
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from analytics import clear_all_caches
from db import _db

STRAVA_CONFIG_PATH  = Path(__file__).parent.parent / "strava_config.json"
STRAVA_AUTH_URL     = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL    = "https://www.strava.com/oauth/token"
STRAVA_REDIRECT_URI = "http://localhost:8000/api/strava/callback"

WORKOUT_TYPE_MAP = {
    "Run":              "Running",
    "Ride":             "Cycling",
    "VirtualRide":      "Cycling",
    "Walk":             "Walking",
    "Hike":             "Hiking",
    "Swim":             "Swimming",
    "WeightTraining":   "TraditionalStrengthTraining",
    "Workout":          "FunctionalStrengthTraining",
}

# In-memory sync job state
_sync_job: dict = {"status": "idle", "added": 0, "skipped": 0, "error": None}


def _load_strava_config() -> dict:
    if not STRAVA_CONFIG_PATH.exists():
        return {}
    with open(STRAVA_CONFIG_PATH) as f:
        return json.load(f)


def _save_strava_config(cfg: dict) -> None:
    with open(STRAVA_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def _ensure_valid_token(cfg: dict) -> dict:
    """Refresh access_token if expired or within 60 s of expiry."""
    if not cfg.get("refresh_token"):
        raise ValueError("Not connected to Strava")
    if time.time() < cfg.get("token_expires_at", 0) - 60:
        return cfg
    resp = httpx.post(STRAVA_TOKEN_URL, data={
        "client_id":     cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "grant_type":    "refresh_token",
        "refresh_token": cfg["refresh_token"],
    })
    resp.raise_for_status()
    data = resp.json()
    cfg["access_token"]     = data["access_token"]
    cfg["refresh_token"]    = data["refresh_token"]
    cfg["token_expires_at"] = data["expires_at"]
    _save_strava_config(cfg)
    return cfg


def _append_activities(activities: list) -> tuple:
    """Append new Strava activities into SQLite (workouts + metrics tables)."""
    conn = _db()
    _90min_s = 90 * 60  # seconds

    # Load existing workout start_ts for dedup
    existing_ts = [r[0] for r in conn.execute("SELECT start_ts FROM workouts WHERE source='Strava'").fetchall()]

    def _near_existing(ts: float) -> bool:
        return any(abs(e - ts) < _90min_s for e in existing_ts)

    wo_rows  = []
    met_rows = []
    added = skipped = 0

    for act in activities:
        local_str = act.get("start_date_local", act["start_date"])
        dt_local  = datetime.fromisoformat(local_str.replace("Z", "+00:00")).replace(tzinfo=None)
        start_ts  = dt_local.timestamp()

        if _near_existing(start_ts):
            skipped += 1
            continue

        elapsed_sec  = act.get("elapsed_time", 0)
        end_ts       = start_ts + elapsed_sec
        duration_min = round(elapsed_sec / 60, 4)
        distance_m   = act.get("distance", 0)
        distance_km  = round(distance_m / 1000, 4) if distance_m else None
        sport_type   = act.get("sport_type") or act.get("type", "")
        workout_type = WORKOUT_TYPE_MAP.get(sport_type, sport_type)
        moving_sec   = act.get("moving_time", elapsed_sec)
        avg_speed_ms = act.get("average_speed")

        wo_rows.append((
            workout_type, start_ts, end_ts, duration_min, distance_km, None,
            "Strava", None,
            round(moving_sec / 60, 4),
            act.get("total_elevation_gain"),
            act.get("average_heartrate"),
            act.get("max_heartrate"),
            act.get("suffer_score"),
            act.get("average_cadence"),
            act.get("average_watts"),
            round(avg_speed_ms * 3.6, 3) if avg_speed_ms else None,
            act.get("name", ""),
            act.get("workout_type", 0),
            int(bool(act.get("trainer", False))),
        ))
        existing_ts.append(start_ts)
        added += 1

        # Distance record into metrics table
        if sport_type == "Run" and distance_km:
            met_rows.append(("DistanceWalkingRunning", start_ts, end_ts, distance_km, "km", "Strava", None))
        elif sport_type in ("Ride", "VirtualRide") and distance_km:
            met_rows.append(("DistanceCycling", start_ts, end_ts, distance_km, "km", "Strava", None))

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


def _run_sync_job(force: bool = False):
    global _sync_job
    _sync_job = {"status": "running", "added": 0, "skipped": 0, "error": None}
    try:
        cfg = _load_strava_config()
        cfg = _ensure_valid_token(cfg)

        if force:
            conn = _db()
            conn.execute("DELETE FROM workouts WHERE source='Strava'")
            conn.execute("DELETE FROM metrics WHERE source='Strava'")
            conn.commit()
            cfg["last_sync_timestamp"] = 0
            after_ts = 0
        else:
            after_ts = int(cfg.get("last_sync_timestamp") or 0)

        headers = {"Authorization": f"Bearer {cfg['access_token']}"}

        activities = []
        page = 1
        while True:
            resp = httpx.get(
                "https://www.strava.com/api/v3/athlete/activities",
                headers=headers,
                params={"after": after_ts, "per_page": 100, "page": page},
                timeout=30,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            activities.extend(batch)
            page += 1

        added, skipped = _append_activities(activities)

        cfg["last_sync_timestamp"] = int(time.time())
        _save_strava_config(cfg)

        clear_all_caches()

        _sync_job = {"status": "done", "added": added, "skipped": skipped, "error": None}
    except Exception as e:
        _sync_job = {"status": "error", "added": 0, "skipped": 0, "error": str(e)}
