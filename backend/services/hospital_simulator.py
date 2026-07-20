"""
Hospital Simulator -- Simulated Walk-in Admissions

Generates synthetic incoming clinical reports for patient admissions.
Selects an existing patient from the database and simulates them checking
into the clinic with a new medical report that has intentional variations
(blood group, drugs, diagnoses, or dose escalation) compared to their
historical records.
"""

import random
import json
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from database.models import PatientRecord, PendingReport, HospitalAPatient, HospitalBPatient, HospitalCPatient

# ── Template data for generating realistic records ──────────────

CLINIC_NAMES = [
    "Hospital A",
    "Hospital B",
    "Hospital C"
]

BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

DIAGNOSES = [
    "Type 2 Diabetes", "Hypertension", "Asthma", "COPD",
    "Coronary Artery Disease", "Atrial Fibrillation", "Osteoarthritis",
    "Chronic Kidney Disease", "Hypothyroidism", "Migraine",
    "Anxiety Disorder", "Iron Deficiency Anemia", "Heart Failure",
    "GERD", "Obesity", "Depression"
]

MEDICATIONS = [
    "Metformin 500mg", "Lisinopril 10mg", "Amlodipine 5mg",
    "Atorvastatin 20mg", "Metoprolol 50mg", "Omeprazole 20mg",
    "Levothyroxine 50mcg", "Albuterol Inhaler", "Aspirin 81mg",
    "Insulin Glargine", "Losartan 50mg", "Hydrochlorothiazide 25mg",
    "Sertraline 50mg", "Pantoprazole 40mg"
]

GENDERS = ["Male", "Female"]

# Realistic dose escalation pairs for chronic disease management.
# Simulates "last doc gave 10mg, issue still there, new doc gave 20mg".
DOSE_ESCALATION_MAP = {
    "Metformin 500mg":     "Metformin 1000mg",      # Uncontrolled Type 2 Diabetes
    "Lisinopril 10mg":     "Lisinopril 20mg",       # Uncontrolled Hypertension
    "Amlodipine 5mg":      "Amlodipine 10mg",       # Persistent high BP
    "Atorvastatin 20mg":   "Atorvastatin 40mg",     # High cholesterol not responding
    "Metoprolol 50mg":     "Metoprolol 100mg",      # Tachycardia / heart rate control
    "Losartan 50mg":       "Losartan 100mg",        # Hypertension / renal protection
    "Sertraline 50mg":     "Sertraline 100mg",      # Inadequate depression response
    "Levothyroxine 50mcg": "Levothyroxine 75mcg",   # TSH still elevated
}


def _random_dob() -> str:
    year = random.randint(1945, 2005)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year}-{month:02d}-{day:02d}"


def _generate_completely_new_report(clinic_name: str) -> Dict[str, Any]:
    """Generate a completely new patient profile for a new admission."""
    first_names = ["Carlos", "Wei", "James", "Robert", "Kavya", "Ashley", "Smita", "Rohit", "Lakshmi", "Arjun", "Ritu", "Priya"]
    last_names = ["Joshi", "Wilson", "Das", "Kumar", "Singh", "Krishnan", "Shah", "Garcia", "Bose", "Patel", "Reddy", "Menon"]
    name = f"{random.choice(first_names)} {random.choice(last_names)}"
    
    num_dx = random.randint(1, 2)
    num_meds = random.randint(1, 3)

    return {
        "patient_id": f"ADM_{random.randint(1000, 9999)}",
        "name": name,
        "dob": _random_dob(),
        "gender": random.choice(GENDERS),
        "blood_group": random.choice(BLOOD_GROUPS),
        "diagnosis": json.dumps(random.sample(DIAGNOSES, num_dx)),
        "medications": json.dumps(random.sample(MEDICATIONS, num_meds)),
        "source_hospital": clinic_name,
    }


def _apply_dose_escalation(meds_list: List[str]) -> List[str]:
    """
    Find medications in the list that have a dose escalation path
    and escalate the first one found. Returns the modified list.
    """
    new_meds = meds_list.copy()
    for i, med in enumerate(new_meds):
        if med in DOSE_ESCALATION_MAP:
            new_meds[i] = DOSE_ESCALATION_MAP[med]
            return new_meds
    # No escalatable med found — fall back to swapping one med entirely
    if new_meds:
        new_meds[0] = random.choice([m for m in MEDICATIONS if m not in meds_list])
    return new_meds


