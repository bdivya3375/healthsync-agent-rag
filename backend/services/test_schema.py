"""
Test script to verify all 3 parsers work correctly
against the actual hospital data files.
"""

import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.json_parser import parse_json
from services.xml_parser import parse_xml
from services.csv_parser import parse_csv


def test_all_parsers():
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

    # --- Test JSON Parser (Hospital A) ---
    print("=" * 60)
    print("TESTING JSON PARSER (Hospital A)")
    print("=" * 60)
    json_patients = parse_json(os.path.join(data_dir, 'hospital_A.json'))
    print(f"Total patients parsed: {len(json_patients)}")
    if json_patients:
        p = json_patients[0]
        print(f"  Sample: {p.patient_id} | {p.name} | Age: {p.age} | "
              f"Gender: {p.gender} | Blood: {p.blood_group}")
        print(f"  Allergies: {p.allergies}")
        print(f"  Medications: {p.medications}")
        print(f"  Diagnoses: {p.diagnosis}")
        if p.lab_results:
            print(f"  Lab - Glucose: {p.lab_results.fasting_blood_glucose_mgdl}, "
                  f"BP: {p.lab_results.blood_pressure}, "
                  f"HbA1c: {p.lab_results.hba1c_pct}")
        print(f"  Visits: {p.visit_history}")
        print(f"  Source: {p.source_hospital}")

    # --- Test XML Parser (Hospital B) ---
    print("\n" + "=" * 60)
    print("TESTING XML PARSER (Hospital B)")
    print("=" * 60)
    xml_patients = parse_xml(os.path.join(data_dir, 'hospital_B.xml'))
    print(f"Total patients parsed: {len(xml_patients)}")
    if xml_patients:
        p = xml_patients[0]
        print(f"  Sample: {p.patient_id} | {p.name} | Age: {p.age} | "
              f"Gender: {p.gender} | Blood: {p.blood_group}")
        print(f"  Allergies: {p.allergies}")
        print(f"  Medications: {p.medications}")
        print(f"  Diagnoses: {p.diagnosis}")
        if p.lab_results:
            print(f"  Lab - Glucose: {p.lab_results.fasting_blood_glucose_mgdl}, "
                  f"BP: {p.lab_results.blood_pressure}, "
                  f"HbA1c: {p.lab_results.hba1c_pct}")
        print(f"  Visits: {p.visit_history}")
        print(f"  Source: {p.source_hospital}")

    # --- Test CSV Parser (Hospital C) ---
    print("\n" + "=" * 60)
    print("TESTING CSV PARSER (Hospital C)")
    print("=" * 60)
    csv_patients = parse_csv(os.path.join(data_dir, 'hospital_C.csv'))
    print(f"Total patients parsed: {len(csv_patients)}")
    if csv_patients:
        p = csv_patients[0]
        print(f"  Sample: {p.patient_id} | {p.name} | Age: {p.age} | "
              f"Gender: {p.gender} | Blood: {p.blood_group}")
        print(f"  Allergies: {p.allergies}")
        print(f"  Medications: {p.medications}")
        print(f"  Diagnoses: {p.diagnosis}")
        if p.lab_results:
            print(f"  Lab - Glucose: {p.lab_results.fasting_blood_glucose_mgdl}, "
                  f"BP: {p.lab_results.blood_pressure}, "
                  f"HbA1c: {p.lab_results.hba1c_pct}")
        print(f"  Visits: {p.visit_history}")
        print(f"  Source: {p.source_hospital}")

    # --- Summary ---
    total = len(json_patients) + len(xml_patients) + len(csv_patients)
    print("\n" + "=" * 60)
    print(f"ALL PARSERS PASSED — {total} total patients ingested")
    print(f"  Hospital A (JSON): {len(json_patients)}")
    print(f"  Hospital B (XML):  {len(xml_patients)}")
    print(f"  Hospital C (CSV):  {len(csv_patients)}")
    print("=" * 60)


if __name__ == "__main__":
    test_all_parsers()
