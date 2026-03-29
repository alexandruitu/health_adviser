"""
Tests for Google Drive / HAE file parsing functions.
Uses in-memory SQLite instead of the real database.
"""
import sys
import os
import json
import sqlite3
import pytest
from unittest.mock import patch

# Try to import from the gdrive helper module first, fall back to main
try:
    import backend.gdrive as gdrive_module
    from backend.gdrive import _parse_hae_stage, _ingest_hae_file
    _module = gdrive_module
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    try:
        import gdrive as gdrive_module
        from gdrive import _parse_hae_stage, _ingest_hae_file
        _module = gdrive_module
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        import backend.main as gdrive_module
        from backend.main import _parse_hae_stage, _ingest_hae_file
        _module = gdrive_module


# ─── _parse_hae_stage ────────────────────────────────────────────────────────

def test_parse_hae_stage_rem():
    assert _parse_hae_stage("AsleepREM") == "REM"


def test_parse_hae_stage_deep():
    assert _parse_hae_stage("AsleepDeep") == "Deep"


def test_parse_hae_stage_core():
    assert _parse_hae_stage("AsleepCore") == "Core"


def test_parse_hae_stage_inbed():
    assert _parse_hae_stage("InBed") == "InBed"


def test_parse_hae_stage_awake():
    assert _parse_hae_stage("awake") == "Awake"


def test_parse_hae_stage_unknown():
    assert _parse_hae_stage("garbage") == "Core"


# ─── _ingest_hae_file ────────────────────────────────────────────────────────

def _make_in_memory_db():
    """Create an in-memory SQLite connection with required tables."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sleep (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            date         TEXT NOT NULL,
            stage        TEXT NOT NULL,
            start_ts     REAL,
            end_ts       REAL,
            duration_min REAL,
            source       TEXT,
            UNIQUE(date, stage, start_ts)
        );
        CREATE TABLE IF NOT EXISTS metrics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            start_ts    REAL,
            end_ts      REAL,
            value       REAL,
            unit        TEXT,
            source      TEXT,
            device      TEXT,
            UNIQUE(metric_name, start_ts)
        );
        CREATE TABLE IF NOT EXISTS workouts (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            workout_type        TEXT,
            start_ts            REAL UNIQUE,
            end_ts              REAL,
            duration_min        REAL,
            distance_km         REAL,
            active_energy_kcal  REAL,
            source              TEXT,
            device              TEXT,
            moving_time_min     REAL,
            elevation_m         REAL,
            avg_hr              REAL,
            max_hr              REAL,
            suffer_score        REAL,
            avg_cadence         REAL,
            avg_watts           REAL,
            avg_speed_kmh       REAL,
            activity_name       TEXT,
            workout_subtype     INTEGER DEFAULT 0,
            trainer             INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS gdrive_files (
            file_id       TEXT PRIMARY KEY,
            file_name     TEXT,
            modified_time TEXT,
            processed_at  REAL,
            records_added INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sync_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            source    TEXT,
            synced_at REAL,
            added     INTEGER,
            skipped   INTEGER,
            note      TEXT
        );
    """)
    conn.commit()
    return conn


def _make_hae_sleep_payload():
    """HAE payload with a sleep_analysis metric."""
    return json.dumps({
        "data": {
            "metrics": [
                {
                    "name": "sleep_analysis",
                    "units": "hr",
                    "data": [
                        {
                            "sleepStart": "2024-01-15 22:00:00",
                            "date": "2024-01-16",
                            "rem": 1.5,
                            "deep": 1.0,
                            "core": 4.0,
                            "awake": 0.25,
                            "inBed": 7.0,
                            "source": "Apple Watch",
                        }
                    ]
                }
            ],
            "workouts": []
        }
    }).encode()


def _make_hae_metric_payload():
    """HAE payload with a heart_rate metric."""
    return json.dumps({
        "data": {
            "metrics": [
                {
                    "name": "heart_rate",
                    "units": "bpm",
                    "data": [
                        {
                            "date": "2024-01-15 08:00:00",
                            "qty": 65.0,
                            "source": "Apple Watch",
                        }
                    ]
                }
            ],
            "workouts": []
        }
    }).encode()


def test_ingest_hae_sleep_rows():
    """Given a HAE payload with sleep_analysis, correct sleep rows are inserted."""
    conn = _make_in_memory_db()
    with patch.object(_module, "_db", return_value=conn):
        added, skipped = _ingest_hae_file(_make_hae_sleep_payload())

    rows = conn.execute("SELECT * FROM sleep").fetchall()
    assert len(rows) > 0
    stages = {r["stage"] for r in rows}
    # Should have Core, Deep, REM at minimum (awake/inBed also if > 0)
    assert "Core" in stages
    assert "REM" in stages
    assert "Deep" in stages
    assert added > 0


def test_ingest_hae_metric_rows():
    """Given a HAE payload with heart_rate metric, metric rows are inserted."""
    conn = _make_in_memory_db()
    with patch.object(_module, "_db", return_value=conn):
        added, skipped = _ingest_hae_file(_make_hae_metric_payload())

    rows = conn.execute("SELECT * FROM metrics WHERE metric_name = 'HeartRate'").fetchall()
    assert len(rows) > 0
    assert rows[0]["value"] == pytest.approx(65.0)
    assert added > 0


def test_ingest_hae_invalid_json():
    """Invalid JSON content returns (0, 0)."""
    conn = _make_in_memory_db()
    with patch.object(_module, "_db", return_value=conn):
        result = _ingest_hae_file(b"not valid json {{{")
    assert result == (0, 0)


def test_ingest_hae_empty_payload():
    """Payload with empty metrics/workouts lists returns (0, 0)."""
    payload = json.dumps({"data": {"metrics": [], "workouts": []}}).encode()
    conn = _make_in_memory_db()
    with patch.object(_module, "_db", return_value=conn):
        added, skipped = _ingest_hae_file(payload)
    assert added == 0
    assert skipped == 0
