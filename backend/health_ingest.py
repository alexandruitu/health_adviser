"""
Health Auto Export ingest helpers.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent.parent.parent / "health_csvs" / "cleaned"

# How each daily_summary column is built from a by_type CSV:  col_name → (csv_name, agg)
_DAILY_AGG: dict = {
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

# Maps Health Auto Export metric names → our by_type CSV filenames
HEALTH_METRIC_MAP: dict = {
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
# (populated by main.py after importing analytics functions)
_CACHES_TO_CLEAR = [
    "_daily", "_workouts", "_running_dist_by_day", "_cycling_dist_by_day",
    "_pmc_df", "_valid_metrics", "_sleep",
]

HEALTH_INGEST_CONFIG = Path(__file__).parent.parent / "health_ingest_config.json"


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
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return s.strip()


def _ingest_metrics(metrics: list) -> tuple:
    """Append new metric rows from Health Auto Export payload. Returns (added, skipped, new_dates)."""
    added = skipped = 0
    new_dates: set = set()

    unmapped_names: list = []
    for metric in metrics:
        raw_name = metric.get("name", "")
        csv_name = HEALTH_METRIC_MAP.get(raw_name)
        if csv_name is None:
            unmapped_names.append(raw_name)
            continue

        unit = metric.get("units", "")
        rows = metric.get("data", [])
        if not rows:
            continue

        csv_path = DATA_DIR / "by_type" / f"{csv_name}.csv"

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

            _ns_arr = np.asarray(existing_ns, dtype="int64")
            if len(_ns_arr) and bool((np.abs(_ns_arr - ts_ns) < _90s_ns).any()):
                skipped += 1
                continue

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


def _ingest_workouts(workouts: list) -> tuple:
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
        duration_min = w.get("duration")
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


def _rebuild_daily_for_dates(new_dates: set) -> None:
    """Recompute daily_summary.csv rows for the given dates from by_type CSVs."""
    # Import here to avoid circular dependency
    from analytics import _daily

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
