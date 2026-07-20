"""
Conflict Resolver — Hospital Reliability Scoring & Clinical Recommendations

Two core responsibilities:
    1. Score each hospital's data reliability based on majority-vote
       agreement patterns across all patient conflicts
    2. Generate actionable clinical recommendations for each conflict,
       suggesting what tests to order and which value is most likely correct

Reliability Scoring Algorithm:
    - For each conflict field, determine the "majority value" (2/3 agree)
    - Hospitals matching the majority get +1 agreement
    - The outlier hospital gets +1 disagreement
    - If all 3 disagree, all get +1 disagreement
    - Score = (agreements / total_comparisons) * 100
    - CRITICAL field disagreements are weighted heavier in grading

Clinical Recommendation Engine:
    - Maps each conflict type to specific medical actions
    - Determines urgency based on severity
    - Suggests the most likely correct value using majority vote
    - Identifies which hospital is the trusted source
"""

import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from models.conflict_models import (
    ConflictSeverity,
    ConflictRecord,
    ClinicalRecommendation,
    HospitalReliabilityScore,
    PatientConflictReport,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Clinical Recommendation Templates
# ---------------------------------------------------------------------------

RECOMMENDATION_TEMPLATES = {
    "blood_group": {
        "action": "Order ABO/Rh blood typing test immediately",
        "urgency": "IMMEDIATE",
        "rationale": (
            "Blood group mismatch is life-threatening. An incorrect blood type "
            "on record can lead to fatal hemolytic transfusion reactions. "
            "A fresh blood typing test is mandatory before any transfusion "
            "or surgical procedure."
        ),
    },
    "allergies": {
        "action": "Conduct comprehensive allergy assessment (skin prick test / IgE panel)",
        "urgency": "IMMEDIATE",
        "rationale": (
            "Missing or incorrect allergy records pose a direct risk of "
            "anaphylaxis or severe adverse drug reactions. All listed allergies "
            "across sources should be treated as active until clinically "
            "ruled out through proper allergy testing."
        ),
    },
    "medications": {
        "action": "Perform medication reconciliation with patient interview",
        "urgency": "SOON",
        "rationale": (
            "Medication list discrepancies can lead to dangerous drug "
            "interactions, duplicate therapy, or missed critical medications. "
            "A pharmacist-led medication reconciliation with the patient "
            "is recommended to establish the accurate current regimen."
        ),
    },
    "diagnosis": {
        "action": "Schedule clinical review with attending physician",
        "urgency": "SOON",
        "rationale": (
            "Conflicting diagnoses across hospital records may indicate "
            "evolving conditions, misdiagnosis, or data entry errors. "
            "A clinical review of the patient's full history and current "
            "symptoms is needed to confirm the active diagnosis list."
        ),
    },
    "gender": {
        "action": "Verify patient demographics against government-issued ID",
        "urgency": "SOON",
        "rationale": (
            "Gender affects drug dosing calculations, reference ranges "
            "for lab values, and screening recommendations. Verify against "
            "the patient's official identification documents."
        ),
    },
    "age": {
        "action": "Verify date of birth from patient's official ID document",
        "urgency": "ROUTINE",
        "rationale": (
            "Age discrepancies are often caused by data entry errors or "
            "different recording dates. Confirm the patient's actual date "
            "of birth to ensure correct age-based clinical decisions."
        ),
    },
    "fasting_blood_glucose_mgdl": {
        "action": "Order repeat fasting blood glucose test",
        "urgency": "SOON",
        "rationale": (
            "Fasting glucose values differ significantly across sources. "
            "A fresh fasting glucose test will provide the current accurate "
            "reading for diabetes management decisions."
        ),
    },
    "hemoglobin_gdl": {
        "action": "Order complete blood count (CBC) panel",
        "urgency": "SOON",
        "rationale": (
            "Hemoglobin discrepancies may indicate changing anemia status "
            "or lab measurement errors. A fresh CBC will establish the "
            "current hemoglobin level."
        ),
    },
    "serum_creatinine_mgdl": {
        "action": "Order renal function panel (BMP/CMP)",
        "urgency": "SOON",
        "rationale": (
            "Creatinine discrepancies affect kidney function staging (eGFR). "
            "Repeat testing is needed to accurately assess current renal status "
            "and adjust nephrotoxic drug dosing."
        ),
    },
    "total_cholesterol_mgdl": {
        "action": "Order fasting lipid panel",
        "urgency": "ROUTINE",
        "rationale": (
            "Cholesterol values vary with diet and testing conditions. "
            "A standardized fasting lipid panel will provide accurate "
            "values for cardiovascular risk assessment."
        ),
    },
    "hba1c_pct": {
        "action": "Order HbA1c test",
        "urgency": "SOON",
        "rationale": (
            "HbA1c reflects 3-month average blood sugar control. "
            "Discrepancies may indicate lab calibration differences "
            "or changing glycemic control. A fresh test provides the "
            "most accurate current reading."
        ),
    },
    "blood_pressure": {
        "action": "Perform standardized blood pressure measurement (3 readings, seated)",
        "urgency": "ROUTINE",
        "rationale": (
            "Blood pressure naturally varies between visits and readings. "
            "A standardized measurement protocol will establish the "
            "patient's true baseline for hypertension management."
        ),
    },
}


# ---------------------------------------------------------------------------
# Majority Vote Logic
# ---------------------------------------------------------------------------

def _find_majority_value(values_by_source: Dict[str, Any]) -> Tuple[Optional[Any], str, List[str]]:
    """
    Determine the majority value from hospital sources.

    Returns:
        Tuple of (majority_value, confidence, list_of_agreeing_sources)
        - majority_value: The value most sources agree on (None if all differ)
        - confidence: "HIGH" (unanimous-1), "MODERATE" (simple majority), "LOW" (no majority)
        - agreeing_sources: List of hospitals that have the majority value
    """
    if not values_by_source:
        return None, "LOW", []

    # For list values, convert to comparable form
    def normalize(val):
        if isinstance(val, list):
            return tuple(sorted(val))
        return val

    normalized = {src: normalize(val) for src, val in values_by_source.items()}
    counter = Counter(normalized.values())

    if not counter:
        return None, "LOW", []

    most_common_normalized, count = counter.most_common(1)[0]
    total = len(values_by_source)

    # Find agreeing sources
    agreeing = [src for src, val in normalized.items() if val == most_common_normalized]

    # Find the original (un-normalized) value
    majority_value = values_by_source[agreeing[0]]

    if count == total:
        # All agree — shouldn't be a conflict, but handle gracefully
        return majority_value, "HIGH", agreeing
    elif count > total / 2:
        # True majority exists
        confidence = "HIGH" if count >= total - 1 else "MODERATE"
        return majority_value, confidence, agreeing
    else:
        # No majority — all sources disagree
        return None, "LOW", []


def _find_outlier_sources(
    values_by_source: Dict[str, Any],
    agreeing_sources: List[str],
) -> List[str]:
    """Return sources that disagree with the majority."""
    return [src for src in values_by_source if src not in agreeing_sources]


# ---------------------------------------------------------------------------
# Recommendation Generator
# ---------------------------------------------------------------------------

def generate_recommendation(conflict: ConflictRecord) -> ClinicalRecommendation:
    """
    Generate a clinical recommendation for a specific conflict.

    Uses majority-vote analysis to suggest the most likely correct value
    and identifies which hospital is the trusted source.
    """
    template = RECOMMENDATION_TEMPLATES.get(conflict.field, {
        "action": f"Review and verify {conflict.field} with clinical team",
        "urgency": "ROUTINE",
        "rationale": f"Conflicting {conflict.field} values detected across sources.",
    })

    # Determine majority value
    majority_val, confidence, agreeing = _find_majority_value(conflict.values_by_source)
    outliers = _find_outlier_sources(conflict.values_by_source, agreeing)

    # Build the trusted source description
    if agreeing:
        trusted_source = f"{', '.join(agreeing)} (majority agreement)"
    else:
        trusted_source = "No clear majority — all sources differ"

    # Enhance rationale with specific guidance
    rationale = template["rationale"]
    if outliers:
        rationale += (
            f" NOTE: {', '.join(outliers)} reported a different value "
            f"than the majority. Prioritize data from {', '.join(agreeing)} "
            f"until verification is complete."
        )

    return ClinicalRecommendation(
        action=template["action"],
        urgency=template["urgency"],
        rationale=rationale,
        suggested_value=majority_val,
        confidence=confidence,
        trusted_source=trusted_source,
    )


# ---------------------------------------------------------------------------
# Hospital Reliability Scorer
# ---------------------------------------------------------------------------

def _score_to_grade(score: float, critical_misses: int) -> str:
    """
    Convert reliability score to a letter grade.

    Critical disagreements (blood group, allergies) cause automatic
    grade penalties because those errors are life-threatening.
    """
    # Penalize for critical field errors
    if critical_misses >= 3:
        return "F"
    if critical_misses >= 2:
        return max("D", _raw_grade(score))  # Can't be better than D

    return _raw_grade(score)


def _raw_grade(score: float) -> str:
    """Map score 0-100 to letter grade."""
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


def score_hospital_reliability(
    patient_reports: List[PatientConflictReport],
) -> List[HospitalReliabilityScore]:
    """
    Score each hospital's data reliability based on how often it
    agrees with the majority across all patient conflicts.

    Algorithm:
        1. For each conflict across all patients, find the majority value
        2. Hospitals agreeing with the majority get +1 agreement
        3. Outlier hospitals get +1 disagreement
        4. Score = (agreements / total_comparisons) * 100
        5. Apply grade penalties for CRITICAL field outliers

    Returns:
        List of HospitalReliabilityScore, one per hospital source.
    """
    # Track per-hospital stats
    hospital_stats: Dict[str, Dict] = defaultdict(lambda: {
        "agreements": 0,
        "disagreements": 0,
        "critical_disagreements": 0,
        "total": 0,
        "field_agree": defaultdict(int),
        "field_total": defaultdict(int),
    })

    for report in patient_reports:
        for conflict in report.conflicts:
            _, confidence, agreeing = _find_majority_value(conflict.values_by_source)
            outliers = _find_outlier_sources(conflict.values_by_source, agreeing)
            is_critical = conflict.severity == ConflictSeverity.CRITICAL

            # Score each hospital involved in this conflict
            for src in conflict.values_by_source:
                stats = hospital_stats[src]
                stats["total"] += 1
                stats["field_total"][conflict.field] += 1

                if src in agreeing and confidence != "LOW":
                    stats["agreements"] += 1
                    stats["field_agree"][conflict.field] += 1
                elif src in outliers:
                    stats["disagreements"] += 1
                    if is_critical:
                        stats["critical_disagreements"] += 1
                else:
                    # No clear majority — count as partial disagreement
                    stats["disagreements"] += 1

    # Build score objects
    scores = []
    for hospital, stats in sorted(hospital_stats.items()):
        total = stats["total"]
        if total == 0:
            continue

        overall = round((stats["agreements"] / total) * 100, 1)

        # Per-field scores
        field_scores = {}
        for field, field_total in stats["field_total"].items():
            if field_total > 0:
                field_agree = stats["field_agree"].get(field, 0)
                field_scores[field] = round((field_agree / field_total) * 100, 1)

        grade = _score_to_grade(overall, stats["critical_disagreements"])

        scores.append(HospitalReliabilityScore(
            hospital=hospital,
            overall_score=overall,
            total_fields_compared=total,
            agreements=stats["agreements"],
            disagreements=stats["disagreements"],
            critical_disagreements=stats["critical_disagreements"],
            reliability_grade=grade,
            field_scores=field_scores,
        ))

    # Sort by score descending (most reliable first)
    scores.sort(key=lambda s: s.overall_score, reverse=True)

    return scores


def enrich_conflicts_with_recommendations(
    patient_reports: List[PatientConflictReport],
) -> List[PatientConflictReport]:
    """
    Attach clinical recommendations to every conflict in every report.

    This mutates the conflict records in-place, adding the
    recommendation field with actionable clinical guidance.
    """
    for report in patient_reports:
        for conflict in report.conflicts:
            conflict.recommendation = generate_recommendation(conflict)

    return patient_reports
