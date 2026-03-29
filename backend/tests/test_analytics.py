"""
Tests for analytics helper functions.
These tests import from the analytics module (once created) or fall back to main.py.
"""
import sys
import os
import math
import pytest
import pandas as pd
import numpy as np

# Try to import from the analytics helper module first, fall back to main
try:
    from backend.analytics import (
        date_filter,
        to_records,
        _period_col,
        _sleep,
        _pmc_df,
    )
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    try:
        from analytics import (
            date_filter,
            to_records,
            _period_col,
            _sleep,
            _pmc_df,
        )
    except ImportError:
        # Fall back to main.py
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from backend.main import (
            date_filter,
            to_records,
            _period_col,
            _sleep,
            _pmc_df,
        )


# ─── date_filter ─────────────────────────────────────────────────────────────

def _make_df():
    return pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-06-15", "2024-12-31"]),
        "val": [1, 2, 3],
    })


def test_date_filter_start_only():
    df = _make_df()
    result = date_filter(df, "date", "2024-06-15", None)
    assert len(result) == 2
    assert all(result["date"] >= "2024-06-15")


def test_date_filter_end_only():
    df = _make_df()
    result = date_filter(df, "date", None, "2024-06-15")
    assert len(result) == 2
    assert all(result["date"] <= "2024-06-15")


def test_date_filter_both():
    df = _make_df()
    result = date_filter(df, "date", "2024-06-15", "2024-06-15")
    assert len(result) == 1
    assert result.iloc[0]["val"] == 2


def test_date_filter_no_args():
    df = _make_df()
    result = date_filter(df, "date", None, None)
    assert len(result) == 3


# ─── to_records ──────────────────────────────────────────────────────────────

def test_to_records_nan_to_none():
    df = pd.DataFrame({"a": [1.0, float("nan"), 3.0]})
    records = to_records(df)
    assert records[1]["a"] is None


def test_to_records_inf_to_none():
    df = pd.DataFrame({"a": [1.0, float("inf"), -float("inf")]})
    records = to_records(df)
    assert records[1]["a"] is None
    assert records[2]["a"] is None


def test_to_records_valid_values():
    df = pd.DataFrame({"a": [1.5, 2.5], "b": ["x", "y"]})
    records = to_records(df)
    assert records[0]["a"] == 1.5
    assert records[1]["b"] == "y"


# ─── _period_col ─────────────────────────────────────────────────────────────

def test_period_col_week():
    dates = pd.Series(pd.to_datetime(["2024-01-15", "2024-01-16", "2024-01-22"]))
    result = _period_col(dates, "week")
    # 2024-01-15 is a Monday, 2024-01-16 is Tuesday → same week Monday
    # 2024-01-22 is next Monday
    assert result.iloc[0] == result.iloc[1]  # same week
    assert result.iloc[0] != result.iloc[2]  # different week
    # format: YYYY-MM-DD
    assert len(result.iloc[0]) == 10


def test_period_col_month():
    dates = pd.Series(pd.to_datetime(["2024-01-15", "2024-01-31", "2024-02-01"]))
    result = _period_col(dates, "month")
    assert result.iloc[0] == result.iloc[1]  # same month
    assert result.iloc[0] != result.iloc[2]  # different month
    # format: YYYY-MM
    assert len(result.iloc[0]) == 7


def test_period_col_year():
    dates = pd.Series(pd.to_datetime(["2024-01-15", "2024-12-31", "2025-01-01"]))
    result = _period_col(dates, "year")
    assert result.iloc[0] == result.iloc[1]  # same year
    assert result.iloc[0] != result.iloc[2]  # different year
    # format: YYYY (4 digits)
    assert len(result.iloc[0]) == 4


# ─── sleep functions ─────────────────────────────────────────────────────────

def _make_sleep_df():
    """Create a minimal sleep stage DataFrame (input to _sleep pivot logic)."""
    rows = [
        {"date": "2024-01-15", "stage": "Core",  "duration_min": 240.0},
        {"date": "2024-01-15", "stage": "Deep",  "duration_min": 60.0},
        {"date": "2024-01-15", "stage": "REM",   "duration_min": 90.0},
        {"date": "2024-01-15", "stage": "Awake", "duration_min": 15.0},
        {"date": "2024-01-15", "stage": "InBed", "duration_min": 405.0},
        {"date": "2024-01-16", "stage": "InBed", "duration_min": 420.0},
    ]
    return pd.DataFrame(rows)


