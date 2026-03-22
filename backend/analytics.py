"""
Analytics helper functions — cached loaders and pure-compute utilities.
"""
import math
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from db import _db

DATA_DIR = Path(__file__).parent.parent.parent / "health_csvs" / "cleaned"

STRAVA_EXTRA_COLS = [
    "moving_time_min", "elevation_m", "avg_hr", "max_hr",
    "suffer_score", "avg_cadence", "avg_watts", "avg_speed_kmh",
    "activity_name", "workout_subtype", "trainer",
]


# ─── pure-compute utilities ───────────────────────────────────────────────────

def date_filter(df: pd.DataFrame, col: str, start: Optional[str], end: Optional[str]) -> pd.DataFrame:
    if start:
        df = df[df[col] >= start]
    if end:
        df = df[df[col] <= end]
    return df


def to_records(df: pd.DataFrame) -> list:
    rows = df.to_dict(orient="records")
    clean = []
    for row in rows:
        clean.append({
            k: (None if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else v)
            for k, v in row.items()
        })
    return clean


def _period_col(series: pd.Series, resolution: str) -> pd.Series:
    """Return a sortable period-start string for each timestamp."""
    if resolution == "week":
        return series.dt.to_period("W").dt.start_time.dt.strftime("%Y-%m-%d")
    if resolution == "month":
        return series.dt.to_period("M").dt.start_time.dt.strftime("%Y-%m")
    return series.dt.year.astype(str)


# ─── cached loaders ──────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _daily() -> pd.DataFrame:
    """Compute daily summary from SQLite metrics table."""
    conn = _db()
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
        "VO2MaxCycling":                "AVG",
        "BloodGlucose":                 "AVG",
        "DistanceWalkingRunning":       "SUM",
        "DistanceCycling":              "SUM",
        "FlightsClimbed":               "SUM",
        "AppleExerciseTime":            "SUM",
        "MindfulSession":               "SUM",
        "WalkingHeartRateAverage":      "AVG",
        "BloodPressureSystolic":        "AVG",
        "BloodPressureDiastolic":       "AVG",
    }
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

    # HeartRate mean / min / max (individual readings — 3 aggs on same metric)
    for suffix, agg in [("mean", "AVG"), ("min", "MIN"), ("max", "MAX")]:
        q = f"""
            SELECT date(datetime(start_ts, 'unixepoch')) AS day,
                   {agg}(value) AS val
            FROM metrics
            WHERE metric_name = 'HeartRate'
            GROUP BY day
        """
        tmp = pd.read_sql_query(q, conn)
        tmp.columns = ["date", f"HeartRate_{suffix}"]
        df = df.merge(tmp, on="date", how="left")

    # Per-source HRV: Garmin (overnight) vs Apple Health / Elite HRV (all non-Garmin)
    q_garmin = """
        SELECT date(datetime(start_ts, 'unixepoch')) AS day, AVG(value) AS val
        FROM metrics
        WHERE metric_name = 'HeartRateVariabilitySDNN' AND source = 'Garmin'
        GROUP BY day
    """
    q_apple = """
        SELECT date(datetime(start_ts, 'unixepoch')) AS day, AVG(value) AS val
        FROM metrics
        WHERE metric_name = 'HeartRateVariabilitySDNN'
          AND (source != 'Garmin' OR source IS NULL OR source = '')
        GROUP BY day
    """
    for q, col in [(q_garmin, "HRV_Garmin"), (q_apple, "HRV_Apple")]:
        tmp = pd.read_sql_query(q, conn)
        tmp.columns = ["date", col]
        df = df.merge(tmp, on="date", how="left")

    df["date"] = pd.to_datetime(df["date"])
    return df