def _admit_standard_patient(db: Session) -> PendingReport:
    """
    Fallback for generating a random new walk-in report without relying on the manifest.
    Returns the saved PendingReport object.
    1. Grabbing an existing patient from the database.
    2. Generating a new report for them from an external clinic.
    3. Introducing a mismatch (conflict) with 90% chance:
       - 25% blood group mismatch
       - 25% diagnosis variation
       - 25% medication swap (different drug entirely)
       - 25% dose escalation (same drug, higher dose)
    4. Saving this report to the pending_reports queue in PostgreSQL.
    """
    clinic_name = random.choice(CLINIC_NAMES)
    
    # Try to grab an existing patient from the selected hospital's DB
    if clinic_name == "Hospital A":
        existing = db.query(HospitalAPatient).all()
    elif clinic_name == "Hospital B":
        existing = db.query(HospitalBPatient).all()
    else:
        existing = db.query(HospitalCPatient).all()
        
    if not existing:
        existing = db.query(PatientRecord).all()
    
    if not existing or random.random() < 0.2:
        # Generate a completely new patient report (no history)
        raw = _generate_completely_new_report(clinic_name)
    else:
        # Pick a random patient to "re-admit" with overlapping details
        base = random.choice(existing)
        
        try:
            base_dx = json.loads(base.diagnosis)
        except Exception:
            base_dx = []
            
        try:
            base_meds = json.loads(base.medications)
        except Exception:
            base_meds = []

        raw = {
            "patient_id": base.patient_id,
            "name": base.name,
            "dob": base.dob,
            "gender": base.gender,
            "blood_group": base.blood_group,
            "diagnosis": json.dumps(base_dx),
            "medications": json.dumps(base_meds),
            "source_hospital": clinic_name,
        }

        # 80% chance of introducing at least one clinical conflict
        if random.random() < 0.8:
            choice = random.randint(1, 4)
            if choice == 1:
                # Conflict 1: Blood group mismatch
                raw["blood_group"] = random.choice([bg for bg in BLOOD_GROUPS if bg != base.blood_group])
            elif choice == 2:
                # Conflict 2: Diagnosis variation
                new_dx = base_dx.copy()
                if new_dx:
                    new_dx[0] = random.choice([d for d in DIAGNOSES if d not in base_dx])
                else:
                    new_dx = [random.choice(DIAGNOSES)]
                raw["diagnosis"] = json.dumps(new_dx)
            elif choice == 3:
                # Conflict 3: Medication swap (entirely different drug)
                new_meds = base_meds.copy()
                if new_meds:
                    new_meds[0] = random.choice([m for m in MEDICATIONS if m not in base_meds])
                else:
                    new_meds = [random.choice(MEDICATIONS)]
                raw["medications"] = json.dumps(new_meds)
            else:
                # Conflict 4: Dose escalation (same drug, higher dose)
                new_meds = _apply_dose_escalation(base_meds)
                raw["medications"] = json.dumps(new_meds)

    # Save to the pending admissions queue in PostgreSQL
    pending = PendingReport(
        patient_id=raw["patient_id"],
        name=raw["name"],
        dob=raw["dob"],
        gender=raw["gender"],
        blood_group=raw["blood_group"],
        diagnosis=raw["diagnosis"],
        medications=raw["medications"],
        source_hospital=raw["source_hospital"],
        status="Pending"
    )
    
    db.add(pending)
    db.commit()
    db.refresh(pending)
    
    return pending


def admit_from_manifest(db: Session) -> PendingReport:
    """
    Admit a patient directly from the conflict_manifest.json to ensure conflicts.
    """
    import os
    manifest_path = os.path.join(os.path.dirname(__file__), "..", "data", "conflict_manifest.json")
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    
    conflicted_patients = manifest.get("conflicts", [])
    if not conflicted_patients:
        return _admit_standard_patient(db)
        
    cp = random.choice(conflicted_patients)
    
    base = db.query(PatientRecord).filter(PatientRecord.patient_id == cp["pid"]).first()
    if not base:
        # Fallback if the database is completely empty
        return _admit_standard_patient(db)
        
    try:
        base_dx = json.loads(base.diagnosis)
    except Exception:
        base_dx = []
        
    try:
        base_meds = json.loads(base.medications)
    except Exception:
        base_meds = []
        
    raw = {
        "patient_id": base.patient_id,
        "name": base.name,
        "dob": base.dob,
        "gender": base.gender,
        "blood_group": base.blood_group,
        "diagnosis": json.dumps(base_dx),
        "medications": json.dumps(base_meds),
        "source_hospital": "Hospital B",
    }
    
    for conflict in cp.get("conflicts", []):
        field = conflict.get("field")
        # Randomly choose Hospital B or C to inject the conflict from
        source_hosp = random.choice(["hospital_B", "hospital_C"])
        raw["source_hospital"] = source_hosp.replace("_", " ").title()
        
        if field == "blood_group":
            raw["blood_group"] = conflict.get(source_hosp, raw["blood_group"])
        elif field == "medications":
            raw["medications"] = json.dumps(conflict.get(source_hosp, base_meds))
        elif field == "diagnosis":
            raw["diagnosis"] = json.dumps(conflict.get(source_hosp, base_dx))
            
    pending = PendingReport(
        patient_id=raw["patient_id"],
        name=raw["name"],
        dob=raw["dob"],
        gender=raw["gender"],
        blood_group=raw["blood_group"],
        diagnosis=raw["diagnosis"],
        medications=raw["medications"],
        source_hospital=raw["source_hospital"],
        status="Pending"
    )
    
    db.add(pending)
    db.commit()
    db.refresh(pending)
    
    return pending


def admit_simulated_patient(db: Session) -> PendingReport:
    """
    Main entry point for generating a single new walk-in report.
    90% chance to generate a conflicted report from the manifest.
    10% chance to generate a standard pseudo-random report.
    """
    if random.random() < 0.90:
        return admit_from_manifest(db)
    return _admit_standard_patient(db)

