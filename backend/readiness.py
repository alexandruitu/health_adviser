"""
Personalized Recovery Readiness Index
======================================
Answers: "Given YOUR physiology and training load, how ready are you today?"

Components (weights renormalize if a signal is missing for a given day):
  1. HRV Score         (40%) — tonight's HRV vs personal 30-day rolling average
  2. Sleep Score       (35%) — Garmin Sleep Score vs personal 30-day baseline
  3. Body Battery      (25%) — body battery charged during sleep (Garmin, 0-100)
  + TSB Modifier       (±15 pts additive) — training stress balance from PMC

Readiness bands:
  85-100 → Peak          (hard training / race ready)
  70-84  → High          (quality training)
  55-69  → Moderate      (aerobic / technique work)
  40-54  → Low           (active recovery)
  0-39   → Recovery      (rest day)
"""

from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Optional

from db import _db


# ── Component weights ────────────────────────────────────────────────────────
_WEIGHTS = {
    "hrv":     0.40,
    "sleep":   0.35,
    "battery": 0.25,
}

# ── TSB → modifier mapping (additive points) ─────────────────────────────────
# Positive TSB = fresh; deeply negative = accumulated fatigue
def _tsb_modifier(tsb: Optional[float]) -> float:
    if tsb is None:
        return 0.0
    if tsb > 10:
        return 10.0   # well rested / tapering
    if tsb > 0:
        return 5.0    # slightly fresh
    if tsb > -15:
        return 0.0    # neutral zone
    if tsb > -30:
        return -5.0   # moderate fatigue
    if tsb > -50:
        return -12.0  # significant fatigue
    return -15.0      # heavy training block


# ── Rolling personal baseline ─────────────────────────────────────────────────
def _rolling_avg(metric_name: str, reference_date: date,
                 window_days: int = 30, min_days: int = 7) -> Optional[float]:
    """
    Personal baseline: AVG of metric over the [window_days] days BEFORE
    reference_date (exclusive), requiring at least min_days of data.
    """
    conn = _db()
    end_ts   = datetime.combine(reference_date, datetime.min.time()).timestamp()
    start_ts = end_ts - window_days * 86400

    row = conn.execute("""
        SELECT AVG(value), COUNT(*)
        FROM metrics
        WHERE metric_name = ?
          AND source = 'Garmin'
          AND start_ts >= ? AND start_ts < ?
    """, (metric_name, start_ts, end_ts)).fetchone()

    if row and row[1] and row[1] >= min_days and row[0] is not None:
        return row[0]
    return None


# ── Individual component scores ───────────────────────────────────────────────
def _hrv_score(hrv_val: float, baseline: float) -> float:
    """
    Map HRV deviation from personal baseline to 0-100.
    At baseline → 70 (neutral).
    +20% above  → ~100 (excellent recovery signal).
    -20% below  → ~10  (strong suppression signal).
    """
    pct_dev = (hrv_val - baseline) / baseline          # -1 to +1 range typically
    score = 70.0 + pct_dev * 150.0                     # ±20% → ±30 pts from 70
    return max(0.0, min(100.0, score))


def _sleep_score(garmin_score: float, baseline: float) -> float:
    """
    Normalize Garmin Sleep Score against personal baseline.
    At baseline → 70, above/below scales linearly.
    """
    pct_dev = (garmin_score - baseline) / max(baseline, 1.0)
    score = garmin_score + pct_dev * 20.0              # slight amplification
    return max(0.0, min(100.0, score))


def _battery_score(bb: float) -> float:
    """Body battery is already 0-100. Apply mild curve to sharpen mid-range."""
    return max(0.0, min(100.0, bb))


