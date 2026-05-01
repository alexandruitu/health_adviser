"""
Biomarker extraction and categorization helpers.
"""
import io
import json
import os
from pathlib import Path

from db import _db, _ensure_biomarker_tables

from paths import BIOMARKERS_CONFIG_PATH

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


def _load_biomarkers_config() -> dict:
    if BIOMARKERS_CONFIG_PATH.exists():
        with open(BIOMARKERS_CONFIG_PATH) as f:
            return json.load(f)
    return {}


def _extract_biomarkers_via_claude(pdf_bytes: bytes) -> dict:
    """Extract biomarkers from a PDF using Claude API."""
    import anthropic
    from pypdf import PdfReader
    from fastapi import HTTPException

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
