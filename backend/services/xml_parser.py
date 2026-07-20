"""
XML Parser — Hospital B Data Ingestion

Parses hospital_B.xml which contains multiple <patient_record> elements
under a <HospitalB_PatientRegistry> root.

Field mapping (Hospital B → Unified Schema):
    @patient_id                  → patient_id  (XML attribute)
    patient_name                 → name
    patient_age                  → age
    biological_sex               → gender
    abo_blood_group              → blood_group
    allergy_list/allergy_item    → allergies
    medication_list/drug         → medications
    diagnosis_list/diagnosis     → diagnosis
    laboratory_values/*          → lab_results (nested)
    encounter_dates/encounter    → visit_history
"""

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List

from models.unified_schema import Patient, LabResults


def _normalize_gender(raw: str) -> str:
    """Normalize gender codes (M/F) to FHIR standard (Male/Female/Unknown)."""
    mapping = {"m": "Male", "f": "Female", "male": "Male", "female": "Female"}
    return mapping.get(raw.strip().lower(), "Unknown")


def _filter_allergies(allergy_list: list) -> List[str]:
    """Remove placeholder 'None' entries from allergy lists."""
    return [a for a in allergy_list if a and a.strip().lower() != "none"]


def _parse_lab_results(lab_elem) -> LabResults:
    """Map Hospital B XML lab value tags to the unified LabResults schema."""
    def _float(tag: str):
        val = lab_elem.findtext(tag)
        return float(val) if val is not None else None

    def _int(tag: str):
        val = lab_elem.findtext(tag)
        return int(val) if val is not None else None

    return LabResults(
        fasting_blood_glucose_mgdl=_float("glucose_fasting_mg_per_dl"),
        blood_pressure=lab_elem.findtext("bp_reading"),
        hemoglobin_gdl=_float("hgb_g_per_dl"),
        serum_creatinine_mgdl=_float("creatinine_mg_per_dl"),
        total_cholesterol_mgdl=_int("cholesterol_mg_per_dl"),
        hba1c_pct=_float("glycated_hb_percent"),
    )


def parse_xml(file_path: str) -> List[Patient]:
    """
    Parse Hospital B XML file and return a list of unified Patient objects.

    The XML structure is:
    <HospitalB_PatientRegistry>
        <patient_record patient_id="PT1000">
            <patient_name>...</patient_name>
            <medication_list><drug>...</drug></medication_list>
            ...
        </patient_record>
        ...
    </HospitalB_PatientRegistry>
    """
    tree = ET.parse(file_path)
    root = tree.getroot()

    patients = []

    for record in root.findall("patient_record"):
        # Extract allergy items
        raw_allergies = [
            item.text for item in record.findall("allergy_list/allergy_item")
            if item.text
        ]

        # Extract medications
        medications = [
            drug.text for drug in record.findall("medication_list/drug")
            if drug.text
        ]

        # Extract diagnoses
        diagnoses = [
            diag.text for diag in record.findall("diagnosis_list/diagnosis")
            if diag.text
        ]

        # Extract visit/encounter dates
        visits = [
            enc.text for enc in record.findall("encounter_dates/encounter")
            if enc.text
        ]

        # Parse lab results
        lab_elem = record.find("laboratory_values")
        lab_results = _parse_lab_results(lab_elem) if lab_elem is not None else None

        # Extract age
        age_text = record.findtext("patient_age")
        age = int(age_text) if age_text else None

        patient = Patient(
            patient_id=record.get("patient_id", ""),
            name=record.findtext("patient_name", ""),
            age=age,
            gender=_normalize_gender(record.findtext("biological_sex", "")),
            blood_group=record.findtext("abo_blood_group", ""),
            allergies=_filter_allergies(raw_allergies),
            diagnosis=diagnoses,
            medications=medications,
            lab_results=lab_results,
            visit_history=visits,
            source_hospital="Hospital_B",
            last_updated=datetime.now().isoformat(),
        )
        patients.append(patient)

    return patients
