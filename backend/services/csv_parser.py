"""
CSV Parser — Hospital C Data Ingestion

Parses hospital_C.csv which uses pipe (|) delimiters for multi-value
fields and has unique column names.

Field mapping (Hospital C → Unified Schema):
    RECORD_NO            → patient_id
    PATIENT_FULL_NAME    → name
    AGE_AT_VISIT         → age
    GENDER_CODE          → gender
    BLOOD_GRP            → blood_group
    DRUG_ALLERGIES       → allergies       (pipe-delimited)
    PRESCRIBED_DRUGS     → medications     (pipe-delimited)
    ACTIVE_DIAGNOSES     → diagnosis       (pipe-delimited)
    FBS_MGDL             → lab_results.fasting_blood_glucose_mgdl
    BP_MMHG              → lab_results.blood_pressure
    HGB_GDL              → lab_results.hemoglobin_gdl
    CREAT_MGDL           → lab_results.serum_creatinine_mgdl
    CHOL_MGDL            → lab_results.total_cholesterol_mgdl
    HBA1C_PCT            → lab_results.hba1c_pct
    VISIT_DATES          → visit_history   (pipe-delimited)
    DATA_SOURCE          → source_hospital
"""

import csv
from datetime import datetime
from typing import List

from models.unified_schema import Patient, LabResults


def _normalize_gender(raw: str) -> str:
    """Normalize gender codes (M/F) to FHIR standard (Male/Female/Unknown)."""
    mapping = {"m": "Male", "f": "Female", "male": "Male", "female": "Female"}
    return mapping.get(raw.strip().lower(), "Unknown")


def _split_pipe_field(value: str) -> List[str]:
    """Split pipe-delimited multi-value fields, stripping whitespace."""
    if not value or not value.strip():
        return []
    return [item.strip() for item in value.split("|") if item.strip()]


def _filter_allergies(allergy_list: List[str]) -> List[str]:
    """Remove placeholder entries ('None', 'NOT_RECORDED') from allergy lists."""
    placeholders = {"none", "not_recorded", ""}
    return [a for a in allergy_list if a.strip().lower() not in placeholders]


def _safe_float(value: str):
    """Safely convert string to float, returning None on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: str):
    """Safely convert string to int, returning None on failure."""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _parse_lab_results(row: dict) -> LabResults:
    """Extract lab values from CSV row columns into unified LabResults."""
    return LabResults(
        fasting_blood_glucose_mgdl=_safe_float(row.get("FBS_MGDL")),
        blood_pressure=row.get("BP_MMHG", "").strip() or None,
        hemoglobin_gdl=_safe_float(row.get("HGB_GDL")),
        serum_creatinine_mgdl=_safe_float(row.get("CREAT_MGDL")),
        total_cholesterol_mgdl=_safe_int(row.get("CHOL_MGDL")),
        hba1c_pct=_safe_float(row.get("HBA1C_PCT")),
    )


def parse_csv(file_path: str) -> List[Patient]:
    """
    Parse Hospital C CSV file and return a list of unified Patient objects.

    CSV structure (pipe-delimited multi-values):
    RECORD_NO,PATIENT_FULL_NAME,AGE_AT_VISIT,GENDER_CODE,BLOOD_GRP,...
    HOSP_C_0001,Carlos Joshi,21,F,B-,Aspirin,Montelukast,Depression,...

    Multi-value fields use | as separator (e.g., "Aspirin|Ibuprofen").
    Missing allergies are marked as "NOT_RECORDED".
    """
    patients = []

    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            # Parse age safely
            age = _safe_int(row.get("AGE_AT_VISIT"))

            # Split pipe-delimited fields
            raw_allergies = _split_pipe_field(row.get("DRUG_ALLERGIES", ""))
            medications = _split_pipe_field(row.get("PRESCRIBED_DRUGS", ""))
            diagnoses = _split_pipe_field(row.get("ACTIVE_DIAGNOSES", ""))
            visits = _split_pipe_field(row.get("VISIT_DATES", ""))

            patient = Patient(
                patient_id=row.get("RECORD_NO", "").strip(),
                name=row.get("PATIENT_FULL_NAME", "").strip(),
                age=age,
                gender=_normalize_gender(row.get("GENDER_CODE", "")),
                blood_group=row.get("BLOOD_GRP", "").strip(),
                allergies=_filter_allergies(raw_allergies),
                diagnosis=diagnoses,
                medications=medications,
                lab_results=_parse_lab_results(row),
                visit_history=visits,
                source_hospital=row.get("DATA_SOURCE", "Hospital_C").strip(),
                last_updated=datetime.now().isoformat(),
            )
            patients.append(patient)

    return patients
