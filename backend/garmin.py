"""
Garmin Connect integration using the garth library.
Uses email/password auth (Garmin does not expose a public OAuth API).
Tokens are persisted in garth_tokens/ directory next to this file.

Activity priority: Strava > Garmin.
When a Strava activity is imported, any Garmin activity within 5 min of the
same type is automatically removed (Strava has richer analysis).

Garmin is used for wellness data not available on Strava:
  sleep stages, overnight HRV, stress, body battery.
"""
import json
import time
from datetime import date, datetime, timedelta, timezone
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

# How close (seconds) a Garmin activity must be to a Strava one to be replaced
_STRAVA_PRIORITY_WINDOW = 5 * 60   # 5 minutes


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
    if not GARMIN_TOKEN_DIR.exists():
        return False
    try:
        garth.resume(str(GARMIN_TOKEN_DIR))
        return garth.client.oauth2_token is not None
    except Exception:
        return False


def _login(email: str, password: str, mfa_code: Optional[str] = None) -> None:
    """Authenticate with Garmin Connect and save tokens to disk."""
    def _prompt_mfa() -> str:
        if mfa_code:
            return mfa_code.strip()
        raise ValueError("MFA_REQUIRED")

    garth.login(email, password, prompt_mfa=_prompt_mfa)
    GARMIN_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    garth.save(str(GARMIN_TOKEN_DIR))


def is_connected() -> bool:
    cfg = _load_garmin_config()
    if not cfg.get("email"):
        return False
    return _resume_session()


# ─── activity ingestion ───────────────────────────────────────────────────────

