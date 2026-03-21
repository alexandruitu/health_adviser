"""
Tests for health_ingest helper functions — specifically _parse_hae_date.
"""
import sys
import os
import pytest

# Try to import from the health_ingest helper module first, fall back to main
try:
    from backend.health_ingest import _parse_hae_date
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    try:
        from health_ingest import _parse_hae_date
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from backend.main import _parse_hae_date


# ─── _parse_hae_date ─────────────────────────────────────────────────────────

def test_parse_hae_date_with_tz():
    """'2024-01-15 07:30:00 -0500' parses to a local naive string 'YYYY-MM-DD HH:MM:SS'."""
    result = _parse_hae_date("2024-01-15 07:30:00 -0500")
    # Must be a naive datetime string (no timezone info)
    assert "+" not in result
    assert result.count(":") == 2
    assert len(result) == 19  # 'YYYY-MM-DD HH:MM:SS'


def test_parse_hae_date_no_tz():
    """'2024-01-15 07:30:00' (no timezone) returns the same string."""
    result = _parse_hae_date("2024-01-15 07:30:00")
    assert result == "2024-01-15 07:30:00"


def test_parse_hae_date_iso_tz():
    """'2024-01-15T07:30:00+00:00' parses correctly to a naive local string."""
    result = _parse_hae_date("2024-01-15T07:30:00+00:00")
    # Must be a naive datetime string
    assert "T" not in result
    assert "+" not in result
    assert len(result) == 19


def test_parse_hae_date_unknown_fmt():
    """Unknown format returns the input stripped."""
    raw = "not-a-date-string"
    result = _parse_hae_date(raw)
    assert result == raw.strip()