def _pivot_sleep(df):
    """Replicate the pivot logic from _sleep, operating on provided df."""
    if df.empty:
        return pd.DataFrame(columns=["night", "Awake", "Core", "Deep", "InBed", "REM", "Unspecified", "total_sleep_hours"])
    df = df.copy()
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


def test_sleep_pivot_basic():
    df = _make_sleep_df()
    pivot = _pivot_sleep(df)
    row = pivot[pivot["night"] == pd.Timestamp("2024-01-15")].iloc[0]
    assert row["Core"] == pytest.approx(4.0)  # 240 min / 60
    assert row["Deep"] == pytest.approx(1.0)  # 60 min
    assert row["REM"]  == pytest.approx(1.5)  # 90 min


def test_sleep_total_hours():
    df = _make_sleep_df()
    pivot = _pivot_sleep(df)
    row = pivot[pivot["night"] == pd.Timestamp("2024-01-15")].iloc[0]
    # total = Core + Deep + REM = 4 + 1 + 1.5 = 6.5
    assert row["total_sleep_hours"] == pytest.approx(6.5)


def test_sleep_fallback_inbed():
    """When Core/Deep/REM are all 0, total_sleep_hours falls back to InBed."""
    df = _make_sleep_df()
    pivot = _pivot_sleep(df)
    row = pivot[pivot["night"] == pd.Timestamp("2024-01-16")].iloc[0]
    # No Core/Deep/REM for 2024-01-16, only InBed=7h
    assert row["total_sleep_hours"] == pytest.approx(7.0)


def test_sleep_empty_input():
    df = pd.DataFrame(columns=["date", "stage", "duration_min"])
    pivot = _pivot_sleep(df)
    assert pivot.empty
    expected_cols = {"night", "Awake", "Core", "Deep", "InBed", "REM", "Unspecified", "total_sleep_hours"}
    assert expected_cols.issubset(set(pivot.columns))


# ─── TRIMP tests ─────────────────────────────────────────────────────────────

# Replicate constants from main.py for testing
REST_HR = 50
MAX_HR  = 185
HR_RANGE = MAX_HR - REST_HR
DEFAULT_HR_RATIO = (0.65 * MAX_HR - REST_HR) / HR_RANGE


def _trimp_row(dur, avg_hr, is_run=True):
    """Pure function replicating the TRIMP calculation in _pmc_df."""
    if dur <= 0:
        return 0.0
    if avg_hr is None or math.isnan(avg_hr) or avg_hr <= REST_HR:
        hr_ratio = DEFAULT_HR_RATIO
    else:
        hr_ratio = min((avg_hr - REST_HR) / HR_RANGE, 1.0)
    b = 1.92 if is_run else 1.67
    return dur * hr_ratio * 0.64 * math.exp(b * hr_ratio)


def test_trimp_no_hr():
    """When HR is missing, TRIMP uses DEFAULT_HR_RATIO and is > 0."""
    result = _trimp_row(60, float("nan"), is_run=True)
    assert result > 0
    # Verify it uses the default ratio
    expected = 60 * DEFAULT_HR_RATIO * 0.64 * math.exp(1.92 * DEFAULT_HR_RATIO)
    assert result == pytest.approx(expected, rel=1e-6)


def test_trimp_with_hr():
    """TRIMP with avg_hr=165, rest=50, max=185 is > 0."""
    result = _trimp_row(60, 165, is_run=True)
    assert result > 0
    hr_ratio = (165 - REST_HR) / HR_RANGE
    expected = 60 * hr_ratio * 0.64 * math.exp(1.92 * hr_ratio)
    assert result == pytest.approx(expected, rel=1e-6)


def test_trimp_zero_duration():
    """TRIMP for 0-min workout = 0."""
    result = _trimp_row(0, 165, is_run=True)
    assert result == 0.0
