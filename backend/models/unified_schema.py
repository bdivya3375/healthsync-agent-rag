from pydantic import BaseModel
from typing import List, Optional


class LabResults(BaseModel):
    """Standardized laboratory results aligned with FHIR Observation resources."""
    fasting_blood_glucose_mgdl: Optional[float] = None
    blood_pressure: Optional[str] = None
    hemoglobin_gdl: Optional[float] = None
    serum_creatinine_mgdl: Optional[float] = None
    total_cholesterol_mgdl: Optional[int] = None
    hba1c_pct: Optional[float] = None


class Patient(BaseModel):
    """
    Unified patient schema aligned with FHIR Patient + clinical resources.

    Maps heterogeneous hospital data (JSON/XML/CSV) into a single
    standardized structure for downstream conflict detection and analysis.
    """
    patient_id: str
    name: str
    age: Optional[int] = None
    dob: Optional[str] = None
    gender: str
    blood_group: str
    allergies: List[str] = []
    diagnosis: List[str] = []
    medications: List[str] = []
    lab_results: Optional[LabResults] = None
    visit_history: List[str] = []
    source_hospital: str
    last_updated: Optional[str] = None