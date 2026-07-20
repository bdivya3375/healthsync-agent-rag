"""
Bi-directional Exporter -- Custom Format Exporter

Converts a unified standard Patient record back into hospital-specific custom formats:
1. Hospital A: JSON format with nested lab results and custom camelCase attributes.
2. Hospital B: Beautiful XML document hierarchy using ElementTree.
3. Hospital C: Pipe-delimited CSV row string.
"""

import json
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import csv
import io
from datetime import datetime
from typing import Dict, Any

from models.unified_schema import Patient


def export_to_hospital_a_json(patient: Patient) -> str:
    """Converts a standard Patient record to Hospital A JSON structure."""
    record = {
        "patientId": patient.patient_id,
        "fullName": patient.name,
        "ageYears": patient.age,
        "sex": "Female" if patient.gender == "Female" else "Male" if patient.gender == "Male" else "Unknown",
        "bloodType": patient.blood_group,
        "knownAllergies": patient.allergies or ["None"],
        "currentMedications": patient.medications or [],
        "diagnosedConditions": patient.diagnosis or [],
        "labResults": {
            "fastingBloodGlucose_mgdL": patient.lab_results.fasting_blood_glucose_mgdl if patient.lab_results else None,
            "bloodPressure": patient.lab_results.blood_pressure if patient.lab_results else None,
            "hemoglobin_gdL": patient.lab_results.hemoglobin_gdl if patient.lab_results else None,
            "serumCreatinine_mgdL": patient.lab_results.serum_creatinine_mgdl if patient.lab_results else None,
            "totalCholesterol_mgdL": patient.lab_results.total_cholesterol_mgdl if patient.lab_results else None,
            "hba1c_pct": patient.lab_results.hba1c_pct if patient.lab_results else None
        },
        "visitHistory": patient.visit_history or [],
        "sourceHospital": "Hospital_A",
        "recordCreated": datetime.now().isoformat()
    }
    return json.dumps(record, indent=2)