def _append_garmin_activities(activities: list) -> tuple:
    """Insert Garmin activities, skipping any that already have a Strava match.

    Deduplication is by UNIQUE(start_ts, workout_type) in the DB.
    Activities already imported from Strava within 5 min are skipped
    (Strava data takes priority — richer analysis).
    """
    conn = _db()
    added = skipped = 0

    # Load Strava timestamps once for priority check
    strava_ts = [
        r[0] for r in conn.execute("SELECT start_ts FROM workouts WHERE source='Strava'").fetchall()
    ]

    def _has_strava_match(ts: float) -> bool:
        return any(abs(s - ts) < _STRAVA_PRIORITY_WINDOW for s in strava_ts)

    for act in activities:
        start_str = act.get("startTimeLocal") or act.get("startTimeGMT", "")
        try:
            dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            skipped += 1
            continue

        start_ts = dt.timestamp()

        # Skip if Strava already has this activity (Strava wins)
        if _has_strava_match(start_ts):
            skipped += 1
            continue

        type_info    = act.get("activityType") or {}
        type_key     = type_info.get("typeKey", "other") if isinstance(type_info, dict) else "other"
        workout_type = GARMIN_TYPE_MAP.get(type_key, type_key)

        duration_sec  = act.get("duration") or 0
        moving_sec    = act.get("movingDuration") or duration_sec
        end_ts        = start_ts + duration_sec
        duration_min  = round(duration_sec / 60, 4)
        distance_m    = act.get("distance") or 0
        distance_km   = round(distance_m / 1000, 4) if distance_m else None
        avg_speed_ms  = act.get("averageSpeed")
        avg_speed_kmh = round(avg_speed_ms * 3.6, 3) if avg_speed_ms else None
        cadence       = act.get("averageCadence") or act.get("avgBikeCadence")

        cur = conn.execute("""
            INSERT OR IGNORE INTO workouts
            (workout_type,start_ts,end_ts,duration_min,distance_km,active_energy_kcal,
             source,device,moving_time_min,elevation_m,avg_hr,max_hr,suffer_score,
             avg_cadence,avg_watts,avg_speed_kmh,activity_name,workout_subtype,trainer)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            workout_type, start_ts, end_ts, duration_min, distance_km,
            act.get("calories"),
            "Garmin", None,
            round(moving_sec / 60, 4),
            act.get("elevationGain"),
            act.get("averageHR"),
            act.get("maxHR"),
            None,
            cadence,
            act.get("averagePower"),
            avg_speed_kmh,
            act.get("activityName", ""),
            type_key,
            0,
        ))

        if cur.rowcount:
            added += 1
            if type_key in ("running", "trail_running", "treadmill_running", "track_running") and distance_km:
                conn.execute(
                    "INSERT OR IGNORE INTO metrics(metric_name,start_ts,end_ts,value,unit,source,device) VALUES(?,?,?,?,?,?,?)",
                    ("DistanceWalkingRunning", start_ts, end_ts, distance_km, "km", "Garmin", None),
                )
            elif ("cycling" in type_key or type_key in ("virtual_ride", "gravel_cycling", "mountain_biking")) and distance_km:
                conn.execute(
                    "INSERT OR IGNORE INTO metrics(metric_name,start_ts,end_ts,value,unit,source,device) VALUES(?,?,?,?,?,?,?)",
                    ("DistanceCycling", start_ts, end_ts, distance_km, "km", "Garmin", None),
                )
        else:
            skipped += 1

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
        if len(batch) < limit:
            break
        start += limit

    return activities


# ─── wellness ingestion ───────────────────────────────────────────────────────

def _sync_wellness(start_date: date, end_date: date) -> dict:
    """
    Fetch Garmin wellness data for the given date range and store in DB.
    Covers: sleep stages, overnight HRV, stress, body battery.
    Returns counts per category.
    """
    conn = _db()
    counts = {"sleep_rows": 0, "hrv_rows": 0, "stress_rows": 0, "body_battery_rows": 0}

    # ── 1. Sleep stages via SleepData.get() ──────────────────────────────────
    current = start_date
    while current <= end_date:
        try:
            sd = garth.SleepData.get(current)
            if sd and sd.daily_sleep_dto:
                dto = sd.daily_sleep_dto
                date_str = str(dto.calendar_date)
                start_ms = dto.sleep_start_timestamp_gmt
                end_ms   = dto.sleep_end_timestamp_gmt
                start_ts = start_ms / 1000
                end_ts   = end_ms / 1000

                stages = [
                    ("Deep",  dto.deep_sleep_seconds),
                    ("Core",  dto.light_sleep_seconds),   # Garmin "light" = Apple Health "Core"
                    ("REM",   dto.rem_sleep_seconds),
                    ("Awake", dto.awake_sleep_seconds),
                ]
                for stage, seconds in stages:
                    if seconds:
                        duration_min = round(seconds / 60, 4)
                        conn.execute("""
                            INSERT OR REPLACE INTO sleep(date, stage, start_ts, end_ts, duration_min, source)
                            VALUES(?, ?, ?, ?, ?, 'Garmin')
                        """, (date_str, stage, start_ts, end_ts, duration_min))
                        counts["sleep_rows"] += 1

                # ── Extra sleep wellness metrics ──────────────────────────────
                def _g(obj, *names, default=None):
                    """Try multiple attribute names, return first non-None."""
                    for n in names:
                        v = getattr(obj, n, None)
                        if v is not None:
                            return v
                    return default

                # Sleep Score: nested in sleep_scores.overall.value
                sleep_score_val = None
                try:
                    sleep_score_val = dto.sleep_scores.overall.value
                except Exception:
                    pass

                # avgHeartRate is NOT mapped by garth's Python object — fetch from raw endpoint
                raw_avg_hr = None
                try:
                    raw = garth.connectapi(
                        f"/wellness-service/wellness/dailySleepData/{dto.user_profile_pk}",
                        params={"date": date_str, "nonSleepBufferMinutes": 60},
                    )
                    raw_dto = raw.get("dailySleepDTO") or {}
                    raw_avg_hr = raw_dto.get("avgHeartRate")
                except Exception:
                    pass

                # Use calendar_date midnight as the canonical ts for all wellness metrics
                # (so they align to the Garmin "date" label, e.g. "Mar 25" regardless of
                # when sleep physically started/ended in UTC)
                cal_ts     = datetime(dto.calendar_date.year, dto.calendar_date.month, dto.calendar_date.day, tzinfo=timezone.utc).timestamp()
                cal_ts_end = cal_ts + 86400

                extra_metrics = [
                    # Confirmed attribute names via garth probe 2026-03-26
                    ("GarminSleepScore",          sleep_score_val,                                   "score"),
                    ("GarminSleepHR",             raw_avg_hr,                                        "bpm"),
                    ("GarminSleepRespiration",    _g(dto, "average_respiration_value"),              "brpm"),
                    ("GarminSleepRespirationLow", _g(dto, "lowest_respiration_value"),               "brpm"),
                    ("GarminSleepSpO2",           _g(dto, "average_sp_o2_value",                     # note: sp_o2 not spo2
                                                      "average_spo2_value"),                         "pct"),
                    ("GarminSleepSpO2Low",        _g(dto, "lowest_sp_o2_value",
                                                      "lowest_spo2_value"),                          "pct"),
                    ("GarminSleepRestless",       _g(dto, "awake_count",                             # best proxy available
                                                      "restless_moments_count"),                     "count"),
                    ("GarminAvgSleepStress",      _g(dto, "avg_sleep_stress"),                       "score"),
                    # Body battery during sleep is captured in the user-summary step below
                ]

                for metric_name, val, unit in extra_metrics:
                    if val is not None:
                        try:
                            conn.execute("""
                                INSERT OR REPLACE INTO metrics
                                (metric_name, start_ts, end_ts, value, unit, source, device)
                                VALUES(?, ?, ?, ?, ?, 'Garmin', NULL)
                            """, (metric_name, cal_ts, cal_ts_end, float(val), unit))
                        except Exception:
                            pass

        except Exception:
            pass
        current += timedelta(days=1)

    # ── 2. Overnight HRV via DailyHRV.list() ─────────────────────────────────
    # garth returns up to 28 days per call — chunk accordingly
    chunk_start = start_date
    while chunk_start <= end_date:
        chunk_end = min(chunk_start + timedelta(days=27), end_date)
        try:
            hrv_list = garth.DailyHRV.list(end=chunk_end, period=(chunk_end - chunk_start).days + 1)
            for hrv in hrv_list:
                if hrv.last_night_avg:
                    ts = datetime(hrv.calendar_date.year, hrv.calendar_date.month, hrv.calendar_date.day, tzinfo=timezone.utc).timestamp()
                    conn.execute("""
                        INSERT OR IGNORE INTO metrics
                        (metric_name, start_ts, end_ts, value, unit, source, device)
                        VALUES('HeartRateVariabilitySDNN', ?, ?, ?, 'ms', 'Garmin', NULL)
                    """, (ts, ts + 86400, hrv.last_night_avg))
                    counts["hrv_rows"] += 1
        except Exception:
            pass
        chunk_start = chunk_end + timedelta(days=1)

    # ── 3. Stress via DailyStress.list() ─────────────────────────────────────
    chunk_start = start_date
    while chunk_start <= end_date:
        chunk_end = min(chunk_start + timedelta(days=27), end_date)
        try:
            stress_list = garth.DailyStress.list(end=chunk_end, period=(chunk_end - chunk_start).days + 1)
            for s in stress_list:
                if s.overall_stress_level and s.overall_stress_level > 0:
                    ts = datetime(s.calendar_date.year, s.calendar_date.month, s.calendar_date.day, tzinfo=timezone.utc).timestamp()
                    conn.execute("""
                        INSERT OR IGNORE INTO metrics
                        (metric_name, start_ts, end_ts, value, unit, source, device)
                        VALUES('GarminStress', ?, ?, ?, 'score', 'Garmin', NULL)
                    """, (ts, ts + 86400, s.overall_stress_level))
                    counts["stress_rows"] += 1
        except Exception:
            pass
        chunk_start = chunk_end + timedelta(days=1)

    # ── 4. Body Battery via connectapi ────────────────────────────────────────
    # Returns per-day max/min/end body battery (0-100 readiness score)
    chunk_start = start_date
    while chunk_start <= end_date:
        chunk_end = min(chunk_start + timedelta(days=13), end_date)   # API limit ~2 weeks
        try:
            bb_data = garth.connectapi(
                "/wellness-service/wellness/bodyBattery/reports/daily",
                params={"startDate": str(chunk_start), "endDate": str(chunk_end)},
            )
            for day in (bb_data or []):
                day_date = day.get("date") or day.get("calendarDate", "")
                if not day_date:
                    continue
                # Use the charged level (highest) as the daily readiness score
                high = day.get("bodyBatteryValueForDay")
                if high is None:
                    # fall back to max in the stat list
                    stat_list = day.get("bodyBatteryStatList") or []
                    values = [s.get("bodyBattery") for s in stat_list if s.get("bodyBattery") is not None]
                    high = max(values) if values else None
                if high is not None:
                    try:
                        ts = datetime.strptime(day_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
                        conn.execute("""
                            INSERT OR IGNORE INTO metrics
                            (metric_name, start_ts, end_ts, value, unit, source, device)
                            VALUES('GarminBodyBattery', ?, ?, ?, 'score', 'Garmin', NULL)
                        """, (ts, ts + 86400, high))
                        counts["body_battery_rows"] += 1
                    except Exception:
                        pass
        except Exception:
            pass
        chunk_start = chunk_end + timedelta(days=1)

    # ── 5. Daily heart rate stats via user-summary endpoint ─────────────────
    # /usersummary-service/usersummary/daily returns min/max/resting HR plus
    # minAvg/maxAvg that capture full-day HR including workouts.
    current = start_date
    hr_day_count = 0
    while current <= end_date:
        try:
            summary = garth.connectapi(
                "/usersummary-service/usersummary/daily",
                params={"calendarDate": current.isoformat()},
            )
            if summary:
                max_hr = summary.get("maxHeartRate")
                min_hr = summary.get("minHeartRate")
                resting_hr = summary.get("restingHeartRate")
                # maxAvgHeartRate / minAvgHeartRate are rolling averages —
                # use the midpoint of min and maxAvg as daily mean estimate
                min_avg = summary.get("minAvgHeartRate")
                max_avg = summary.get("maxAvgHeartRate")
                avg_hr = round((min_avg + max_avg) / 2, 1) if min_avg and max_avg else None

                ts = datetime(current.year, current.month, current.day, tzinfo=timezone.utc).timestamp()
                bb_sleep = summary.get("bodyBatteryDuringSleep")
                for metric, val in [
                    ("GarminHeartRate_mean",       avg_hr),
                    ("GarminHeartRate_min",        min_hr),
                    ("GarminHeartRate_max",        max_hr),
                    ("GarminRestingHeartRate",     resting_hr),
                    ("GarminBodyBatteryDuringSleep", bb_sleep),
                ]:
                    if val is not None and val > 0:
                        unit = "score" if "Battery" in metric else "bpm"
                        conn.execute("""
                            INSERT OR REPLACE INTO metrics
                            (metric_name, start_ts, end_ts, value, unit, source, device)
                            VALUES(?, ?, ?, ?, ?, 'Garmin', NULL)
                        """, (metric, ts, ts + 86400, float(val), unit))
                        counts["hr_rows"] = counts.get("hr_rows", 0) + 1
        except Exception:
            pass
        hr_day_count += 1
        if hr_day_count % 30 == 0:
            conn.commit()
        current += timedelta(days=1)

    # ── 6. VO2 Max from biometric profile (current snapshot) ─────────────────
    # Garmin doesn't expose a historical VO2 Max series, so we snapshot the
    # current value on every sync — over time this builds a sparse history.
    try:
        profile = garth.connectapi("/userprofile-service/userprofile/personal-information")
        bio = profile.get("biometricProfile", {})
        today_ts = datetime(end_date.year, end_date.month, end_date.day, tzinfo=timezone.utc).timestamp()
        for metric, val in [
            ("VO2Max",         bio.get("vo2Max")),
            ("VO2MaxCycling",  bio.get("vo2MaxCycling")),
        ]:
            if val is not None:
                conn.execute("""
                    INSERT OR REPLACE INTO metrics
                    (metric_name, start_ts, end_ts, value, unit, source, device)
                    VALUES(?, ?, ?, ?, 'mL/kg/min', 'Garmin', NULL)
                """, (metric, today_ts, today_ts + 86400, float(val)))
                counts["vo2max"] = counts.get("vo2max", 0) + 1
    except Exception:
        pass

    conn.commit()
    return counts


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
            conn.execute("DELETE FROM sleep WHERE source='Garmin'")
            conn.commit()
            after_ts = 0.0
        else:
            after_ts = float(cfg.get("last_sync_timestamp") or 0)

        # Sync activities
        activities = _fetch_activities(after_ts)
        added, skipped = _append_garmin_activities(activities)

        # Sync wellness data (sleep, HRV, stress, body battery)
        wellness_start = date.fromtimestamp(after_ts) if after_ts else date(2020, 1, 1)
        wellness_counts = _sync_wellness(wellness_start, date.today())

        cfg["last_sync_timestamp"] = int(time.time())
        _save_garmin_config(cfg)

        clear_all_caches()

        _garmin_sync_job = {
            "status": "done",
            "added": added,
            "skipped": skipped,
            "wellness": wellness_counts,
            "error": None,
        }

    except Exception as e:
        _garmin_sync_job = {"status": "error", "added": 0, "skipped": 0, "error": str(e)}
