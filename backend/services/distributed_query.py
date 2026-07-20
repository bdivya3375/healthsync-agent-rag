"""
Distributed Database Query Service

Simulates querying separate, isolated hospital databases (tables in this case)
to build a comprehensive history for the Clinical Agents.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
import json
from typing import List

from database.models import HospitalAPatient, HospitalBPatient, HospitalCPatient

def fetch_patient_history_across_hospitals(db: Session, normalized_name: str) -> List[dict]:
    """
    Query Hospital A, Hospital B, and Hospital C silos for the patient's records.
    Returns a unified list of dicts that the orchestrator agents can process.
    """
    history_records = []

    # Query Hospital A
    hosp_a = db.query(HospitalAPatient).filter(func.lower(HospitalAPatient.name) == normalized_name).all()
    for record in hosp_a:
        history_records.append({
            "source_hospital": record.source_hospital,
            "blood_group": record.blood_group,
            "diagnosis": record.diagnosis, # Stored as JSON string
            "medications": record.medications, # Stored as JSON string
        })

    # Query Hospital B
    hosp_b = db.query(HospitalBPatient).filter(func.lower(HospitalBPatient.name) == normalized_name).all()
    for record in hosp_b:
        history_records.append({
            "source_hospital": record.source_hospital,
            "blood_group": record.blood_group,
            "diagnosis": record.diagnosis,
            "medications": record.medications,
        })

    # Query Hospital C
    hosp_c = db.query(HospitalCPatient).filter(func.lower(HospitalCPatient.name) == normalized_name).all()
    for record in hosp_c:
        history_records.append({
            "source_hospital": record.source_hospital,
            "blood_group": record.blood_group,
            "diagnosis": record.diagnosis,
            "medications": record.medications,
        })

    # Fallback for when the database isn't fully seeded into the split tables
    if not history_records:
        from database.models import PatientRecord
        hosp_general = db.query(PatientRecord).filter(func.lower(PatientRecord.name) == normalized_name).all()
        for record in hosp_general:
            history_records.append({
                "source_hospital": record.source_hospital,
                "blood_group": record.blood_group,
                "diagnosis": record.diagnosis,
                "medications": record.medications,
            })

    return history_records
