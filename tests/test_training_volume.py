"""
Tests for /api/training/volume endpoint.
Run with:  cd health_app && python3 -m pytest tests/ -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from backend.main import training_volume, training_pmc, training_hrv, _daily, _workouts, _by_type


# ── empty range ───────────────────────────────────────────────────────────────

def test_empty_range_returns_empty_list():
    """No workouts or distance in a future-only range must return [] (not 500)."""
    result = training_volume(resolution="month", start="2026-03-01", end="2026-03-15")
    assert result == []


def test_empty_year_range_returns_empty_list():
    result = training_volume(resolution="year", start="2030-01-01", end="2030-12-31")
    assert result == []


# ── period format ─────────────────────────────────────────────────────────────

def test_month_resolution_period_format():
    """Monthly periods must be YYYY-MM strings."""
    result = training_volume(resolution="month", start="2025-01-01", end="2025-06-30")
    assert len(result) > 0
    for row in result:
        assert len(row["period"]) == 7, f"Bad period: {row['period']}"
        assert row["period"][4] == "-"


def test_week_resolution_period_format():
    """Weekly periods must be YYYY-MM-DD (Monday) strings."""
    result = training_volume(resolution="week", start="2025-01-01", end="2025-03-31")
    assert len(result) > 0
    for row in result:
        assert len(row["period"]) == 10, f"Bad period: {row['period']}"


def test_year_resolution_period_format():
    result = training_volume(resolution="year", start="2022-01-01", end="2025-12-31")
    assert len(result) > 0
    for row in result:
        assert len(row["period"]) == 4


# ── running distance sanity ───────────────────────────────────────────────────

def test_running_km_not_inflated_by_walking():
    """
    DistanceWalkingRunning includes all daily steps.
    running_km must be well below the total DWR for the same period.
    For a recreational runner, annual running distance is < 2500 km.
    """
    result = training_volume(resolution="year", start="2025-01-01", end="2025-12-31")
    assert len(result) == 1
    running_km = result[0]["running_km"]

    daily = _daily()
    total_dwr = daily[daily["date"].dt.year == 2025]["DistanceWalkingRunning"].sum()

    assert running_km < total_dwr, (
        f"running_km ({running_km:.0f}) should be less than total DWR ({total_dwr:.0f})"
    )
    assert running_km < 2500, (
        f"running_km ({running_km:.0f}) is implausibly high for a recreational runner"
    )


def test_running_km_per_month_under_300():
    """No single month should exceed 300 km for a recreational runner."""
    result = training_volume(resolution="month", start="2025-01-01", end="2025-12-31")
    for row in result:
        assert row["running_km"] <= 300, (
            f"Month {row['period']} has {row['running_km']:.0f} km — likely includes walking"
        )


def test_running_km_proportional_to_sessions():
    """
    Months with 0 running sessions must have 0 running km.
    Months with sessions must have > 0 km.
    """
    result = training_volume(resolution="month", start="2025-01-01", end="2025-12-31")
    for row in result:
        if row["running_sessions"] == 0:
            assert row["running_km"] == 0, (
                f"{row['period']}: 0 sessions but {row['running_km']} km"
            )
        else:
            assert row["running_km"] > 0, (
                f"{row['period']}: {row['running_sessions']} sessions but 0 km"
            )


# ── cycling distance ──────────────────────────────────────────────────────────

def test_cycling_km_per_month_under_1500():
    """DistanceCycling is specific to cycling workouts; monthly total should be sane."""
    result = training_volume(resolution="month", start="2025-01-01", end="2025-12-31")
    for row in result:
        assert row["cycling_km"] <= 1500, (
            f"Month {row['period']} has {row['cycling_km']:.0f} cycling km"
        )


# ── required columns ──────────────────────────────────────────────────────────

def test_all_required_columns_present():
    result = training_volume(resolution="month", start="2025-06-01", end="2025-08-31")
    assert len(result) > 0
    required = {"period", "running_min", "running_sessions", "longest_run_min",
                "cycling_min", "cycling_sessions", "longest_ride_min",
                "running_km", "cycling_km"}
    assert required.issubset(result[0].keys())


# ── PMC sanity ────────────────────────────────────────────────────────────────

def test_pmc_has_required_columns():
    result = training_pmc(start="2025-01-01", end="2025-03-31")
    assert len(result) > 0
    assert {"date", "ctl", "atl", "tsb", "load"}.issubset(result[0].keys())


def test_pmc_tsb_equals_ctl_minus_atl():
    result = training_pmc(start="2025-06-01", end="2025-06-30")
    for row in result:
        assert abs(row["tsb"] - (row["ctl"] - row["atl"])) < 0.2


# ── HRV sanity ────────────────────────────────────────────────────────────────

def test_hrv_has_rolling_column():
    result = training_hrv(start="2025-01-01", end="2025-12-31")
    assert len(result) > 0
    assert "hrv_30d" in result[0]


def test_hrv_values_in_plausible_range():
    result = training_hrv(start="2025-01-01", end="2025-12-31")
    for row in result:
        if row["hrv"] is not None:
            assert 10 <= row["hrv"] <= 200, f"HRV {row['hrv']} out of range"
