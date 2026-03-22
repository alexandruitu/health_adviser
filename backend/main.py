"""
Apple Health Dashboard — FastAPI backend
Reads from the cleaned CSV directory and serves aggregated data.
"""

import io
import json
import math
import os
import time
from pathlib import Path
from typing import Optional, List

import pandas as pd
from fastapi import FastAPI, Query, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

# ─── helper modules ───────────────────────────────────────────────────────────
from db import _db, _ensure_biomarker_tables
from analytics import (
    _daily,
    _sleep,
    _workouts,
    _activity,
    _profile,
    _by_type,
    _running_dist_by_day,
    _cycling_dist_by_day,
    _pmc_df,
    _period_col,
    date_filter,
    to_records,
    _valid_metrics,
    STRAVA_EXTRA_COLS,
    DATA_DIR,
    clear_all_caches,
)
from health_ingest import (
    _DAILY_AGG,
    HEALTH_METRIC_MAP,
    _load_ingest_config,
    _save_ingest_config,
    _parse_hae_date,
    _ingest_metrics,
    _ingest_workouts,
    _rebuild_daily_for_dates,
)
from strava import (
    WORKOUT_TYPE_MAP,
    _load_strava_config,
    _save_strava_config,
    _ensure_valid_token,
    _append_activities,
    _run_sync_job,
    _sync_job,
    STRAVA_CONFIG_PATH,
    STRAVA_TOKEN_URL,
)
from gdrive import (
    _load_gdrive_config,
    _save_gdrive_config,
    _ensure_gdrive_token,
    _gdrive_folder_id,
    _parse_hae_stage,
    _ingest_hae_file,
    _run_gdrive_sync,
    _gdrive_sync_job,
    GDRIVE_CONFIG_PATH,
    GDRIVE_TOKEN_URL,
    GDRIVE_FILES_API,
)
from biomarkers import (
    BIOMARKER_CATEGORIES,
    _categorize_marker,
    BIOMARKERS_CONFIG_PATH,
    _load_biomarkers_config,
    _extract_biomarkers_via_claude,
)
from garmin import (
    _load_garmin_config,
    _save_garmin_config,
    _login as _garmin_login,
    _resume_session as _garmin_resume,
    _run_garmin_sync,
    _garmin_sync_job,
    GARMIN_CONFIG_PATH,
)

# ─── constants kept in main (OAuth redirect URIs used directly in routes) ────
STRAVA_AUTH_URL     = "https://www.strava.com/oauth/authorize"
STRAVA_REDIRECT_URI = "http://localhost:8000/api/strava/callback"
GDRIVE_AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
GDRIVE_REDIRECT_URI = "http://localhost:8000/api/gdrive/callback"
GDRIVE_SCOPES       = "https://www.googleapis.com/auth/drive.readonly"

# ─── app setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="Apple Health API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173", "http://localhost:5174"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Ensure biomarker tables exist on startup
_ensure_biomarker_tables()


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

    sleep_df = _sleep()
    last90_sleep = sleep_df[sleep_df["night"] >= sleep_df["night"].max() - pd.Timedelta(days=90)]
    avg_sleep = round(float(last90_sleep["total_sleep_hours"].dropna().mean()), 1) if len(last90_sleep) else None

    workouts_df = _workouts()
    last90_wo = workouts_df[workouts_df["startDate"] >= workouts_df["startDate"].max() - pd.Timedelta(days=90)]
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


@app.get("/api/available_metrics")
def available_metrics():
    return _valid_metrics()


# ─── training analytics ──────────────────────────────────────────────────────