def export_to_hospital_b_xml(patient: Patient) -> str:
    """Converts a standard Patient record to Hospital B XML tag structure."""
    root = ET.Element("HospitalB_PatientRegistry")
    record = ET.SubElement(root, "patient_record", patient_id=patient.patient_id)
    
    ET.SubElement(record, "patient_name").text = patient.name
    ET.SubElement(record, "patient_age").text = str(patient.age) if patient.age is not None else ""
    ET.SubElement(record, "biological_sex").text = "F" if patient.gender == "Female" else "M" if patient.gender == "Male" else "U"
    ET.SubElement(record, "abo_blood_group").text = patient.blood_group

    # Allergies
    allergy_list = ET.SubElement(record, "allergy_list")
    if patient.allergies:
        for allergy in patient.allergies:
            ET.SubElement(allergy_list, "allergy_item").text = allergy
    else:
        ET.SubElement(allergy_list, "allergy_item").text = "None"

    # Medications
    med_list = ET.SubElement(record, "medication_list")
    if patient.medications:
        for med in patient.medications:
            ET.SubElement(med_list, "drug").text = med

    # Diagnosis
    diag_list = ET.SubElement(record, "diagnosis_list")
    if patient.diagnosis:
        for diag in patient.diagnosis:
            ET.SubElement(diag_list, "diagnosis").text = diag

    # Lab values
    lab_vals = ET.SubElement(record, "laboratory_values")
    if patient.lab_results:
        ET.SubElement(lab_vals, "glucose_fasting_mg_per_dl").text = (
            str(patient.lab_results.fasting_blood_glucose_mgdl) if patient.lab_results.fasting_blood_glucose_mgdl is not None else ""
        )
        ET.SubElement(lab_vals, "bp_reading").text = patient.lab_results.blood_pressure or ""
        ET.SubElement(lab_vals, "hgb_g_per_dl").text = (
            str(patient.lab_results.hemoglobin_gdl) if patient.lab_results.hemoglobin_gdl is not None else ""
        )
        ET.SubElement(lab_vals, "creatinine_mg_per_dl").text = (
            str(patient.lab_results.serum_creatinine_mgdl) if patient.lab_results.serum_creatinine_mgdl is not None else ""
        )
        ET.SubElement(lab_vals, "cholesterol_mg_per_dl").text = (
            str(patient.lab_results.total_cholesterol_mgdl) if patient.lab_results.total_cholesterol_mgdl is not None else ""
        )
        ET.SubElement(lab_vals, "glycated_hb_percent").text = (
            str(patient.lab_results.hba1c_pct) if patient.lab_results.hba1c_pct is not None else ""
        )

    # Encounters
    encounter_dates = ET.SubElement(record, "encounter_dates")
    if patient.visit_history:
        for visit in patient.visit_history:
            ET.SubElement(encounter_dates, "encounter").text = visit

    # Make pretty printing XML
    rough_string = ET.tostring(root, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


def export_to_hospital_c_csv(patient: Patient) -> str:
    """Converts a standard Patient record to Hospital C pipe-delimited CSV structure."""
    fieldnames = [
        "RECORD_NO", "PATIENT_FULL_NAME", "AGE_AT_VISIT", "GENDER_CODE", "BLOOD_GRP",
        "DRUG_ALLERGIES", "PRESCRIBED_DRUGS", "ACTIVE_DIAGNOSES", "FBS_MGDL",
        "BP_MMHG", "HGB_GDL", "CREAT_MGDL", "CHOL_MGDL", "HBA1C_PCT", "VISIT_DATES",
        "DATA_SOURCE"
    ]
    
    # Format list fields as pipe | separated strings
    allergies_str = "|".join(patient.allergies) if patient.allergies else "NOT_RECORDED"
    medications_str = "|".join(patient.medications) if patient.medications else ""
    diagnoses_str = "|".join(patient.diagnosis) if patient.diagnosis else ""
    visits_str = "|".join(patient.visit_history) if patient.visit_history else ""

    row = {
        "RECORD_NO": patient.patient_id,
        "PATIENT_FULL_NAME": patient.name,
        "AGE_AT_VISIT": str(patient.age) if patient.age is not None else "",
        "GENDER_CODE": "F" if patient.gender == "Female" else "M" if patient.gender == "Male" else "U",
        "BLOOD_GRP": patient.blood_group,
        "DRUG_ALLERGIES": allergies_str,
        "PRESCRIBED_DRUGS": medications_str,
        "ACTIVE_DIAGNOSES": diagnoses_str,
        "FBS_MGDL": str(patient.lab_results.fasting_blood_glucose_mgdl) if patient.lab_results and patient.lab_results.fasting_blood_glucose_mgdl is not None else "",
        "BP_MMHG": patient.lab_results.blood_pressure if patient.lab_results and patient.lab_results.blood_pressure else "",
        "HGB_GDL": str(patient.lab_results.hemoglobin_gdl) if patient.lab_results and patient.lab_results.hemoglobin_gdl is not None else "",
        "CREAT_MGDL": str(patient.lab_results.serum_creatinine_mgdl) if patient.lab_results and patient.lab_results.serum_creatinine_mgdl is not None else "",
        "CHOL_MGDL": str(patient.lab_results.total_cholesterol_mgdl) if patient.lab_results and patient.lab_results.total_cholesterol_mgdl is not None else "",
        "HBA1C_PCT": str(patient.lab_results.hba1c_pct) if patient.lab_results and patient.lab_results.hba1c_pct is not None else "",
        "VISIT_DATES": visits_str,
        "DATA_SOURCE": "Hospital_C"
    }

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerow(row)
    return output.getvalue()


def export_patient_by_format(patient: Patient, fmt: str) -> str:
    """Convenience multiplexer for exporting dynamic patient records."""
    fmt = fmt.lower().strip()
    if fmt == "json":
        return export_to_hospital_a_json(patient)
    elif fmt == "xml":
        return export_to_hospital_b_xml(patient)
    elif fmt == "csv":
        return export_to_hospital_c_csv(patient)
    else:
        raise ValueError(f"Unsupported export format: {fmt}")
