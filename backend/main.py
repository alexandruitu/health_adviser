"""
Apple Health Dashboard — FastAPI backend
Reads from the cleaned CSV directory and serves aggregated data.
"""

import io
import json
import math
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from functools import lru_cache
from typing import Optional, List

import httpx
import numpy as np
import pandas as pd
from fastapi import FastAPI, Query, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

DATA_DIR              = Path(__file__).parent.parent.parent / "health_csvs" / "cleaned"
RAW_DATA_DIR          = Path(__file__).parent.parent.parent / "health_csvs"
STRAVA_CONFIG_PATH    = Path(__file__).parent.parent / "strava_config.json"
HEALTH_INGEST_CONFIG  = Path(__file__).parent.parent / "health_ingest_config.json"
GDRIVE_CONFIG_PATH    = Path(__file__).parent.parent / "gdrive_config.json"
STRAVA_AUTH_URL     = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL    = "https://www.strava.com/oauth/token"
STRAVA_REDIRECT_URI = "http://localhost:8000/api/strava/callback"
GDRIVE_AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
GDRIVE_TOKEN_URL    = "https://oauth2.googleapis.com/token"
GDRIVE_REDIRECT_URI = "http://localhost:8000/api/gdrive/callback"
GDRIVE_SCOPES       = "https://www.googleapis.com/auth/drive.readonly"
DB_PATH             = Path(__file__).parent / "health.db"


def _db() -> sqlite3.Connection:
    """Return a thread-local SQLite connection with row_factory."""
    import threading
    if not hasattr(_db, "_local"):
        _db._local = threading.local()
    if not hasattr(_db._local, "conn"):
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = _sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _db._local.conn = conn
    return _db._local.conn


app = FastAPI(title="Apple Health API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# ─── cached loaders ──────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _daily() -> pd.DataFrame:
    """Compute daily summary from SQLite metrics table."""
    conn = _db()
    # Key metrics we need for charts — aggregate per day
    METRIC_AGG = {
        "StepCount":                    "SUM",
        "ActiveEnergyBurned":           "SUM",
        "BasalEnergyBurned":            "SUM",
        "RestingHeartRate":             "AVG",
        "HeartRateVariabilitySDNN":     "AVG",
        "BodyMass":                     "AVG",
        "BodyFatPercentage":            "AVG",
        "BodyMassIndex":                "AVG",
        "LeanBodyMass":                 "AVG",
        "VO2Max":                       "AVG",
        "BloodGlucose":                 "AVG",
        "DistanceWalkingRunning":       "SUM",
        "DistanceCycling":              "SUM",
        "FlightsClimbed":               "SUM",
        "AppleExerciseTime":            "SUM",
        "MindfulSession":               "SUM",
    }
    # Build a pivot using multiple queries then merge
    base = pd.date_range(
        start=pd.Timestamp("2012-01-01"),
        end=pd.Timestamp.now().normalize(),
        freq="D"
    )
    df = pd.DataFrame({"date": base})
    df["date"] = df["date"].dt.date.astype(str)

    for metric, agg in METRIC_AGG.items():
        q = f"""
            SELECT date(datetime(start_ts, 'unixepoch')) AS day,
                   {agg}(value) AS val
            FROM metrics
            WHERE metric_name = ?
            GROUP BY day
        """
        tmp = pd.read_sql_query(q, conn, params=(metric,))
        tmp.columns = ["date", metric]
        df = df.merge(tmp, on="date", how="left")

    df["date"] = pd.to_datetime(df["date"])
    return df


@lru_cache(maxsize=1)
@lru_cache(maxsize=1)
def _sleep() -> pd.DataFrame:
    """Build nightly sleep summary from SQLite sleep table (stage rows)."""
    conn = _db()
    df = pd.read_sql_query(
        "SELECT date, stage, duration_min FROM sleep WHERE stage IN ('Core','Deep','REM','Awake','InBed','Unspecified')",
        conn
    )
    if df.empty:
        return pd.DataFrame(columns=["night", "Awake", "Core", "Deep", "InBed", "REM", "Unspecified", "total_sleep_hours"])
    df["duration_h"] = df["duration_min"] / 60.0
    pivot = df.pivot_table(index="date", columns="stage", values="duration_h", aggfunc="sum").reset_index()
    pivot.columns.name = None
    pivot = pivot.rename(columns={"date": "night"})
    pivot["night"] = pd.to_datetime(pivot["night"])
    for col in ["Awake", "Core", "Deep", "InBed", "REM", "Unspecified"]:
        if col not in pivot.columns:
            pivot[col] = 0.0
    pivot = pivot.fillna(0.0)
    # total_sleep_hours = Core + Deep + REM (exclude InBed/Awake/Unspecified)
    pivot["total_sleep_hours"] = pivot[["Core", "Deep", "REM"]].sum(axis=1)
    # Fall back to InBed or Unspecified for older data with no stages
    mask = pivot["total_sleep_hours"] == 0
    pivot.loc[mask, "total_sleep_hours"] = pivot.loc[mask, ["InBed", "Unspecified"]].max(axis=1)
    return pivot.sort_values("night")


STRAVA_EXTRA_COLS = [
    "moving_time_min", "elevation_m", "avg_hr", "max_hr",
    "suffer_score", "avg_cadence", "avg_watts", "avg_speed_kmh",
    "activity_name", "workout_subtype", "trainer",
]

@lru_cache(maxsize=1)
def _workouts() -> pd.DataFrame:
    conn = _db()
    df = pd.read_sql_query("""
        SELECT
            workout_type        AS workoutType,
            start_ts,
            end_ts,
            duration_min,
            distance_km         AS distance,
            active_energy_kcal  AS activeEnergy_kcal,
            source              AS sourceName,
            device,
            moving_time_min,
            elevation_m,
            avg_hr,
            max_hr,
            suffer_score,
            avg_cadence,
            avg_watts,
            avg_speed_kmh,
            activity_name,
            workout_subtype,
            trainer
        FROM workouts
        ORDER BY start_ts DESC
    """, conn)
    df["startDate"] = pd.to_datetime(df["start_ts"], unit="s", errors="coerce")
    df["endDate"]   = pd.to_datetime(df["end_ts"],   unit="s", errors="coerce")
    return df


@lru_cache(maxsize=1)
def _activity() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "activity_summaries.csv", parse_dates=["dateComponents"])
    df = df.sort_values("dateComponents")
    return df


@lru_cache(maxsize=1)
def _profile() -> dict:
    df = pd.read_csv(DATA_DIR / "profile.csv")
    return dict(zip(df["attribute"], df["value"]))


@lru_cache(maxsize=64)
def _by_type(name: str) -> pd.DataFrame:
    conn = _db()
    df = pd.read_sql_query("""
        SELECT
            start_ts,
            end_ts,
            value       AS value_num,
            unit,
            source      AS sourceName,
            device
        FROM metrics
        WHERE metric_name = ?
        ORDER BY start_ts
    """, conn, params=(name,))
    df["startDate"] = pd.to_datetime(df["start_ts"], unit="s", errors="coerce")
    df["endDate"]   = pd.to_datetime(df["end_ts"],   unit="s", errors="coerce")
    return df


