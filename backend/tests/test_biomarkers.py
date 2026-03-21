"""
Tests for biomarker categorization functions.
"""
import sys
import os
import pytest

# Try to import from the biomarkers helper module first, fall back to main
try:
    from backend.biomarkers import _categorize_marker
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    try:
        from biomarkers import _categorize_marker
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from backend.main import _categorize_marker


# ─── _categorize_marker ──────────────────────────────────────────────────────

def test_categorize_hematology():
    assert _categorize_marker("Hemoglobin") == "hematology"


def test_categorize_cardiovascular():
    assert _categorize_marker("LDL Cholesterol") == "cardiovascular"


def test_categorize_glucose():
    assert _categorize_marker("HbA1c") == "glucose_metabolism"


def test_categorize_liver():
    assert _categorize_marker("ALT") == "liver"


def test_categorize_kidney():
    assert _categorize_marker("Creatinine") == "kidney"


def test_categorize_thyroid():
    assert _categorize_marker("TSH") == "thyroid"


def test_categorize_case_insensitive():
    assert _categorize_marker("HEMOGLOBIN") == "hematology"


def test_categorize_unknown():
    assert _categorize_marker("FooBarXyz") == "other"
