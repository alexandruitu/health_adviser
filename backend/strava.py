"""
Strava integration helpers.
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
import pandas as pd

from analytics import DATA_DIR, STRAVA_EXTRA_COLS, clear_all_caches

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
    """Append new Strava activities to workouts.csv and distance CSVs."""
    workouts_path = DATA_DIR / "workouts.csv"
    dwr_path      = DATA_DIR / "by_type" / "DistanceWalkingRunning.csv"
    cyc_path      = DATA_DIR / "by_type" / "DistanceCycling.csv"

    wo_existing  = pd.read_csv(workouts_path)
    dwr_existing = pd.read_csv(dwr_path)
    cyc_existing = pd.read_csv(cyc_path)

    wo_existing["_ts"]  = pd.to_datetime(wo_existing["startDate"], errors="coerce").astype("int64")
    dwr_existing["_ts"] = pd.to_datetime(dwr_existing["startDate"], errors="coerce").astype("int64")
    cyc_existing["_ts"] = pd.to_datetime(cyc_existing["startDate"], errors="coerce").astype("int64")
    _90min_ns = 90 * 60 * int(1e9)

    def _near_existing(ts_ns: int, existing_df: pd.DataFrame, wtype: Optional[str] = None) -> bool:
        col = existing_df["_ts"].dropna()
        return bool((abs(col - ts_ns) < _90min_ns).any())

    wo_rows, dwr_rows, cyc_rows = [], [], []
    added = skipped = 0

    for act in activities:
        local_str = act.get("start_date_local", act["start_date"])
        dt_local  = datetime.fromisoformat(local_str.replace("Z", "+00:00")).replace(tzinfo=None)
        start_str = dt_local.strftime("%Y-%m-%d %H:%M:%S")

        elapsed_sec  = act.get("elapsed_time", 0)
        duration_min = round(elapsed_sec / 60, 4)
        distance_m   = act.get("distance", 0)
        distance_km  = round(distance_m / 1000, 4) if distance_m else None

        end_dt  = dt_local + timedelta(seconds=elapsed_sec)
        end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

        sport_type   = act.get("sport_type") or act.get("type", "")
        workout_type = WORKOUT_TYPE_MAP.get(sport_type, sport_type)

        ts_ns = int(dt_local.timestamp() * 1e9)
        if _near_existing(ts_ns, wo_existing):
            skipped += 1
            continue

        moving_sec    = act.get("moving_time", elapsed_sec)
        moving_min    = round(moving_sec / 60, 4)
        elevation_m   = act.get("total_elevation_gain")
        avg_hr        = act.get("average_heartrate")
        max_hr        = act.get("max_heartrate")
        suffer_score  = act.get("suffer_score")
        avg_cadence   = act.get("average_cadence")
        avg_watts     = act.get("average_watts")
        avg_speed_ms  = act.get("average_speed")
        avg_speed_kmh = round(avg_speed_ms * 3.6, 3) if avg_speed_ms else None
        activity_name = act.get("name", "")
        workout_sub   = act.get("workout_type", 0)
        trainer       = int(bool(act.get("trainer", False)))

        wo_rows.append({
            "workoutType":       workout_type,
            "duration_min":      duration_min,
            "distance":          distance_km,
            "distanceUnit":      "km" if distance_km else None,
            "activeEnergy_kcal": None,
            "sourceName":        "Strava",
            "startDate":         start_str,
            "endDate":           end_str,
            "device":            None,
            "moving_time_min":   moving_min,
            "elevation_m":       elevation_m,
            "avg_hr":            avg_hr,
            "max_hr":            max_hr,
            "suffer_score":      suffer_score,
            "avg_cadence":       avg_cadence,
            "avg_watts":         avg_watts,
            "avg_speed_kmh":     avg_speed_kmh,
            "activity_name":     activity_name,
            "workout_subtype":   workout_sub,
            "trainer":           trainer,
        })
        added += 1
        new_wo_row = pd.DataFrame([{"startDate": start_str, "_ts": ts_ns}])
        wo_existing = pd.concat([wo_existing, new_wo_row], ignore_index=True)

        if sport_type == "Run" and distance_km:
            if not _near_existing(ts_ns, dwr_existing):
                dwr_rows.append({
                    "startDate":  start_str,
                    "endDate":    end_str,
                    "value_num":  distance_km,
                    "unit":       "km",
                    "sourceName": "Strava",
                    "device":     None,
                })
                new_dwr_row = pd.DataFrame([{"startDate": start_str, "_ts": ts_ns}])
                dwr_existing = pd.concat([dwr_existing, new_dwr_row], ignore_index=True)

        if sport_type in ("Ride", "VirtualRide") and distance_km:
            if not _near_existing(ts_ns, cyc_existing):
                cyc_rows.append({
                    "startDate":  start_str,
                    "endDate":    end_str,
                    "value_num":  distance_km,
                    "unit":       "km",
                    "sourceName": "Strava",
                    "device":     None,
                })
                new_cyc_row = pd.DataFrame([{"startDate": start_str, "_ts": ts_ns}])
                cyc_existing = pd.concat([cyc_existing, new_cyc_row], ignore_index=True)

    if wo_rows:
        wo_new = pd.DataFrame(wo_rows)
        existing_cols = pd.read_csv(workouts_path, nrows=0).columns.tolist()
        for col in existing_cols:
            if col not in wo_new.columns:
                wo_new[col] = np.nan
        needs_header_update = any(c not in existing_cols for c in wo_new.columns)
        if needs_header_update:
            wo_existing_full = pd.read_csv(workouts_path)
            for col in wo_new.columns:
                if col not in wo_existing_full.columns:
                    wo_existing_full[col] = np.nan
            pd.concat([wo_existing_full, wo_new], ignore_index=True).to_csv(workouts_path, index=False)
        else:
            wo_new[existing_cols].to_csv(workouts_path, mode="a", header=False, index=False)
    if dwr_rows:
        pd.DataFrame(dwr_rows).to_csv(dwr_path, mode="a", header=False, index=False)
    if cyc_rows:
        pd.DataFrame(cyc_rows).to_csv(cyc_path, mode="a", header=False, index=False)

    return added, skipped


def _run_sync_job(force: bool = False):
    global _sync_job
    _sync_job = {"status": "running", "added": 0, "skipped": 0, "error": None}
    try:
        cfg = _load_strava_config()
        cfg = _ensure_valid_token(cfg)

        if force:
            workouts_path = DATA_DIR / "workouts.csv"
            dwr_path      = DATA_DIR / "by_type" / "DistanceWalkingRunning.csv"
            cyc_path      = DATA_DIR / "by_type" / "DistanceCycling.csv"
            for p in [workouts_path, dwr_path, cyc_path]:
                df = pd.read_csv(p)
                src_col = "sourceName" if "sourceName" in df.columns else None
                if src_col:
                    df = df[df[src_col] != "Strava"]
                if p == workouts_path:
                    for col in STRAVA_EXTRA_COLS:
                        if col not in df.columns:
                            df[col] = np.nan
                df.to_csv(p, index=False)
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
