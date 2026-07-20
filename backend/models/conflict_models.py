"""
Conflict Detection & Resolution Data Models

Pydantic models for representing detected conflicts, clinical
recommendations, and hospital reliability scores.
"""

from enum import Enum
from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class ConflictSeverity(str, Enum):
    """
    Severity levels for medical data conflicts.

    CRITICAL — Life-threatening if wrong (blood group, allergies)
    HIGH     — Clinically significant (medications, diagnoses, gender)
    MEDIUM   — Requires review (lab value discrepancies)
    LOW      — Minor variance (age off by 1-2 years, rounding)
    """
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ClinicalRecommendation(BaseModel):
    """Actionable clinical suggestion for resolving a conflict."""
    action: str                       # e.g., "Order ABO/Rh blood typing test"
    urgency: str                      # "IMMEDIATE", "SOON", "ROUTINE"
    rationale: str                    # Why this action is needed
    suggested_value: Optional[Any] = None  # Most likely correct value (majority vote)
    confidence: Optional[str] = None  # "HIGH", "MODERATE", "LOW"
    trusted_source: Optional[str] = None   # Which hospital likely has the right data


class ConflictRecord(BaseModel):
    """A single field-level conflict detected across hospital sources."""
    field: str
    severity: ConflictSeverity
    values_by_source: Dict[str, Any]
    description: str
    recommendation: Optional[ClinicalRecommendation] = None


class HospitalReliabilityScore(BaseModel):
    """Reliability metrics for a single hospital data source."""
    hospital: str
    overall_score: float              # 0-100 reliability percentage
    total_fields_compared: int        # How many fields were checked
    agreements: int                   # Fields where this hospital agreed with majority
    disagreements: int                # Fields where this hospital was the outlier
    critical_disagreements: int       # Outlier on CRITICAL fields (blood/allergy)
    reliability_grade: str            # A/B/C/D/F letter grade
    field_scores: Dict[str, float]    # Per-field reliability {"blood_group": 95.0, ...}


class PatientConflictReport(BaseModel):
    """All conflicts detected for a single patient identity."""
    patient_name: str
    matched_ids: Dict[str, str]
    total_sources: int
    conflicts: List[ConflictRecord]
    has_critical: bool = False


class ConflictSummary(BaseModel):
    """Aggregate summary of the entire conflict detection run."""
    total_unique_patients: int
    patients_with_conflicts: int
    conflict_rate_pct: float
    total_conflicts: int
    by_severity: Dict[str, int]
    by_field: Dict[str, int]
    patient_reports: List[PatientConflictReport]
    hospital_reliability: List[HospitalReliabilityScore] = []