# ── Single-day readiness ──────────────────────────────────────────────────────
def _day_readiness(d: date, pmc_by_date: dict) -> Optional[dict]:
    """
    Compute readiness for a single date. Returns None if no signals available.
    pmc_by_date: {date_str: {atl, ctl, tsb}} from the PMC dataframe.
    """
    conn = _db()
    cal_ts     = datetime.combine(d, datetime.min.time()).timestamp()
    cal_ts_end = cal_ts + 86400
    date_str   = str(d)

    def _latest(metric: str) -> Optional[float]:
        row = conn.execute("""
            SELECT value FROM metrics
            WHERE metric_name = ? AND source = 'Garmin'
              AND start_ts >= ? AND start_ts < ?
            ORDER BY start_ts DESC LIMIT 1
        """, (metric, cal_ts, cal_ts_end)).fetchone()
        return row[0] if row else None

    # ── Raw values ─────────────────────────────────────────────────────────
    hrv_val     = _latest("HeartRateVariabilitySDNN")
    sleep_raw   = _latest("GarminSleepScore")
    battery_val = _latest("GarminBodyBatteryDuringSleep")

    # ── Personal baselines (30-day rolling, excluding today) ───────────────
    hrv_baseline   = _rolling_avg("HeartRateVariabilitySDNN", d)
    sleep_baseline = _rolling_avg("GarminSleepScore", d)

    # ── Component scores ───────────────────────────────────────────────────
    components: dict[str, Optional[float]] = {
        "hrv":     _hrv_score(hrv_val, hrv_baseline) if hrv_val and hrv_baseline else None,
        "sleep":   _sleep_score(sleep_raw, sleep_baseline) if sleep_raw and sleep_baseline else None,
        "battery": _battery_score(battery_val) if battery_val is not None else None,
    }

    # Need at least one signal
    available = {k: v for k, v in components.items() if v is not None}
    if not available:
        return None

    # ── Weighted average (renormalize if some components missing) ──────────
    total_weight = sum(_WEIGHTS[k] for k in available)
    base = sum(_WEIGHTS[k] * v for k, v in available.items()) / total_weight

    # ── TSB modifier ───────────────────────────────────────────────────────
    pmc_today = pmc_by_date.get(date_str, {})
    tsb = pmc_today.get("tsb")
    modifier = _tsb_modifier(tsb)

    readiness = max(0.0, min(100.0, base + modifier))

    return {
        "date":            date_str,
        "readiness":       round(readiness, 1),
        "label":           _label(readiness),
        # components (for breakdown display)
        "hrv_score":       round(components["hrv"], 1)     if components["hrv"]     is not None else None,
        "sleep_score":     round(components["sleep"], 1)   if components["sleep"]   is not None else None,
        "battery_score":   round(components["battery"], 1) if components["battery"] is not None else None,
        "tsb_modifier":    round(modifier, 1),
        # raw values (for tooltip)
        "hrv_val":         round(hrv_val, 1)       if hrv_val     is not None else None,
        "hrv_baseline":    round(hrv_baseline, 1)  if hrv_baseline is not None else None,
        "sleep_raw":       round(sleep_raw, 1)     if sleep_raw   is not None else None,
        "sleep_baseline":  round(sleep_baseline, 1) if sleep_baseline is not None else None,
        "battery_val":     round(battery_val, 1)   if battery_val is not None else None,
        "tsb":             round(tsb, 1)           if tsb         is not None else None,
        "atl":             round(pmc_today.get("atl", 0), 1),
        "ctl":             round(pmc_today.get("ctl", 0), 1),
    }


def _label(score: float) -> str:
    if score >= 85: return "Peak"
    if score >= 70: return "High"
    if score >= 55: return "Moderate"
    if score >= 40: return "Low"
    return "Recovery"


# ── Public API ────────────────────────────────────────────────────────────────
def compute_readiness_series(start_date: date, end_date: date) -> list[dict]:
    """
    Compute Readiness Index for every day in [start_date, end_date].
    Returns list of day dicts sorted by date.
    """
    # Load full PMC into memory once (cheap — already cached in analytics.py)
    from analytics import _pmc_df
    pmc_df = _pmc_df()
    pmc_by_date = {
        str(row["date"])[:10]: {
            "atl": row.get("atl"),
            "ctl": row.get("ctl"),
            "tsb": row.get("tsb"),
        }
        for row in pmc_df.to_dict("records")
    }

    results = []
    current = start_date
    while current <= end_date:
        day = _day_readiness(current, pmc_by_date)
        if day:
            results.append(day)
        current += timedelta(days=1)

    return results


def compute_readiness_today() -> Optional[dict]:
    """Convenience wrapper for today's readiness."""
    from analytics import _pmc_df
    pmc_df = _pmc_df()
    pmc_by_date = {str(row["date"])[:10]: row for row in pmc_df.to_dict("records")}
    return _day_readiness(date.today(), pmc_by_date)