def date_filter(df: pd.DataFrame, col: str, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
    if start:
        df = df[df[col] >= start]
    if end:
        df = df[df[col] <= end]
    return df


def to_records(df: pd.DataFrame) -> list:
    import math
    rows = df.to_dict(orient="records")
    # Replace NaN/inf with None so Python's json encoder doesn't choke
    clean = []
    for row in rows:
        clean.append({
            k: (None if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else v)
            for k, v in row.items()
        })
    return clean


# ─── routes ──────────────────────────────────────────────────────────────────

@app.get("/api/profile")
def profile():
    return _profile()


@app.get("/api/daily")
def daily(
    start: Optional[str] = None,
    end: Optional[str] = None,
    metrics: Optional[str] = Query(None, description="Comma-separated column names"),
):
    df = _daily().copy()
    df = date_filter(df, "date", start, end)
    if metrics:
        cols = ["date"] + [m for m in metrics.split(",") if m in df.columns]
        df = df[cols].copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return to_records(df)


@app.get("/api/daily/columns")
def daily_columns():
    return list(_daily().columns)


@app.get("/api/sleep")
def sleep(start: Optional[str] = None, end: Optional[str] = None):
    df = _sleep().copy()
    df = date_filter(df, "night", start, end).copy()
    df["night"] = df["night"].dt.strftime("%Y-%m-%d")
    return to_records(df)


@app.get("/api/workouts")
def workouts(
    start: Optional[str] = None,
    end: Optional[str] = None,
    workout_type: Optional[str] = None,
):
    df = _workouts().copy()
    df = date_filter(df, "startDate", start, end).copy()
    if workout_type:
        df = df[df["workoutType"].str.contains(workout_type, case=False, na=False)].copy()
    df["startDate"] = df["startDate"].dt.strftime("%Y-%m-%d")
    df["endDate"] = df["endDate"].dt.strftime("%Y-%m-%d")
    return to_records(df)


@app.get("/api/workouts/types")
def workout_types():
    df = _workouts()
    counts = df["workoutType"].value_counts().reset_index()
    counts.columns = ["type", "count"]
    return to_records(counts)


@app.get("/api/activity")
def activity(start: Optional[str] = None, end: Optional[str] = None):
    df = _activity().copy()
    df = date_filter(df, "dateComponents", start, end).copy()
    df["dateComponents"] = df["dateComponents"].dt.strftime("%Y-%m-%d")
    return to_records(df)


@app.get("/api/metric/{name}")
def metric_series(
    name: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    resample: Optional[str] = Query(None, description="Pandas resample rule, e.g. 1D, 1W, 1ME"),
):
    """Return a raw or resampled time series for any by_type metric."""
    try:
        df = _by_type(name)
    except FileNotFoundError:
        return {"error": f"Unknown metric: {name}"}

    df = date_filter(df, "startDate", start, end)

    if resample:
        df = df.set_index("startDate")
        numeric = df.select_dtypes("number")
        df = numeric.resample(resample).mean().reset_index()
        df = df.rename(columns={"startDate": "date"})
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    else:
        df["date"] = df["startDate"].dt.strftime("%Y-%m-%d %H:%M")
        df = df.drop(columns=["startDate", "endDate"], errors="ignore")

    return to_records(df)


@app.get("/api/metric/{name}/stats")
def metric_stats(name: str, start: Optional[str] = None, end: Optional[str] = None):
    """Summary statistics for a metric."""
    try:
        df = _by_type(name)
    except FileNotFoundError:
        return {"error": f"Unknown metric: {name}"}
    df = date_filter(df, "startDate", start, end)
    col = "value_num"
    if col not in df.columns:
        return {"error": "No numeric column found"}
    s = df[col].dropna()
    return {
        "count": int(s.count()),
        "mean": round(float(s.mean()), 2),
        "median": round(float(s.median()), 2),
        "std": round(float(s.std()), 2),
        "min": round(float(s.min()), 2),
        "max": round(float(s.max()), 2),
        "q25": round(float(s.quantile(0.25)), 2),
        "q75": round(float(s.quantile(0.75)), 2),
        "unit": df["unit"].iloc[0] if "unit" in df.columns else "",
        "date_min": str(df["startDate"].min())[:10],
        "date_max": str(df["startDate"].max())[:10],
    }


@app.get("/api/summary/cards")
def summary_cards():
    """Key stats for dashboard overview cards."""
    daily = _daily()
    last90 = daily[daily["date"] >= daily["date"].max() - pd.Timedelta(days=90)]

    def safe_mean(col):
        s = last90[col].dropna()
        return round(float(s.mean()), 1) if len(s) else None

    def safe_last(col):
        s = daily[col].dropna()
        return round(float(s.iloc[-1]), 1) if len(s) else None

    sleep = _sleep()
    last90_sleep = sleep[sleep["night"] >= sleep["night"].max() - pd.Timedelta(days=90)]
    avg_sleep = round(float(last90_sleep["total_sleep_hours"].dropna().mean()), 1) if len(last90_sleep) else None

    workouts = _workouts()
    last90_wo = workouts[workouts["startDate"] >= workouts["startDate"].max() - pd.Timedelta(days=90)]
    workout_count = int(len(last90_wo))

    return {
        "avg_steps_90d": safe_mean("StepCount"),
        "avg_resting_hr_90d": safe_mean("RestingHeartRate"),
        "avg_hrv_90d": safe_mean("HeartRateVariabilitySDNN"),
        "avg_sleep_90d": avg_sleep,
        "latest_weight_kg": safe_last("BodyMass"),
        "latest_body_fat_pct": safe_last("BodyFatPercentage"),
        "latest_vo2max": safe_last("VO2Max"),
        "workouts_90d": workout_count,
        "avg_active_kcal_90d": safe_mean("ActiveEnergyBurned"),
        "period": "last 90 days",
    }


@lru_cache(maxsize=1)
def _valid_metrics() -> list[str]:
    """Return only metrics that have ≥10 valid numeric rows."""
    bt = DATA_DIR / "by_type"
    valid = []
    for path in sorted(bt.glob("*.csv")):
        try:
            df = pd.read_csv(path, usecols=["value_num"], low_memory=False)
            if df["value_num"].dropna().shape[0] >= 10:
                valid.append(path.stem)
        except Exception:
            pass
    return valid


@app.get("/api/available_metrics")
def available_metrics():
    return _valid_metrics()


# ─── training analytics ──────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _running_dist_by_day() -> pd.Series:
    """
    Daily running distance (km) from DistanceWalkingRunning records within
    running workout windows, with multi-source deduplication.

    Problem: Apple Health stores DWR records from multiple sources simultaneously
    (e.g. Strava posts one aggregate record; iPhone posts 10-min segments) for
    the same workout, causing double-counting when naively summed.

    Solution: for each workout window, group records by source app and take
    the source with the highest total — typically the training app (Strava/Garmin)
    which records a single accurate value for the whole effort.
    """
    try:
        dwr = _by_type("DistanceWalkingRunning").copy()
    except FileNotFoundError:
        return pd.Series(dtype=float, name="running_km")

    wo = _workouts()
    all_runs = wo[wo["workoutType"].str.contains("Running", na=False)].copy()
    # Drop outlier sessions > 10 h
    all_runs = all_runs[all_runs["duration_min"] <= 600]
    runs = all_runs[["startDate", "endDate"]].copy()

    if runs.empty or dwr.empty:
        return pd.Series(dtype=float, name="running_km")

    # Convert to km if device was set to miles
    if "unit" in dwr.columns and (dwr["unit"] == "mi").any():
        mi_mask = dwr["unit"] == "mi"
        dwr.loc[mi_mask, "value_num"] = dwr.loc[mi_mask, "value_num"] * 1.60934

    dwr["date"] = dwr["startDate"].dt.normalize()
    source_col = "sourceName" if "sourceName" in dwr.columns else None
    keep_cols = ["startDate", "date", "value_num"] + ([source_col] if source_col else [])
    dwr_sorted = dwr.sort_values("startDate")[keep_cols].reset_index(drop=True)

    runs_sorted = runs.sort_values("startDate").reset_index(drop=True)
    runs_sorted = runs_sorted.rename(columns={"startDate": "run_start", "endDate": "run_end"})

    # For each DWR record, find the most-recently-started run that began before it
    merged = pd.merge_asof(
        dwr_sorted,
        runs_sorted,
        left_on="startDate",
        right_on="run_start",
        direction="backward",
    )

    # Keep only records whose startDate falls STRICTLY inside the workout window
    # (strict < excludes post-workout pedometer records that begin at workout end)
    in_run = merged[merged["startDate"] < merged["run_end"]].copy()

    if in_run.empty:
        return pd.Series(dtype=float, name="running_km")

    if source_col:
        # Use workout start as a stable workout ID
        in_run["workout_id"] = in_run["run_start"]
        # Sum each (workout, source) pair, then pick the best source per workout
        by_source = (
            in_run.groupby(["workout_id", "date", source_col])["value_num"]
            .sum()
        )
        best = by_source.groupby(level=["workout_id", "date"]).max()
        return best.groupby("date").sum().rename("running_km")
    else:
        return in_run.groupby("date")["value_num"].sum().rename("running_km")


@lru_cache(maxsize=1)
def _cycling_dist_by_day() -> pd.Series:
    """
    Daily cycling distance (km) from DistanceCycling records within cycling
    workout windows, with multi-source deduplication (same logic as running).
    """
    try:
        dc = _by_type("DistanceCycling").copy()
    except FileNotFoundError:
        return pd.Series(dtype=float, name="cycling_km")

    wo = _workouts()
    all_rides = wo[wo["workoutType"].str.contains("Cycling", na=False)].copy()
    # Drop outlier sessions (e.g. Strava never-stopped rides > 10 h)
    all_rides = all_rides[all_rides["duration_min"] <= 600]
    rides = all_rides[["startDate", "endDate"]].copy()

    if rides.empty or dc.empty:
        return pd.Series(dtype=float, name="cycling_km")

    if "unit" in dc.columns and (dc["unit"] == "mi").any():
        dc.loc[dc["unit"] == "mi", "value_num"] *= 1.60934

    dc["date"] = dc["startDate"].dt.normalize()
    source_col = "sourceName" if "sourceName" in dc.columns else None
    keep_cols = ["startDate", "date", "value_num"] + ([source_col] if source_col else [])
    dc_sorted = dc.sort_values("startDate")[keep_cols].reset_index(drop=True)

    rides_sorted = rides.sort_values("startDate").reset_index(drop=True)
    rides_sorted = rides_sorted.rename(columns={"startDate": "ride_start", "endDate": "ride_end"})

    merged = pd.merge_asof(
        dc_sorted,
        rides_sorted,
        left_on="startDate",
        right_on="ride_start",
        direction="backward",
    )
    in_ride = merged[merged["startDate"] < merged["ride_end"]].copy()

    if in_ride.empty:
        return pd.Series(dtype=float, name="cycling_km")

    if source_col:
        in_ride["workout_id"] = in_ride["ride_start"]
        by_source = (
            in_ride.groupby(["workout_id", "date", source_col])["value_num"]
            .sum()
        )
        best = by_source.groupby(level=["workout_id", "date"]).max()
        return best.groupby("date").sum().rename("cycling_km")
    else:
        return in_ride.groupby("date")["value_num"].sum().rename("cycling_km")


@lru_cache(maxsize=1)
def _pmc_df() -> pd.DataFrame:
    """
    Compute full-history PMC (ATL / CTL / TSB) using the Banister TRIMP model.

    TRIMP (Training Impulse) = duration_min × HR_ratio × 0.64 × e^(b × HR_ratio)
      HR_ratio = (avg_HR − rest_HR) / (max_HR − rest_HR)
      b = 1.92 for running, 1.67 for cycling (sport-specific blood-lactate curve)

    For activities without HR data, a conservative default HR_ratio is used
    (equivalent to ~65 % HRmax effort).

    ATL τ = 7d  (acute fatigue),  CTL τ = 42d  (chronic fitness)
    TSB = CTL − ATL  (form / freshness)
    """
    # ── HR config (personal) ────────────────────────────────────────────────
    REST_HR = 50          # bpm  (user resting HR)
    MAX_HR  = 185         # bpm  (user max HR)
    HR_RANGE = MAX_HR - REST_HR   # 135

    # default HR ratio when avg_hr is missing (~65 % HRmax → moderate aerobic)
    DEFAULT_HR_RATIO = (0.65 * MAX_HR - REST_HR) / HR_RANGE  # ≈ 0.52

    wo = _workouts().copy()
    wo["date"]     = pd.to_datetime(wo["startDate"], errors="coerce").dt.normalize()
    wo["duration_min"] = pd.to_numeric(wo["duration_min"], errors="coerce").fillna(0)
    wo["avg_hr"]   = pd.to_numeric(wo.get("avg_hr"), errors="coerce")
    wo["is_run"]   = wo["workoutType"].str.contains("Running", na=False)
    wo["is_cyc"]   = wo["workoutType"].str.contains("Cycling", na=False)

    # ── compute TRIMP per activity ───────────────────────────────────────────
    def trimp_row(row):
        dur = row["duration_min"]
        if dur <= 0:
            return 0.0
        hr = row["avg_hr"]
        if pd.isna(hr) or hr <= REST_HR:
            hr_ratio = DEFAULT_HR_RATIO
        else:
            hr_ratio = min((hr - REST_HR) / HR_RANGE, 1.0)
        b = 1.92 if row["is_run"] else 1.67   # running vs cycling exponent
        return dur * hr_ratio * 0.64 * np.exp(b * hr_ratio)

    wo["trimp"] = wo.apply(trimp_row, axis=1)

    # filter outlier sessions > 16 h (unstopped GPS tracks)
    wo = wo[wo["duration_min"] < 960]

    trimp_total = wo.groupby("date")["trimp"].sum()
    run_min     = wo[wo["is_run"]].groupby("date")["duration_min"].sum()
    cyc_min     = wo[wo["is_cyc"]].groupby("date")["duration_min"].sum()

    full_range = pd.date_range(trimp_total.index.min(), pd.Timestamp.today().normalize(), freq="D")
    full = pd.DataFrame(index=full_range)
    full["load"]    = trimp_total
    full["run_min"] = run_min
    full["cyc_min"] = cyc_min
    full = full.fillna(0.0)

    # exact Banister exponential decay:  alpha = 1 − e^(−1/τ)
    alpha_atl = 1 - np.exp(-1 / 7)
    alpha_ctl = 1 - np.exp(-1 / 42)

    full["atl"] = full["load"].ewm(alpha=alpha_atl, adjust=False).mean().round(1)
    full["ctl"] = full["load"].ewm(alpha=alpha_ctl, adjust=False).mean().round(1)
    full["tsb"] = (full["ctl"] - full["atl"]).round(1)

    full.index.name = "date"
    return full.reset_index()


def _period_col(series: pd.Series, resolution: str) -> pd.Series:
    """Return a sortable period-start string for each timestamp."""
    if resolution == "week":
        # ISO week Monday
        return series.dt.to_period("W").dt.start_time.dt.strftime("%Y-%m-%d")
    if resolution == "month":
        return series.dt.to_period("M").dt.start_time.dt.strftime("%Y-%m")
    return series.dt.year.astype(str)


@app.get("/api/training/volume")
def training_volume(
    resolution: str = "month",
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    """Volume aggregated by sport and time resolution (week | month | year)."""
    wo = _workouts().copy()
    ds = _daily().copy()

    # Tag sport
    wo["sport"] = "other"
    wo.loc[wo["workoutType"].str.contains("Running", na=False), "sport"] = "running"
    wo.loc[wo["workoutType"].str.contains("Cycling", na=False), "sport"] = "cycling"

    if start:
        wo = wo[wo["startDate"] >= start]
        ds = ds[ds["date"] >= start]
    if end:
        wo = wo[wo["startDate"] <= end]
        ds = ds[ds["date"] <= end]

    wo["period"] = _period_col(wo["startDate"], resolution)
    ds["period"] = _period_col(ds["date"], resolution)

    # Filter out unrealistically long workouts (e.g. Strava sessions never stopped)
    MAX_WORKOUT_MIN = 600  # 10 hours — anything longer is an outlier
    wo_valid = wo[wo["duration_min"] <= MAX_WORKOUT_MIN]

    run = wo_valid[wo_valid["sport"] == "running"].groupby("period").agg(
        running_min=("duration_min", "sum"),
        running_sessions=("duration_min", "count"),
        longest_run_min=("duration_min", "max"),
    )
    cyc = wo_valid[wo_valid["sport"] == "cycling"].groupby("period").agg(
        cycling_min=("duration_min", "sum"),
        cycling_sessions=("duration_min", "count"),
        longest_ride_min=("duration_min", "max"),
    )
    # cycling_km: read from by_type/DistanceCycling.csv so Strava-synced rides are included
    cyc_dist_day = _cycling_dist_by_day()
    if len(cyc_dist_day) > 0:
        cd = cyc_dist_day.reset_index()
        cd.columns = ["date", "cycling_km"]
        if start:
            cd = cd[cd["date"] >= pd.Timestamp(start)]
        if end:
            cd = cd[cd["date"] <= pd.Timestamp(end)]
        cd["period"] = _period_col(cd["date"], resolution)
        cyc_dist = cd.groupby("period")["cycling_km"].sum().rename("cycling_km").to_frame()
    else:
        cyc_dist = pd.DataFrame(columns=["period", "cycling_km"]).set_index("period")

    # running_km: use workout-window-filtered records to exclude walking distance
    run_dist_day = _running_dist_by_day()
    if len(run_dist_day) > 0:
        rd = run_dist_day.reset_index()
        rd.columns = ["date", "running_km"]
        if start:
            rd = rd[rd["date"] >= pd.Timestamp(start)]
        if end:
            rd = rd[rd["date"] <= pd.Timestamp(end)]
        rd["period"] = _period_col(rd["date"], resolution)
        run_dist = rd.groupby("period")["running_km"].sum()
    else:
        run_dist = pd.Series(dtype=float, name="running_km")
    dist = cyc_dist.join(run_dist, how="outer")

    all_periods = sorted(set(run.index) | set(cyc.index) | set(dist.index))
    if not all_periods:
        return []
    result = pd.DataFrame({"period": pd.Series(all_periods, dtype="object")})
    for part in [run, cyc, dist]:
        result = result.merge(part.reset_index(), on="period", how="left")
    result = result.fillna(0)

    for col in ["running_min", "cycling_min", "running_km", "cycling_km",
                "longest_run_min", "longest_ride_min"]:
        if col in result.columns:
            result[col] = result[col].round(1)
    for col in ["running_sessions", "cycling_sessions"]:
        if col in result.columns:
            result[col] = result[col].astype(int)

    return to_records(result)


@app.get("/api/training/pmc")
def training_pmc(
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    """Fitness (CTL) / Fatigue (ATL) / Form (TSB) performance management curve."""
    df = _pmc_df().copy()
    df = date_filter(df, "date", start, end)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return to_records(df)


@app.get("/api/training/yoy")
def training_yoy(sport: str = "running"):
    """Year-over-year monthly volumes (minutes + km) for running or cycling."""
    wo = _workouts().copy()
    wo["year"]  = wo["startDate"].dt.year
    wo["month"] = wo["startDate"].dt.month

    if sport == "running":
        sport_wo  = wo[wo["workoutType"].str.contains("Running", na=False)]
        dist_day  = _running_dist_by_day()
    else:
        sport_wo  = wo[wo["workoutType"].str.contains("Cycling", na=False)]
        dist_day  = _cycling_dist_by_day()

    # Drop outlier sessions > 10 h before aggregating minutes
    sport_wo = sport_wo[sport_wo["duration_min"] <= 600]
    min_m = sport_wo.groupby(["year", "month"])["duration_min"].sum()

    # Group deduplicated daily distances by (year, month)
    if len(dist_day) > 0:
        dist_df = dist_day.reset_index()
        dist_df.columns = ["date", "km"]
        dist_df["year"]  = dist_df["date"].dt.year
        dist_df["month"] = dist_df["date"].dt.month
        km_m = dist_df.groupby(["year", "month"])["km"].sum()
    else:
        km_m = pd.Series(dtype=float)

    years = sorted(wo["year"].unique())
    month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    rows = []
    for m in range(1, 13):
        row: dict = {"month": m, "label": month_names[m - 1]}
        for y in years:
            row[f"min_{y}"] = round(float(min_m.get((y, m), 0)), 1)
            row[f"km_{y}"]  = round(float(km_m.get((y, m), 0)), 1)
        rows.append(row)

    return {"data": rows, "years": [str(y) for y in years]}


@app.get("/api/training/hrv")
def training_hrv(
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    """Daily HRV with 30-day rolling baseline."""
    hrv = _by_type("HeartRateVariabilitySDNN").copy()
    hrv["date"] = hrv["startDate"].dt.normalize()
    daily_hrv = hrv.groupby("date")["value_num"].mean().reset_index()
    daily_hrv.columns = ["date", "hrv"]

    if start:
        daily_hrv = daily_hrv[daily_hrv["date"] >= start]
    if end:
        daily_hrv = daily_hrv[daily_hrv["date"] <= end]

    daily_hrv["hrv_30d"] = (
        daily_hrv["hrv"].rolling(30, min_periods=5).mean().round(1)
    )
    daily_hrv["hrv"] = daily_hrv["hrv"].round(1)
    daily_hrv["date"] = daily_hrv["date"].dt.strftime("%Y-%m-%d")
    return to_records(daily_hrv)


# ─── Strava integration ───────────────────────────────────────────────────────

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


def _append_activities(activities: list) -> tuple:
    """Append new Strava activities to workouts.csv and distance CSVs."""
    workouts_path = DATA_DIR / "workouts.csv"
    dwr_path      = DATA_DIR / "by_type" / "DistanceWalkingRunning.csv"
    cyc_path      = DATA_DIR / "by_type" / "DistanceCycling.csv"

    wo_existing  = pd.read_csv(workouts_path)
    dwr_existing = pd.read_csv(dwr_path)
    cyc_existing = pd.read_csv(cyc_path)

    # Build timestamp sets for ±90-minute window dedup
    # Strava API local times can differ from Apple Health export times by up to 1 hour
    # (timezone handling differences), so we use a generous 90-minute window
    wo_existing["_ts"]  = pd.to_datetime(wo_existing["startDate"], errors="coerce").astype("int64")
    dwr_existing["_ts"] = pd.to_datetime(dwr_existing["startDate"], errors="coerce").astype("int64")
    cyc_existing["_ts"] = pd.to_datetime(cyc_existing["startDate"], errors="coerce").astype("int64")
    _90min_ns = 90 * 60 * int(1e9)

    def _near_existing(ts_ns: int, existing_df: pd.DataFrame, wtype: Optional[str] = None) -> bool:
        """True if any row in existing_df starts within 90 min of ts_ns."""
        col = existing_df["_ts"].dropna()
        return bool((abs(col - ts_ns) < _90min_ns).any())

    wo_rows, dwr_rows, cyc_rows = [], [], []
    added = skipped = 0

    for act in activities:
        # Use local time to match existing Apple Health rows (no timezone suffix)
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
        workout_sub   = act.get("workout_type", 0)   # 0=regular,1=race,2=long,3=workout
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
            # Strava-enriched fields
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
        # Add new row to in-memory df so subsequent activities in this batch are checked against it
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
        # Align columns to whatever is currently in the file (handles old 9-col and new 20-col headers)
        existing_cols = pd.read_csv(workouts_path, nrows=0).columns.tolist()
        for col in existing_cols:
            if col not in wo_new.columns:
                wo_new[col] = np.nan
        # Add any new columns to the file header if missing
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


@app.get("/api/activities/list")
def activities_list(
    sport: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    sort_by: str = "startDate",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 50,
    search: Optional[str] = None,
):
    wo = _workouts().copy()
    wo["startDate"] = pd.to_datetime(wo["startDate"], errors="coerce")
    if start:
        wo = wo[wo["startDate"] >= pd.Timestamp(start)]
    if end:
        wo = wo[wo["startDate"] <= pd.Timestamp(end) + pd.Timedelta(days=1)]
    if sport and sport.lower() != "all":
        wo = wo[wo["workoutType"].str.contains(sport, case=False, na=False)]
    if search:
        mask = wo["activity_name"].fillna("").str.contains(search, case=False)
        wo = wo[mask]
    # Sort
    valid_cols = [c for c in [sort_by] if c in wo.columns]
    if valid_cols:
        wo = wo.sort_values(valid_cols[0], ascending=(sort_dir == "asc"))
    total = len(wo)
    wo = wo.iloc[(page - 1) * page_size: page * page_size]
    wo["startDate"] = wo["startDate"].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")

    import math as _math

    def safe(v):
        if v is None: return None
        try:
            f = float(v)
            return None if (_math.isnan(f) or _math.isinf(f)) else round(f, 4)
        except (TypeError, ValueError):
            s = str(v).strip()
            return s if s and s.lower() != "nan" else None

    records = []
    for _, r in wo.iterrows():
        pace_s = None
        dist = safe(r.get("distance"))
        dur  = safe(r.get("duration_min"))
        if dist and dur and dist > 0:
            pace_s = round(dur / dist, 4)
        trainer_raw = r.get("trainer")
        is_trainer = False if (trainer_raw is None or (isinstance(trainer_raw, float) and _math.isnan(trainer_raw))) else bool(trainer_raw)
        records.append({
            "date":        str(r["startDate"])[:10],
            "name":        safe(r.get("activity_name")) or "",
            "type":        safe(r.get("workoutType")) or "",
            "source":      safe(r.get("sourceName")) or "",
            "distance_km": dist,
            "duration_min":dur,
            "pace_min_km": pace_s,
            "avg_hr":      safe(r.get("avg_hr")),
            "max_hr":      safe(r.get("max_hr")),
            "elevation_m": safe(r.get("elevation_m")),
            "suffer_score":safe(r.get("suffer_score")),
            "avg_cadence": safe(r.get("avg_cadence")),
            "avg_watts":   safe(r.get("avg_watts")),
            "trainer":     is_trainer,
        })
    return {"total": total, "page": page, "page_size": page_size, "records": records}


@app.get("/api/training/hr_zones")
def training_hr_zones(
    start: Optional[str] = None,
    end: Optional[str] = None,
    hr_max: int = 185,
):
    """Return count of activities per HR zone per sport. Zones based on % of HRmax."""
    wo = _workouts().copy()
    wo["startDate"] = pd.to_datetime(wo["startDate"], errors="coerce")
    if start:
        wo = wo[wo["startDate"] >= pd.Timestamp(start)]
    if end:
        wo = wo[wo["startDate"] <= pd.Timestamp(end) + pd.Timedelta(days=1)]

    wo = wo[wo["avg_hr"].notna() & (wo["avg_hr"] > 0)]
    wo["avg_hr"] = pd.to_numeric(wo["avg_hr"], errors="coerce")
    wo = wo[wo["avg_hr"].notna()]

    zones = [
        {"zone": "Z1 Recovery",   "min_pct": 0,   "max_pct": 60},
        {"zone": "Z2 Aerobic",    "min_pct": 60,  "max_pct": 70},
        {"zone": "Z3 Tempo",      "min_pct": 70,  "max_pct": 80},
        {"zone": "Z4 Threshold",  "min_pct": 80,  "max_pct": 90},
        {"zone": "Z5 VO2Max",     "min_pct": 90,  "max_pct": 200},
    ]

    def assign_zone(hr):
        pct = (hr / hr_max) * 100
        for z in zones:
            if z["min_pct"] <= pct < z["max_pct"]:
                return z["zone"]
        return "Z5 VO2Max"

    wo["zone"] = wo["avg_hr"].apply(assign_zone)

    result = []
    for z in zones:
        zname = z["zone"]
        zdf = wo[wo["zone"] == zname]
        run = zdf[zdf["workoutType"].str.contains("Running", na=False)]
        cyc = zdf[zdf["workoutType"].str.contains("Cycling", na=False)]
        result.append({
            "zone": zname,
            "run_count":     int(len(run)),
            "cyc_count":     int(len(cyc)),
            "run_hours":     round(run["duration_min"].sum() / 60, 1) if len(run) else 0,
            "cyc_hours":     round(cyc["duration_min"].sum() / 60, 1) if len(cyc) else 0,
            "hr_min":        round(hr_max * z["min_pct"] / 100),
            "hr_max":        round(hr_max * z["max_pct"] / 100) if z["max_pct"] < 200 else hr_max,
        })
    return result


@app.get("/api/training/records")
def training_records(sport: str = "running"):
    wo = _workouts().copy()
    wo["startDate"] = pd.to_datetime(wo["startDate"], errors="coerce")
    wo["duration_min"] = pd.to_numeric(wo["duration_min"], errors="coerce")
    wo["distance"] = pd.to_numeric(wo["distance"], errors="coerce")
    wo["elevation_m"] = pd.to_numeric(wo["elevation_m"], errors="coerce")
    wo["avg_hr"] = pd.to_numeric(wo["avg_hr"], errors="coerce")

    if sport == "running":
        df = wo[wo["workoutType"].str.contains("Running", na=False)].copy()
    else:
        df = wo[wo["workoutType"].str.contains("Cycling", na=False)].copy()

    df = df[df["duration_min"] < 960]  # filter unstopped sessions

    if df.empty:
        return []

    records = []

    # Longest by distance
    if df["distance"].notna().any():
        row = df.loc[df["distance"].idxmax()]
        records.append({"type": "Longest distance", "value": round(float(row["distance"]), 1),
                        "unit": "km", "date": str(row["startDate"])[:10]})

    # Longest by duration
    if df["duration_min"].notna().any():
        row = df.loc[df["duration_min"].idxmax()]
        records.append({"type": "Longest duration", "value": round(float(row["duration_min"]) / 60, 2),
                        "unit": "h", "date": str(row["startDate"])[:10]})

    # Most elevation
    if df["elevation_m"].notna().any():
        row = df.loc[df["elevation_m"].idxmax()]
        records.append({"type": "Most elevation", "value": round(float(row["elevation_m"])),
                        "unit": "m", "date": str(row["startDate"])[:10]})

    # Best pace (lowest min/km) for runs, or best speed for cycling
    pace_df = df[(df["distance"] > 1) & (df["duration_min"].notna())]
    if not pace_df.empty:
        pace_df = pace_df.copy()
        pace_df["pace"] = pace_df["duration_min"] / pace_df["distance"]
        row = pace_df.loc[pace_df["pace"].idxmin()]
        if sport == "running":
            p = float(row["pace"])
            records.append({"type": "Best pace", "value": f"{int(p)}:{int((p%1)*60):02d}",
                            "unit": "/km", "date": str(row["startDate"])[:10]})
        else:
            spd = 60 / float(row["pace"])
            records.append({"type": "Best avg speed", "value": round(spd, 1),
                            "unit": "km/h", "date": str(row["startDate"])[:10]})

    # Lowest avg HR
    hr_df = df[df["avg_hr"].notna() & (df["avg_hr"] > 0) & (df["distance"] > 5)]
    if not hr_df.empty:
        row = hr_df.loc[hr_df["avg_hr"].idxmin()]
        records.append({"type": "Lowest avg HR", "value": int(row["avg_hr"]),
                        "unit": "bpm", "date": str(row["startDate"])[:10]})

    return records


# ─────────────────────────────────────────────────────────────────────────────
# Google Drive Integration
# ─────────────────────────────────────────────────────────────────────────────

GDRIVE_CONFIG_PATH   = Path(__file__).parent.parent / "gdrive_config.json"
GDRIVE_AUTH_URL      = "https://accounts.google.com/o/oauth2/v2/auth"
GDRIVE_TOKEN_URL     = "https://oauth2.googleapis.com/token"
GDRIVE_REDIRECT_URI  = "http://localhost:8000/api/gdrive/callback"
GDRIVE_SCOPES        = "https://www.googleapis.com/auth/drive.readonly"
GDRIVE_FILES_API     = "https://www.googleapis.com/drive/v3/files"

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
        raise ValueError("No refresh token — re-authorize Google Drive")
    r = httpx.post(GDRIVE_TOKEN_URL, data={
        "client_id":     cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "refresh_token": cfg["refresh_token"],
        "grant_type":    "refresh_token",
    })
    r.raise_for_status()
    data = r.json()
    cfg["access_token"]    = data["access_token"]
    cfg["token_expires_at"] = time.time() + data.get("expires_in", 3600)
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

def _ingest_hae_file(content: bytes) -> tuple[int, int]:
    """Parse a HAE (Health Auto Export JSON) file and insert into SQLite. Returns (added, skipped)."""
    import math as _math
    try:
        payload = json.loads(content)
    except Exception:
        return 0, 0

    # HAE can wrap in {"data": {...}} or be the object directly
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
        "oxygen_saturation":           "OxygenSaturation",
        "oxygenSaturation":            "OxygenSaturation",
        "lean_body_mass":              "LeanBodyMass",
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
            return None if (_math.isnan(f) or _math.isinf(f)) else f
        except: return None

    # ── Metrics ──────────────────────────────────────────────────────────────
    metric_rows = []
    sleep_rows  = []
    SLEEP_METRIC_NAMES = {"sleep_analysis", "sleepAnalysis", "SleepAnalysis"}

    for m in metrics_list:
        raw_name  = m.get("name", "")
        db_name   = HAE_METRIC_MAP.get(raw_name, raw_name)
        unit      = m.get("units", "")

        # Sleep analysis → HAE daily summary format: one entry per night with
        # numeric hours per stage: {sleepStart, rem, deep, core, awake, inBed}
        if raw_name in SLEEP_METRIC_NAMES or db_name == "SleepAnalysis":
            for entry in m.get("data", []):
                start_ts = safe_ts(entry.get("sleepStart") or entry.get("startDate") or entry.get("date"))
                if start_ts is None: continue
                src = str(entry.get("source", "HealthAutoExport") or "HealthAutoExport")
                # Use HAE's "date" field (wake-up date) as the night label, matching HAE/Garmin convention
                date_ts = safe_ts(entry.get("date"))
                if date_ts:
                    night = datetime.fromtimestamp(date_ts).strftime("%Y-%m-%d")
                else:
                    night = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d")
                # Map HAE field → stage name, value in hours
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
            continue  # don't also add to metric_rows

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

    # ── Workouts ─────────────────────────────────────────────────────────────
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

    # Clear caches so charts refresh
    _workouts.cache_clear()
    _by_type.cache_clear()
    _daily.cache_clear()

    return added, skipped

# ── G-Drive sync job state ────────────────────────────────────────────────────
_gdrive_sync_job: dict = {"status": "idle", "added": 0, "skipped": 0, "error": None, "files_processed": 0}

def _run_gdrive_sync():
    global _gdrive_sync_job
    _gdrive_sync_job = {"status": "running", "added": 0, "skipped": 0, "error": None, "files_processed": 0}
    try:
        cfg = _load_gdrive_config()
        cfg = _ensure_gdrive_token(cfg)
        headers = {"Authorization": f"Bearer {cfg['access_token']}"}

        # Use cached folder_id if available, otherwise resolve from path
        folder_id = cfg.get("folder_id") or _gdrive_folder_id(headers, cfg.get("folder_path", "Health Auto Export/HealthMetrics"))
        if not folder_id:
            _gdrive_sync_job["error"] = f"Folder '{cfg.get('folder_path')}' not found in Google Drive"
            _gdrive_sync_job["status"] = "error"
            return
        # Cache the resolved folder_id
        if not cfg.get("folder_id"):
            cfg["folder_id"] = folder_id
            _save_gdrive_config(cfg)

        # Get processed file IDs from SQLite
        conn = _db()
        processed = {r[0] for r in conn.execute("SELECT file_id FROM gdrive_files").fetchall()}

        # List all .hae files in folder
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

        # Log to sync_log
        conn.execute(
            "INSERT INTO sync_log(source,synced_at,added,skipped,note) VALUES(?,?,?,?,?)",
            ("gdrive", time.time(), total_added, total_skipped, f"{len(new_files)} files")
        )
        conn.commit()

        _gdrive_sync_job["status"] = "done"

    except Exception as e:
        _gdrive_sync_job["status"] = "error"
        _gdrive_sync_job["error"]  = str(e)


@app.get("/api/gdrive/status")
def gdrive_status():
    cfg = _load_gdrive_config()
    connected = bool(cfg.get("access_token") and cfg.get("refresh_token"))
    conn = _db()
    file_count = conn.execute("SELECT COUNT(*) FROM gdrive_files").fetchone()[0]
    last_sync  = conn.execute("SELECT MAX(processed_at) FROM gdrive_files").fetchone()[0]
    return {
        "connected":    connected,
        "file_count":   file_count,
        "last_sync":    last_sync,
        "folder_path":  cfg.get("folder_path"),
    }


@app.get("/api/gdrive/auth")
def gdrive_auth():
    cfg = _load_gdrive_config()
    params = {
        "client_id":     cfg["client_id"],
        "redirect_uri":  GDRIVE_REDIRECT_URI,
        "response_type": "code",
        "scope":         GDRIVE_SCOPES,
        "access_type":   "offline",
        "prompt":        "consent",
    }
    from urllib.parse import urlencode
    return RedirectResponse(f"{GDRIVE_AUTH_URL}?{urlencode(params)}")


@app.get("/api/gdrive/callback")
def gdrive_callback(code: str):
    cfg = _load_gdrive_config()
    r = httpx.post(GDRIVE_TOKEN_URL, data={
        "code":          code,
        "client_id":     cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uri":  GDRIVE_REDIRECT_URI,
        "grant_type":    "authorization_code",
    })
    r.raise_for_status()
    data = r.json()
    cfg["access_token"]     = data["access_token"]
    cfg["refresh_token"]    = data.get("refresh_token", cfg.get("refresh_token"))
    cfg["token_expires_at"] = time.time() + data.get("expires_in", 3600)
    _save_gdrive_config(cfg)
    return RedirectResponse("http://localhost:5173?gdrive=connected")


@app.post("/api/gdrive/sync")
def gdrive_sync(background_tasks: BackgroundTasks):
    if _gdrive_sync_job.get("status") == "running":
        return {"status": "already_running"}
    background_tasks.add_task(_run_gdrive_sync)
    return {"status": "started"}


@app.get("/api/gdrive/sync/status")
def gdrive_sync_status():
    return _gdrive_sync_job


@app.get("/api/strava/status")
def strava_status():
    cfg = _load_strava_config()
    connected = bool(cfg.get("access_token") and cfg.get("refresh_token"))
    return {
        "connected":    connected,
        "last_sync":    cfg.get("last_sync_timestamp"),
        "athlete_name": cfg.get("athlete_name"),
    }


@app.get("/api/strava/auth")
def strava_auth():
    cfg = _load_strava_config()
    if not cfg.get("client_id"):
        return {"error": "client_id not configured in strava_config.json"}
    params = (
        f"client_id={cfg['client_id']}"
        f"&redirect_uri={STRAVA_REDIRECT_URI}"
        f"&response_type=code"
        f"&approval_prompt=auto"
        f"&scope=activity:read_all"
    )
    return RedirectResponse(f"{STRAVA_AUTH_URL}?{params}")


@app.get("/api/strava/callback")
def strava_callback(code: str):
    cfg = _load_strava_config()
    resp = httpx.post(STRAVA_TOKEN_URL, data={
        "client_id":     cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "code":          code,
        "grant_type":    "authorization_code",
    })
    resp.raise_for_status()
    data = resp.json()
    cfg["access_token"]     = data["access_token"]
    cfg["refresh_token"]    = data["refresh_token"]
    cfg["token_expires_at"] = data["expires_at"]
    athlete = data.get("athlete", {})
    cfg["athlete_name"] = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
    _save_strava_config(cfg)
    return RedirectResponse("http://localhost:5173")


# In-memory sync job state
_sync_job: dict = {"status": "idle", "added": 0, "skipped": 0, "error": None}


def _run_sync_job(force: bool = False):
    global _sync_job
    _sync_job = {"status": "running", "added": 0, "skipped": 0, "error": None}
    try:
        cfg = _load_strava_config()
        cfg = _ensure_valid_token(cfg)

        # Force mode: wipe existing Strava rows so we re-import with enriched fields
        if force:
            workouts_path = DATA_DIR / "workouts.csv"
            dwr_path      = DATA_DIR / "by_type" / "DistanceWalkingRunning.csv"
            cyc_path      = DATA_DIR / "by_type" / "DistanceCycling.csv"
            # Remove Strava rows; expand workouts header to include new enriched columns
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

        _workouts.cache_clear()
        _running_dist_by_day.cache_clear()
        _cycling_dist_by_day.cache_clear()
        _pmc_df.cache_clear()
        _valid_metrics.cache_clear()

        _sync_job = {"status": "done", "added": added, "skipped": skipped, "error": None}
    except Exception as e:
        _sync_job = {"status": "error", "added": 0, "skipped": 0, "error": str(e)}


@app.post("/api/strava/sync")
def strava_sync(background_tasks: BackgroundTasks, force: bool = False):
    if _sync_job.get("status") == "running":
        return {"status": "running"}
    background_tasks.add_task(_run_sync_job, force=force)
    return {"status": "started"}


@app.get("/api/strava/sync/status")
def strava_sync_status():
    return _sync_job


@app.get("/api/training/strava_insights")
def training_strava_insights(
    resolution: str = "month",
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    """Strava-enriched metrics: elevation, avg HR, pace, suffer score, cadence."""
    wo = _workouts().copy()
    wo = wo[wo["sourceName"] == "Strava"].copy()

    wo["sport"] = "other"
    wo.loc[wo["workoutType"].str.contains("Running", na=False), "sport"] = "running"
    wo.loc[wo["workoutType"].str.contains("Cycling", na=False), "sport"] = "cycling"

    if start:
        wo = wo[wo["startDate"] >= start]
    if end:
        wo = wo[wo["startDate"] <= end]

    wo = wo[wo["duration_min"] <= 600]  # filter outliers
    wo["period"] = _period_col(wo["startDate"], resolution)

    for col in ["elevation_m", "avg_hr", "max_hr", "suffer_score",
                "avg_cadence", "avg_watts", "moving_time_min", "distance"]:
        if col in wo.columns:
            wo[col] = pd.to_numeric(wo[col], errors="coerce")

    # Pace (min/km) from moving_time / distance
    wo_run = wo[(wo["sport"] == "running") & (wo["distance"] > 0) & (wo["moving_time_min"] > 0)].copy()
    wo_run["pace_min_km"] = wo_run["moving_time_min"] / wo_run["distance"]

    def _agg(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
        if len(df) == 0:
            return pd.DataFrame()
        return df.groupby("period").agg(**{
            f"{prefix}_elevation_m": ("elevation_m", "sum"),
            f"{prefix}_avg_hr":      ("avg_hr",      "mean"),
            f"{prefix}_suffer":      ("suffer_score","sum"),
            f"{prefix}_avg_cadence": ("avg_cadence", "mean"),
            f"{prefix}_avg_watts":   ("avg_watts",   "mean"),
        }).round(1)

    run_agg  = _agg(wo[wo["sport"] == "running"], "run")
    cyc_agg  = _agg(wo[wo["sport"] == "cycling"], "cyc")
    pace_agg = wo_run.groupby("period").agg(run_avg_pace=("pace_min_km", "mean")).round(2) if len(wo_run) > 0 else pd.DataFrame()

    all_periods = sorted(set(run_agg.index) | set(cyc_agg.index) | set(pace_agg.index))
    if not all_periods:
        return []

    result = pd.DataFrame({"period": pd.Series(all_periods, dtype="object")})
    for part in [run_agg, cyc_agg, pace_agg]:
        if len(part) > 0:
            result = result.merge(part.reset_index(), on="period", how="left")
    result = result.fillna(0)
    return to_records(result)


# ─── Apple Health Auto Export ingest ─────────────────────────────────────────

# How each daily_summary column is built from a by_type CSV:  col_name → (csv_name, agg)
_DAILY_AGG: dict[str, tuple[str, str]] = {
    "ActiveEnergyBurned":            ("ActiveEnergyBurned",            "sum"),
    "AppleExerciseTime":             ("AppleExerciseTime",             "sum"),
    "AppleStandTime":                ("AppleStandTime",                "sum"),
    "AppleWalkingSteadiness":        ("AppleWalkingSteadiness",        "mean"),
    "BasalBodyTemperature":          ("BasalBodyTemperature",          "mean"),
    "BasalEnergyBurned":             ("BasalEnergyBurned",             "sum"),
    "BloodGlucose_mean":             ("BloodGlucose",                  "mean"),
    "BloodGlucose_min":              ("BloodGlucose",                  "min"),
    "BloodGlucose_max":              ("BloodGlucose",                  "max"),
    "BloodPressureDiastolic_mean":   ("BloodPressureDiastolic",        "mean"),
    "BloodPressureDiastolic_min":    ("BloodPressureDiastolic",        "min"),
    "BloodPressureDiastolic_max":    ("BloodPressureDiastolic",        "max"),
    "BloodPressureSystolic_mean":    ("BloodPressureSystolic",         "mean"),
    "BloodPressureSystolic_min":     ("BloodPressureSystolic",         "min"),
    "BloodPressureSystolic_max":     ("BloodPressureSystolic",         "max"),
    "BodyFatPercentage":             ("BodyFatPercentage",             "last"),
    "BodyMass":                      ("BodyMass",                      "last"),
    "BodyMassIndex":                 ("BodyMassIndex",                 "last"),
    "DietaryWater":                  ("DietaryWater",                  "sum"),
    "DistanceCycling":               ("DistanceCycling",               "sum"),
    "DistanceWalkingRunning":        ("DistanceWalkingRunning",        "sum"),
    "EnvironmentalAudioExposure":    ("EnvironmentalAudioExposure",    "mean"),
    "FlightsClimbed":                ("FlightsClimbed",                "sum"),
    "HeadphoneAudioExposure":        ("HeadphoneAudioExposure",        "mean"),
    "HeartRate_mean":                ("HeartRate",                     "mean"),
    "HeartRate_min":                 ("HeartRate",                     "min"),
    "HeartRate_max":                 ("HeartRate",                     "max"),
    "HeartRateVariabilitySDNN":      ("HeartRateVariabilitySDNN",      "mean"),
    "Height":                        ("Height",                        "last"),
    "LeanBodyMass":                  ("LeanBodyMass",                  "last"),
    "OxygenSaturation":              ("OxygenSaturation",              "mean"),
    "RespiratoryRate":               ("RespiratoryRate",               "mean"),
    "RestingHeartRate":              ("RestingHeartRate",              "mean"),
    "SixMinuteWalkTestDistance":     ("SixMinuteWalkTestDistance",     "last"),
    "SleepDurationGoal":             ("SleepDurationGoal",             "last"),
    "StepCount":                     ("StepCount",                     "sum"),
    "VO2Max":                        ("VO2Max",                        "mean"),
    "WalkingAsymmetryPercentage":    ("WalkingAsymmetryPercentage",    "mean"),
    "WalkingDoubleSupportPercentage":("WalkingDoubleSupportPercentage","mean"),
    "WalkingHeartRateAverage":       ("WalkingHeartRateAverage",       "mean"),
    "WalkingSpeed":                  ("WalkingSpeed",                  "mean"),
    "WalkingStepLength":             ("WalkingStepLength",             "mean"),
}


def _rebuild_daily_for_dates(new_dates: set) -> None:
    """Recompute daily_summary.csv rows for the given dates from by_type CSVs."""
    if not new_dates:
        return

    ds_path = DATA_DIR / "daily_summary.csv"
    ds = pd.read_csv(ds_path, parse_dates=["date"]) if ds_path.exists() else pd.DataFrame(columns=["date"])

    rows_by_date: dict = {d: {} for d in new_dates}

    for col_name, (csv_name, agg_fn) in _DAILY_AGG.items():
        csv_path = DATA_DIR / "by_type" / f"{csv_name}.csv"
        if not csv_path.exists():
            continue
        try:
            df = pd.read_csv(csv_path, usecols=["startDate", "value_num"], parse_dates=["startDate"])
        except Exception:
            continue
        df["_date"] = df["startDate"].dt.date
        df = df[df["_date"].isin(new_dates) & df["value_num"].notna()]
        if df.empty:
            continue

        if agg_fn == "sum":
            agg = df.groupby("_date")["value_num"].sum()
        elif agg_fn == "mean":
            agg = df.groupby("_date")["value_num"].mean()
        elif agg_fn == "min":
            agg = df.groupby("_date")["value_num"].min()
        elif agg_fn == "max":
            agg = df.groupby("_date")["value_num"].max()
        else:  # last
            agg = df.sort_values("startDate").groupby("_date")["value_num"].last()

        for date, val in agg.items():
            rows_by_date[date][col_name] = val

    new_rows = [{"date": pd.Timestamp(d), **vals} for d, vals in rows_by_date.items() if vals]
    if not new_rows:
        return

    new_df = pd.DataFrame(new_rows)
    if not ds.empty and "date" in ds.columns:
        ds = ds[~ds["date"].isin(new_df["date"])]
    ds = pd.concat([ds, new_df], ignore_index=True).sort_values("date")
    ds["date"] = ds["date"].dt.strftime("%Y-%m-%d")
    ds.to_csv(ds_path, index=False)
    _daily.cache_clear()


# Maps Health Auto Export metric names → our by_type CSV filenames
HEALTH_METRIC_MAP: dict[str, str] = {
    "active_energy":                  "ActiveEnergyBurned",
    "step_count":                     "StepCount",
    "heart_rate":                     "HeartRate",
    "resting_heart_rate":             "RestingHeartRate",
    "heart_rate_variability_sdnn":    "HeartRateVariabilitySDNN",
    "body_mass":                      "BodyMass",
    "body_fat_percentage":            "BodyFatPercentage",
    "body_mass_index":                "BodyMassIndex",
    "blood_glucose":                  "BloodGlucose",
    "blood_pressure_systolic":        "BloodPressureSystolic",
    "blood_pressure_diastolic":       "BloodPressureDiastolic",
    "walking_running_distance":       "DistanceWalkingRunning",
    "cycling_distance":               "DistanceCycling",
    "vo2_max":                        "VO2Max",
    "walking_speed":                  "WalkingSpeed",
    "respiratory_rate":               "RespiratoryRate",
    "oxygen_saturation":              "OxygenSaturation",
    "basal_energy_burned":            "BasalEnergyBurned",
    "flights_climbed":                "FlightsClimbed",
    "walking_heart_rate_average":     "WalkingHeartRateAverage",
}

# Caches that must be cleared after an ingest
_CACHES_TO_CLEAR = [
    "_daily", "_workouts", "_running_dist_by_day", "_cycling_dist_by_day",
    "_pmc_df", "_valid_metrics", "_sleep",
]


def _load_ingest_config() -> dict:
    if not HEALTH_INGEST_CONFIG.exists():
        return {"last_ingest": None, "total_added": 0}
    with open(HEALTH_INGEST_CONFIG) as f:
        return json.load(f)


def _save_ingest_config(cfg: dict) -> None:
    with open(HEALTH_INGEST_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)


def _parse_hae_date(s: str) -> str:
    """Parse Health Auto Export date string → 'YYYY-MM-DD HH:MM:SS' (local time)."""
    # Format: "2024-01-15 07:30:00 -0500"
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            # Store as naive local-time string (consistent with existing CSVs)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return s.strip()


def _ingest_metrics(metrics: list[dict]) -> tuple[int, int, set]:
    """Append new metric rows from Health Auto Export payload. Returns (added, skipped, new_dates)."""
    added = skipped = 0
    new_dates: set = set()

    unmapped_names: list[str] = []
    for metric in metrics:
        raw_name = metric.get("name", "")
        csv_name = HEALTH_METRIC_MAP.get(raw_name)
        if csv_name is None:
            unmapped_names.append(raw_name)
            continue  # unmapped metric — skip

        unit = metric.get("units", "")
        rows = metric.get("data", [])
        if not rows:
            continue

        csv_path = DATA_DIR / "by_type" / f"{csv_name}.csv"

        # Load existing timestamps for dedup (±90 s window)
        if csv_path.exists():
            existing = pd.read_csv(csv_path, usecols=["startDate"])
            existing_ts = pd.to_datetime(existing["startDate"], errors="coerce").dropna()
            existing_ns = existing_ts.astype("int64").values
        else:
            existing_ns = []

        _90s_ns = 90 * int(1e9)

        new_rows = []
        for row in rows:
            raw_date = row.get("date") or row.get("startDate", "")
            start_str = _parse_hae_date(raw_date)
            try:
                ts_ns = int(pd.Timestamp(start_str).value)
            except Exception:
                skipped += 1
                continue

            # Dedup: skip if a record within ±90 s already exists
            _ns_arr = np.asarray(existing_ns, dtype="int64")
            if len(_ns_arr) and bool((np.abs(_ns_arr - ts_ns) < _90s_ns).any()):
                skipped += 1
                continue

            # Value: Health Auto Export uses "qty" for simple metrics,
            # "Avg"/"Min"/"Max" for aggregated (heart rate, etc.)
            value = row.get("qty") or row.get("Avg") or row.get("value")
            if value is None:
                skipped += 1
                continue

            source = row.get("source", "Health Auto Export")
            new_rows.append({
                "startDate": start_str,
                "endDate":   start_str,
                "value_num": float(value),
                "unit":      unit,
                "sourceName": source,
                "device":    "",
            })
            new_dates.add(pd.Timestamp(start_str).date())
            # Add to in-memory existing set to prevent intra-batch dups
            existing_ns = list(existing_ns) + [ts_ns]

        if not new_rows:
            continue

        df_new = pd.DataFrame(new_rows)
        if csv_path.exists():
            df_new.to_csv(csv_path, mode="a", header=False, index=False)
        else:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            df_new.to_csv(csv_path, index=False)
        added += len(new_rows)

    if unmapped_names:
        print(f"[ingest] unmapped metric names: {sorted(set(unmapped_names))}", flush=True)
    return added, skipped, new_dates


def _ingest_workouts(workouts: list[dict]) -> tuple[int, int]:
    """Append new workout rows from Health Auto Export payload. Returns (added, skipped)."""
    if not workouts:
        return 0, 0

    wo_path = DATA_DIR / "workouts.csv"
    wo_existing = pd.read_csv(wo_path) if wo_path.exists() else pd.DataFrame()

    if not wo_existing.empty and "startDate" in wo_existing.columns:
        existing_ts = pd.to_datetime(wo_existing["startDate"], errors="coerce").dropna()
        existing_ns = existing_ts.astype("int64").values
    else:
        existing_ns = []

    _90min_ns = 90 * 60 * int(1e9)

    WORKOUT_TYPE_MAP = {
        "Running":        "Running",
        "Cycling":        "Cycling",
        "Walking":        "Walking",
        "Swimming":       "Swimming",
        "Hiking":         "Hiking",
        "Yoga":           "Yoga",
        "Strength Training": "FunctionalStrengthTraining",
        "HIIT":           "HighIntensityIntervalTraining",
        "Rowing":         "Rowing",
        "Elliptical":     "Elliptical",
    }

    added = skipped = 0
    new_rows = []

    for w in workouts:
        raw_start = w.get("start", "")
        start_str = _parse_hae_date(raw_start) if raw_start else ""
        if not start_str:
            skipped += 1
            continue

        try:
            ts_ns = int(pd.Timestamp(start_str).value)
        except Exception:
            skipped += 1
            continue

        if len(existing_ns) and bool((abs(existing_ns - ts_ns) < _90min_ns).any()):
            skipped += 1
            continue

        raw_end = w.get("end", raw_start)
        end_str = _parse_hae_date(raw_end) if raw_end else start_str
        workout_name = w.get("name", "")
        workout_type = WORKOUT_TYPE_MAP.get(workout_name, workout_name)
        duration_min = w.get("duration")        # Health Auto Export sends minutes
        distance    = w.get("distance")
        dist_unit   = w.get("distance_unit", "km")
        energy      = w.get("active_energy") or w.get("activeEnergyBurned")

        new_rows.append({
            "workoutType":       workout_type,
            "duration_min":      round(float(duration_min), 4) if duration_min else None,
            "distance":          round(float(distance), 4) if distance else None,
            "distanceUnit":      dist_unit,
            "activeEnergy_kcal": round(float(energy), 2) if energy else None,
            "sourceName":        "Health Auto Export",
            "startDate":         start_str,
            "endDate":           end_str,
            "device":            "",
        })
        existing_ns = list(existing_ns) + [ts_ns]

    if not new_rows:
        return 0, skipped

    df_new = pd.DataFrame(new_rows)
    if wo_path.exists():
        df_new.to_csv(wo_path, mode="a", header=False, index=False)
    else:
        df_new.to_csv(wo_path, index=False)

    return len(new_rows), skipped


# ─── Google Drive integration ──────────────────────────────────────────────────

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


@app.get("/api/health/status")
def health_ingest_status():
    cfg = _load_ingest_config()
    # Get local IP for displaying the webhook URL to the user
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "localhost"
    return {
        "last_ingest":  cfg.get("last_ingest"),
        "total_added":  cfg.get("total_added", 0),
        "webhook_url":  f"http://{local_ip}:8000/api/health/ingest",
    }


@app.post("/api/health/ingest")
def health_ingest(payload: dict):
    """
    Receives data pushed by the Health Auto Export iOS app.
    Expected payload: {"data": {"metrics": [...], "workouts": [...]}}
    """
    data = payload.get("data") or payload  # handle both wrapped and flat payloads
    metrics  = data.get("metrics", [])
    workouts = data.get("workouts", [])

    added_m, skipped_m, new_dates = _ingest_metrics(metrics)
    added_w, skipped_w            = _ingest_workouts(workouts)
    added   = added_m + added_w
    skipped = skipped_m + skipped_w

    # Rebuild daily_summary rows for any newly-ingested dates
    if new_dates:
        _rebuild_daily_for_dates(new_dates)

    # Clear all caches so next request re-reads updated CSVs
    for fn_name in _CACHES_TO_CLEAR:
        fn = globals().get(fn_name)
        if fn and hasattr(fn, "cache_clear"):
            fn.cache_clear()

    cfg = _load_ingest_config()
    cfg["last_ingest"]  = int(time.time())
    cfg["total_added"]  = cfg.get("total_added", 0) + added
    _save_ingest_config(cfg)

    return {"added": added, "skipped": skipped}


@app.post("/api/health/upload")
async def health_upload(file: UploadFile = File(...)):
    """
    Accept .hae or .json file uploads from Health Auto Export (iCloud Drive).
    HAE files are plain JSON with the same structure as the REST API payload.
    """
    content = await file.read()

    # Try plain JSON first, then gzip-compressed JSON
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        try:
            import gzip
            payload = json.loads(gzip.decompress(content))
        except Exception:
            raise HTTPException(status_code=400, detail="Could not parse file — expected JSON or gzip-compressed JSON (.hae)")

    data     = payload.get("data") or payload
    metrics  = data.get("metrics", [])
    workouts = data.get("workouts", [])

    if not metrics and not workouts:
        raise HTTPException(status_code=400, detail="No metrics or workouts found in file")

    added_m, skipped_m, new_dates = _ingest_metrics(metrics)
    added_w, skipped_w            = _ingest_workouts(workouts)
    added   = added_m + added_w
    skipped = skipped_m + skipped_w

    if new_dates:
        _rebuild_daily_for_dates(new_dates)

    for fn_name in _CACHES_TO_CLEAR:
        fn = globals().get(fn_name)
        if fn and hasattr(fn, "cache_clear"):
            fn.cache_clear()

    cfg = _load_ingest_config()
    cfg["last_ingest"] = int(time.time())
    cfg["total_added"] = cfg.get("total_added", 0) + added
    _save_ingest_config(cfg)

    return {"added": added, "skipped": skipped, "filename": file.filename}


# ─── Biomarkers ───────────────────────────────────────────────────────────────

def _ensure_biomarker_tables():
    """Create biomarker tables if they don't exist."""
    conn = _db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS biomarker_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            upload_ts INTEGER,
            test_date TEXT,
            lab_name TEXT,
            records_extracted INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS biomarkers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER REFERENCES biomarker_uploads(id) ON DELETE CASCADE,
            test_date TEXT,
            marker_name TEXT,
            marker_canonical TEXT,
            value REAL,
            unit TEXT,
            ref_min REAL,
            ref_max REAL,
            category TEXT,
            status TEXT,
            UNIQUE(upload_id, marker_canonical)
        );
        CREATE INDEX IF NOT EXISTS idx_bio_marker ON biomarkers(marker_canonical);
        CREATE INDEX IF NOT EXISTS idx_bio_date ON biomarkers(test_date);
    """)
    conn.commit()

_ensure_biomarker_tables()


BIOMARKER_CATEGORIES = {
    "hematology": ["hemoglobin", "hematocrit", "red blood cells", "rbc", "wbc", "white blood cells",
                   "platelets", "mcv", "mch", "mchc", "rdw", "neutrophils", "lymphocytes",
                   "monocytes", "eosinophils", "basophils", "leucocite", "eritrocite", "trombocite",
                   "hemoglobina", "hematocrit"],
    "cardiovascular": ["cholesterol", "hdl", "ldl", "triglycerides", "vldl", "non-hdl",
                       "colesterol", "trigliceride"],
    "glucose_metabolism": ["glucose", "hba1c", "insulin", "glicemie", "glucoza"],
    "liver": ["alt", "ast", "ggt", "alkaline phosphatase", "bilirubin", "albumin", "total protein",
              "alat", "asat", "bilirubina", "albumina", "proteine"],
    "kidney": ["creatinine", "urea", "bun", "uric acid", "egfr", "creatinina", "acid uric"],
    "thyroid": ["tsh", "t3", "t4", "free t3", "free t4", "ft3", "ft4"],
    "inflammation": ["crp", "esr", "fibrinogen", "ferritin", "il-6", "tnf",
                     "proteina c reactiva", "vsh"],
    "vitamins_minerals": ["vitamin d", "vitamin b12", "folate", "iron", "transferrin", "tibc",
                          "zinc", "magnesium", "vitamina d", "vitamina b12", "fier", "feritina"],
    "hormones": ["testosterone", "estradiol", "progesterone", "cortisol", "dhea", "lh", "fsh",
                 "prolactin", "testosteron"],
    "performance": ["ck", "ck-mb", "ldh", "creatine kinase", "lactate", "vo2max"],
    "coagulation": ["pt", "aptt", "inr", "fibrinogen", "d-dimer"],
    "urine": ["glucose_urine", "protein_urine", "ph_urine", "leukocytes_urine", "blood_urine"],
}

def _categorize_marker(name: str) -> str:
    name_lower = name.lower()
    for cat, keywords in BIOMARKER_CATEGORIES.items():
        if any(kw in name_lower for kw in keywords):
            return cat
    return "other"


BIOMARKERS_CONFIG_PATH = Path(__file__).parent.parent / "biomarkers_config.json"

def _load_biomarkers_config() -> dict:
    if BIOMARKERS_CONFIG_PATH.exists():
        with open(BIOMARKERS_CONFIG_PATH) as f:
            return json.load(f)
    return {}


def _extract_biomarkers_via_claude(pdf_bytes: bytes) -> dict:
    """Extract biomarkers from a PDF using Claude API."""
    import anthropic
    from pypdf import PdfReader

    # Resolve API key: env var takes precedence, then config file
    api_key = os.environ.get("ANTHROPIC_API_KEY") or _load_biomarkers_config().get("anthropic_api_key")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Anthropic API key not configured. Set ANTHROPIC_API_KEY env var or add 'anthropic_api_key' to health_app/biomarkers_config.json"
        )

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    if len(pdf_text.strip()) < 50:
        raise HTTPException(status_code=400, detail="Could not extract text from PDF")

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are a medical data extraction assistant. Extract all laboratory test results from the following blood work / lab report text.

Return a JSON object with this exact structure:
{{
  "test_date": "YYYY-MM-DD or null if not found",
  "lab_name": "name of the laboratory or null",
  "markers": [
    {{
      "name": "original marker name as in the report",
      "canonical": "standardized English name (e.g. Hemoglobin, LDL Cholesterol, TSH, Vitamin D)",
      "value": numeric_value_as_float,
      "unit": "unit string",
      "ref_min": numeric_min_reference_value_or_null,
      "ref_max": numeric_max_reference_value_or_null,
      "status": "low" or "normal" or "high" or "critical_low" or "critical_high"
    }}
  ]
}}

Rules:
- Extract EVERY numeric lab value you find, including urine and special tests
- For values with only an upper limit (e.g. "< 5.0"), set ref_min to null and ref_max to the limit
- For values with only a lower limit (e.g. "> 1.0"), set ref_min to the limit and ref_max to null
- Convert all numeric values to floats (e.g. "13,5" becomes 13.5, comma is decimal separator in Romanian)
- status is relative to the reference range provided in the report
- If the date is in Romanian/European format like "09.12.2025" convert to "2025-12-09"
- Do not include qualitative/text-only results (like culture results) unless they have a numeric value
- Return ONLY valid JSON with no explanation text outside the JSON

Lab report text:
---
{pdf_text[:8000]}
---"""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Claude returned invalid JSON: {e}")


@app.post("/api/biomarkers/upload")
async def biomarkers_upload(file: UploadFile = File(...)):
    """Upload a lab report PDF; returns extracted biomarkers for user review."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    pdf_bytes = await file.read()
    extracted = _extract_biomarkers_via_claude(pdf_bytes)

    for m in extracted.get("markers", []):
        m["category"] = _categorize_marker(m.get("canonical") or m.get("name", ""))

    return {
        "filename": file.filename,
        "test_date": extracted.get("test_date"),
        "lab_name": extracted.get("lab_name"),
        "markers": extracted.get("markers", []),
        "count": len(extracted.get("markers", [])),
    }


@app.post("/api/biomarkers/confirm")
async def biomarkers_confirm(payload: dict):
    """Save confirmed extracted biomarkers to the database."""
    _ensure_biomarker_tables()
    conn = _db()

    filename  = payload.get("filename", "unknown.pdf")
    test_date = payload.get("test_date")
    lab_name  = payload.get("lab_name")
    markers   = payload.get("markers", [])

    if not markers:
        raise HTTPException(status_code=400, detail="No markers to save")

    cur = conn.execute(
        "INSERT INTO biomarker_uploads (filename, upload_ts, test_date, lab_name, records_extracted) VALUES (?,?,?,?,?)",
        (filename, int(time.time()), test_date, lab_name, len(markers))
    )
    upload_id = cur.lastrowid

    inserted = 0
    for m in markers:
        try:
            val = m.get("value")
            if val is None:
                continue
            conn.execute(
                """INSERT OR REPLACE INTO biomarkers
                   (upload_id, test_date, marker_name, marker_canonical, value, unit,
                    ref_min, ref_max, category, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    upload_id, test_date,
                    m.get("name"), m.get("canonical") or m.get("name"),
                    float(val),
                    m.get("unit", ""),
                    m.get("ref_min"), m.get("ref_max"),
                    m.get("category", "other"),
                    m.get("status", "normal"),
                )
            )
            inserted += 1
        except Exception:
            pass

    conn.commit()
    return {"upload_id": upload_id, "saved": inserted}


@app.get("/api/biomarkers/uploads")
def biomarkers_uploads():
    """List all uploaded lab reports."""
    _ensure_biomarker_tables()
    rows = _db().execute(
        "SELECT id, filename, upload_ts, test_date, lab_name, records_extracted FROM biomarker_uploads ORDER BY test_date DESC, upload_ts DESC"
    ).fetchall()
    return [dict(r) for r in rows]


@app.delete("/api/biomarkers/uploads/{upload_id}")
def biomarkers_delete_upload(upload_id: int):
    """Delete an upload and all its markers."""
    _ensure_biomarker_tables()
    conn = _db()
    conn.execute("DELETE FROM biomarkers WHERE upload_id = ?", (upload_id,))
    conn.execute("DELETE FROM biomarker_uploads WHERE id = ?", (upload_id,))
    conn.commit()
    return {"deleted": upload_id}


@app.get("/api/biomarkers/trends")
def biomarkers_trends(marker: Optional[str] = None):
    """
    Return all biomarker readings for trend charts.
    If `marker` is specified, return that canonical marker over time.
    Otherwise return latest value per marker across all uploads.
    """
    _ensure_biomarker_tables()
    conn = _db()

    if marker:
        rows = conn.execute(
            """SELECT b.test_date, b.marker_name, b.marker_canonical, b.value, b.unit,
                      b.ref_min, b.ref_max, b.category, b.status, u.lab_name, u.filename
               FROM biomarkers b JOIN biomarker_uploads u ON b.upload_id = u.id
               WHERE b.marker_canonical = ?
               ORDER BY b.test_date""",
            (marker,)
        ).fetchall()
        return [dict(r) for r in rows]

    rows = conn.execute(
        """SELECT b.marker_canonical, b.marker_name, b.value, b.unit,
                  b.ref_min, b.ref_max, b.category, b.status, b.test_date, u.lab_name
           FROM biomarkers b JOIN biomarker_uploads u ON b.upload_id = u.id
           WHERE b.rowid IN (
               SELECT b2.rowid FROM biomarkers b2
               WHERE b2.marker_canonical = b.marker_canonical
               ORDER BY b2.test_date DESC LIMIT 1
           )
           ORDER BY b.category, b.marker_canonical"""
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/biomarkers/all")
def biomarkers_all():
    """Return every biomarker reading from every upload for trend charts."""
    _ensure_biomarker_tables()
    rows = _db().execute(
        """SELECT b.test_date, b.marker_canonical, b.marker_name, b.value, b.unit,
                  b.ref_min, b.ref_max, b.category, b.status, b.upload_id, u.lab_name
           FROM biomarkers b JOIN biomarker_uploads u ON b.upload_id = u.id
           ORDER BY b.marker_canonical, b.test_date"""
    ).fetchall()
    return [dict(r) for r in rows]