@lru_cache(maxsize=1)
def _sleep() -> pd.DataFrame:
    """Build nightly sleep summary from SQLite sleep table (stage rows)."""
    conn = _db()
    # AVG across sources deduplicates nights recorded by both Connect and Garmin
    df = pd.read_sql_query(
        """SELECT date, stage, AVG(duration_min) AS duration_min
           FROM sleep
           WHERE stage IN ('Core','Deep','REM','Awake','InBed','Unspecified')
           GROUP BY date, stage""",
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
    pivot["total_sleep_hours"] = pivot[["Core", "Deep", "REM"]].sum(axis=1)
    mask = pivot["total_sleep_hours"] == 0
    pivot.loc[mask, "total_sleep_hours"] = pivot.loc[mask, ["InBed", "Unspecified"]].max(axis=1)
    return pivot.sort_values("night")


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


@lru_cache(maxsize=1)
def _valid_metrics() -> list:
    """Return only metrics that have >= 10 valid numeric rows."""
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


@lru_cache(maxsize=1)
def _running_dist_by_day() -> pd.Series:
    """
    Daily running distance (km).
    Primary source: workouts.distance_km (Strava / Garmin — always populated).
    Supplement: DistanceWalkingRunning metric records for Apple Health workouts
    that have NULL distance_km in the workouts table.
    """
    wo = _workouts()
    all_runs = wo[wo["workoutType"].str.contains("Running", na=False)].copy()
    all_runs = all_runs[all_runs["duration_min"] <= 600]

    # Part 1 — distance already in workouts table (column aliased as "distance")
    wo_dist = (
        all_runs[all_runs["distance"].notna()]
        .assign(date=lambda d: d["startDate"].dt.normalize())
        .groupby("date")["distance"]
        .sum()
        .rename("running_km")
    )

    # Part 2 — Apple Health metric records for workouts that lack distance
    ah_runs = all_runs[all_runs["distance"].isna()]
    if ah_runs.empty:
        return wo_dist if not wo_dist.empty else pd.Series(dtype=float, name="running_km")

    try:
        dwr = _by_type("DistanceWalkingRunning").copy()
    except FileNotFoundError:
        return wo_dist if not wo_dist.empty else pd.Series(dtype=float, name="running_km")

    if dwr.empty:
        return wo_dist if not wo_dist.empty else pd.Series(dtype=float, name="running_km")

    if "unit" in dwr.columns and (dwr["unit"] == "mi").any():
        dwr.loc[dwr["unit"] == "mi", "value_num"] *= 1.60934

    dwr["date"] = dwr["startDate"].dt.normalize()
    runs_sorted = ah_runs[["startDate", "endDate"]].rename(
        columns={"startDate": "run_start", "endDate": "run_end"}
    ).sort_values("run_start").reset_index(drop=True)

    merged = pd.merge_asof(
        dwr.sort_values("startDate")[["startDate", "date", "value_num"]].reset_index(drop=True),
        runs_sorted,
        left_on="startDate", right_on="run_start", direction="backward",
    )
    in_run = merged[merged["startDate"] < merged["run_end"]]
    ah_dist = in_run.groupby("date")["value_num"].sum().rename("running_km")

    combined = pd.concat([wo_dist, ah_dist]).groupby(level=0).sum()
    return combined.rename("running_km")


@lru_cache(maxsize=1)
def _cycling_dist_by_day() -> pd.Series:
    """
    Daily cycling distance (km).
    Primary source: workouts.distance_km (Strava / Garmin — covers ALL cycling
    subtypes: Ride, MountainBikeRide, GravelRide, VirtualRide, etc.).
    Supplement: DistanceCycling metric records for Apple Health workouts that
    have NULL distance_km in the workouts table.
    """
    wo = _workouts()
    all_rides = wo[wo["workoutType"].str.contains("Cycling", na=False)].copy()
    all_rides = all_rides[all_rides["duration_min"] <= 600]

    # Part 1 — distance already in workouts table (column aliased as "distance")
    wo_dist = (
        all_rides[all_rides["distance"].notna()]
        .assign(date=lambda d: d["startDate"].dt.normalize())
        .groupby("date")["distance"]
        .sum()
        .rename("cycling_km")
    )

    # Part 2 — Apple Health metric records for workouts that lack distance
    ah_rides = all_rides[all_rides["distance"].isna()]
    if ah_rides.empty:
        return wo_dist if not wo_dist.empty else pd.Series(dtype=float, name="cycling_km")

    try:
        dc = _by_type("DistanceCycling").copy()
    except FileNotFoundError:
        return wo_dist if not wo_dist.empty else pd.Series(dtype=float, name="cycling_km")

    if dc.empty:
        return wo_dist if not wo_dist.empty else pd.Series(dtype=float, name="cycling_km")

    if "unit" in dc.columns and (dc["unit"] == "mi").any():
        dc.loc[dc["unit"] == "mi", "value_num"] *= 1.60934

    dc["date"] = dc["startDate"].dt.normalize()
    rides_sorted = ah_rides[["startDate", "endDate"]].rename(
        columns={"startDate": "ride_start", "endDate": "ride_end"}
    ).sort_values("ride_start").reset_index(drop=True)

    merged = pd.merge_asof(
        dc.sort_values("startDate")[["startDate", "date", "value_num"]].reset_index(drop=True),
        rides_sorted,
        left_on="startDate", right_on="ride_start", direction="backward",
    )
    in_ride = merged[merged["startDate"] < merged["ride_end"]]
    ah_dist = in_ride.groupby("date")["value_num"].sum().rename("cycling_km")

    combined = pd.concat([wo_dist, ah_dist]).groupby(level=0).sum()
    return combined.rename("cycling_km")


@lru_cache(maxsize=1)
def _pmc_df() -> pd.DataFrame:
    """
    Compute full-history PMC (ATL / CTL / TSB) using the Banister TRIMP model.
    """
    REST_HR = 50
    MAX_HR  = 185
    HR_RANGE = MAX_HR - REST_HR

    DEFAULT_HR_RATIO = (0.65 * MAX_HR - REST_HR) / HR_RANGE

    wo = _workouts().copy()
    wo["date"]     = pd.to_datetime(wo["startDate"], errors="coerce").dt.normalize()
    wo["duration_min"] = pd.to_numeric(wo["duration_min"], errors="coerce").fillna(0)
    wo["avg_hr"]   = pd.to_numeric(wo.get("avg_hr"), errors="coerce")
    wo["is_run"]   = wo["workoutType"].str.contains("Running", na=False)
    wo["is_cyc"]   = wo["workoutType"].str.contains("Cycling", na=False)

    def trimp_row(row):
        dur = row["duration_min"]
        if dur <= 0:
            return 0.0
        hr = row["avg_hr"]
        if pd.isna(hr) or hr <= REST_HR:
            hr_ratio = DEFAULT_HR_RATIO
        else:
            hr_ratio = min((hr - REST_HR) / HR_RANGE, 1.0)
        b = 1.92 if row["is_run"] else 1.67
        return dur * hr_ratio * 0.64 * np.exp(b * hr_ratio)

    wo["trimp"] = wo.apply(trimp_row, axis=1)
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

    alpha_atl = 1 - np.exp(-1 / 7)
    alpha_ctl = 1 - np.exp(-1 / 42)

    full["atl"] = full["load"].ewm(alpha=alpha_atl, adjust=False).mean().round(1)
    full["ctl"] = full["load"].ewm(alpha=alpha_ctl, adjust=False).mean().round(1)
    full["tsb"] = (full["ctl"] - full["atl"]).round(1)

    full.index.name = "date"
    return full.reset_index()


def clear_all_caches() -> None:
    """Clear every lru_cache in this module. Call after any data write."""
    _daily.cache_clear()
    _sleep.cache_clear()
    _workouts.cache_clear()
    _activity.cache_clear()
    _profile.cache_clear()
    _by_type.cache_clear()
    _running_dist_by_day.cache_clear()
    _cycling_dist_by_day.cache_clear()
    _pmc_df.cache_clear()
    _valid_metrics.cache_clear()