@app.get("/api/training/volume")
def training_volume(
    resolution: str = "month",
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    """Volume aggregated by sport and time resolution (week | month | year)."""
    wo = _workouts().copy()
    ds = _daily().copy()

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

    MAX_WORKOUT_MIN = 600
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

    sport_wo = sport_wo[sport_wo["duration_min"] <= 600]
    min_m = sport_wo.groupby(["year", "month"])["duration_min"].sum()

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


# ─── activities list ──────────────────────────────────────────────────────────

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

    df = df[df["duration_min"] < 960]

    if df.empty:
        return []

    records = []

    if df["distance"].notna().any():
        row = df.loc[df["distance"].idxmax()]
        records.append({"type": "Longest distance", "value": round(float(row["distance"]), 1),
                        "unit": "km", "date": str(row["startDate"])[:10]})

    if df["duration_min"].notna().any():
        row = df.loc[df["duration_min"].idxmax()]
        records.append({"type": "Longest duration", "value": round(float(row["duration_min"]) / 60, 2),
                        "unit": "h", "date": str(row["startDate"])[:10]})

    if df["elevation_m"].notna().any():
        row = df.loc[df["elevation_m"].idxmax()]
        records.append({"type": "Most elevation", "value": round(float(row["elevation_m"])),
                        "unit": "m", "date": str(row["startDate"])[:10]})

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

    hr_df = df[df["avg_hr"].notna() & (df["avg_hr"] > 0) & (df["distance"] > 5)]
    if not hr_df.empty:
        row = hr_df.loc[hr_df["avg_hr"].idxmin()]
        records.append({"type": "Lowest avg HR", "value": int(row["avg_hr"]),
                        "unit": "bpm", "date": str(row["startDate"])[:10]})

    return records


# ─── Strava integration ───────────────────────────────────────────────────────

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
    import httpx
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


@app.post("/api/strava/sync")
def strava_sync(background_tasks: BackgroundTasks, force: bool = False):
    import strava as _strava
    if _strava._sync_job.get("status") == "running":
        return {"status": "running"}
    background_tasks.add_task(_run_sync_job, force=force)
    return {"status": "started"}


@app.get("/api/strava/sync/status")
def strava_sync_status():
    import strava as _strava
    return _strava._sync_job


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

    wo = wo[wo["duration_min"] <= 600]
    wo["period"] = _period_col(wo["startDate"], resolution)

    for col in ["elevation_m", "avg_hr", "max_hr", "suffer_score",
                "avg_cadence", "avg_watts", "moving_time_min", "distance"]:
        if col in wo.columns:
            wo[col] = pd.to_numeric(wo[col], errors="coerce")

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


# ─── Google Drive integration ─────────────────────────────────────────────────

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
    from urllib.parse import urlencode
    params = {
        "client_id":     cfg["client_id"],
        "redirect_uri":  GDRIVE_REDIRECT_URI,
        "response_type": "code",
        "scope":         GDRIVE_SCOPES,
        "access_type":   "offline",
        "prompt":        "consent",
    }
    return RedirectResponse(f"{GDRIVE_AUTH_URL}?{urlencode(params)}")


@app.get("/api/gdrive/callback")
def gdrive_callback(code: str):
    cfg = _load_gdrive_config()
    import httpx
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
    import gdrive as _gdrive
    if _gdrive._gdrive_sync_job.get("status") == "running":
        return {"status": "already_running"}
    background_tasks.add_task(_run_gdrive_sync)
    return {"status": "started"}


@app.get("/api/gdrive/sync/status")
def gdrive_sync_status():
    import gdrive as _gdrive
    return _gdrive._gdrive_sync_job


# ─── Garmin Connect integration ───────────────────────────────────────────────

@app.get("/api/garmin/status")
def garmin_status():
    cfg = _load_garmin_config()
    connected = False
    if cfg.get("email"):
        try:
            connected = _garmin_resume()
        except Exception:
            connected = False
    return {
        "connected": connected,
        "email": cfg.get("email") if connected else None,
        "last_sync": cfg.get("last_sync_timestamp"),
    }


@app.post("/api/garmin/connect")
def garmin_connect(body: dict):
    email    = body.get("email", "").strip()
    password = body.get("password", "").strip()
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    try:
        _garmin_login(email, password)
        cfg = _load_garmin_config()
        cfg["email"] = email
        _save_garmin_config(cfg)
        return {"connected": True, "email": email}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Garmin login failed: {e}")


@app.post("/api/garmin/disconnect")
def garmin_disconnect():
    import shutil
    from garmin import GARMIN_TOKEN_DIR
    if GARMIN_TOKEN_DIR.exists():
        shutil.rmtree(str(GARMIN_TOKEN_DIR))
    if GARMIN_CONFIG_PATH.exists():
        GARMIN_CONFIG_PATH.write_text("{}")
    return {"connected": False}


@app.post("/api/garmin/sync")
def garmin_sync(background_tasks: BackgroundTasks, force: bool = False):
    import garmin as _garmin
    if _garmin._garmin_sync_job.get("status") == "running":
        return {"status": "already_running"}
    background_tasks.add_task(_run_garmin_sync, force)
    return {"status": "started"}


@app.get("/api/garmin/sync/status")
def garmin_sync_status():
    import garmin as _garmin
    return _garmin._garmin_sync_job


# ─── Apple Health Auto Export ingest ─────────────────────────────────────────

@app.get("/api/health/status")
def health_ingest_status():
    cfg = _load_ingest_config()
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
    data = payload.get("data") or payload
    metrics  = data.get("metrics", [])
    workouts_data = data.get("workouts", [])

    added_m, skipped_m, new_dates = _ingest_metrics(metrics)
    added_w, skipped_w            = _ingest_workouts(workouts_data)
    added   = added_m + added_w
    skipped = skipped_m + skipped_w

    if new_dates:
        _rebuild_daily_for_dates(new_dates)

    clear_all_caches()

    cfg = _load_ingest_config()
    cfg["last_ingest"]  = int(time.time())
    cfg["total_added"]  = cfg.get("total_added", 0) + added
    _save_ingest_config(cfg)

    return {"added": added, "skipped": skipped}


@app.post("/api/health/upload")
async def health_upload(file: UploadFile = File(...)):
    """
    Accept .hae or .json file uploads from Health Auto Export (iCloud Drive).
    """
    content = await file.read()

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
    workouts_data = data.get("workouts", [])

    if not metrics and not workouts_data:
        raise HTTPException(status_code=400, detail="No metrics or workouts found in file")

    added_m, skipped_m, new_dates = _ingest_metrics(metrics)
    added_w, skipped_w            = _ingest_workouts(workouts_data)
    added   = added_m + added_w
    skipped = skipped_m + skipped_w

    if new_dates:
        _rebuild_daily_for_dates(new_dates)

    clear_all_caches()

    cfg = _load_ingest_config()
    cfg["last_ingest"] = int(time.time())
    cfg["total_added"] = cfg.get("total_added", 0) + added
    _save_ingest_config(cfg)

    return {"added": added, "skipped": skipped, "filename": file.filename}


# ─── Biomarkers ───────────────────────────────────────────────────────────────

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
