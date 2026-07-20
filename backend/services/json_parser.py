"""
JSON Parser — Hospital A Data Ingestion

Parses hospital_A.json which contains an array of patient records
wrapped under a top-level "patients" key.

Field mapping (Hospital A → Unified Schema):
    patientId           → patient_id
    fullName            → name
    ageYears            → age
    sex                 → gender
    bloodType           → blood_group
    knownAllergies      → allergies
    diagnosedConditions → diagnosis
    currentMedications  → medications
    labResults          → lab_results (nested object)
    visitHistory        → visit_history
    sourceHospital      → source_hospital
    recordCreated       → last_updated
"""

import json
from datetime import datetime
from typing import List

from models.unified_schema import Patient, LabResults


def _normalize_gender(raw: str) -> str:
    """Normalize gender values to FHIR standard codes (Male/Female/Other/Unknown)."""
    mapping = {"male": "Male", "female": "Female", "m": "Male", "f": "Female"}
    return mapping.get(raw.strip().lower(), "Unknown")


def _filter_allergies(allergy_list: list) -> List[str]:
    """Remove placeholder 'None' entries from allergy lists."""
    return [a for a in allergy_list if a and a.strip().lower() != "none"]


def _parse_lab_results(lab_data: dict) -> LabResults:
    """Map Hospital A lab result keys to the unified LabResults schema."""
    return LabResults(
        fasting_blood_glucose_mgdl=lab_data.get("fastingBloodGlucose_mgdL"),
        blood_pressure=lab_data.get("bloodPressure"),
        hemoglobin_gdl=lab_data.get("hemoglobin_gdL"),
        serum_creatinine_mgdl=lab_data.get("serumCreatinine_mgdL"),
        total_cholesterol_mgdl=lab_data.get("totalCholesterol_mgdL"),
        hba1c_pct=lab_data.get("hba1c_pct"),
    )


def parse_json(file_path: str) -> List[Patient]:
    """
    Parse Hospital A JSON file and return a list of unified Patient objects.

    The JSON structure is:
    {
        "patients": [
            { "patientId": "...", "fullName": "...", ... },
            ...
        ]
    }
    """
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("patients", [])
    patients = []

    for record in records:
        lab_data = record.get("labResults", {})

        patient = Patient(
            patient_id=record.get("patientId", ""),
            name=record.get("fullName", ""),
            age=record.get("ageYears"),
            gender=_normalize_gender(record.get("sex", "")),
            blood_group=record.get("bloodType", ""),
            allergies=_filter_allergies(record.get("knownAllergies", [])),
            diagnosis=record.get("diagnosedConditions", []),
            medications=record.get("currentMedications", []),
            lab_results=_parse_lab_results(lab_data) if lab_data else None,
            visit_history=record.get("visitHistory", []),
            source_hospital=record.get("sourceHospital", "Hospital_A"),
            last_updated=record.get("recordCreated", datetime.now().isoformat()),
        )
        patients.append(patient)

    return patients
