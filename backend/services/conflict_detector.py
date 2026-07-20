"""
Conflict Detector — Cross-Hospital Record Discrepancy Engine

Identifies and classifies data conflicts when the same patient
appears in multiple hospital sources with inconsistent records.

Conflict Detection Strategy:
    1. Group patients by normalized name (case-insensitive, trimmed)
    2. For each patient appearing in 2+ sources, perform pairwise
       field comparisons across ALL sources simultaneously
    3. Classify each conflict by clinical severity
    4. Generate structured reports with full source attribution

Detected Conflict Types:
    CRITICAL — blood_group, allergies (life-threatening if wrong)
    HIGH     — medications, diagnosis, gender
    MEDIUM   — lab value discrepancies (glucose, hemoglobin, etc.)
    LOW      — age differences (±1-2 years from rounding/timing)
"""

import re
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from models.unified_schema import Patient
from models.conflict_models import (
    ConflictSeverity,
    ConflictRecord,
    PatientConflictReport,
    ConflictSummary,
)
from services.conflict_resolver import (
    enrich_conflicts_with_recommendations,
    score_hospital_reliability,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration: Thresholds for numeric conflict detection
# ---------------------------------------------------------------------------

# Lab values must differ by more than this threshold to count as a conflict
LAB_THRESHOLDS = {
    "fasting_blood_glucose_mgdl": 5.0,   # mg/dL
    "hemoglobin_gdl": 0.5,               # g/dL
    "serum_creatinine_mgdl": 0.3,        # mg/dL
    "total_cholesterol_mgdl": 5,          # mg/dL
    "hba1c_pct": 0.3,                    # %
}

# Age difference threshold (years) — differences <= this are ignored
AGE_TOLERANCE = 0


# ---------------------------------------------------------------------------
# Matching: Group patients across hospitals by identity
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Normalize patient name for cross-hospital matching."""
    return name.strip().lower()


def group_patients_by_identity(patients: List[Patient]) -> Dict[str, List[Patient]]:
    """
    Group patient records by normalized name.

    Since each hospital uses different ID schemes (PT1000 vs HOSP_C_0001),
    name-based matching is the primary linkage strategy.

    Returns:
        Dict mapping normalized name → list of Patient records from
        different sources.
    """
    groups: Dict[str, List[Patient]] = defaultdict(list)

    for patient in patients:
        key = _normalize_name(patient.name)
        groups[key].append(patient)

    return dict(groups)


# ---------------------------------------------------------------------------
# Conflict Checkers: One function per conflict type
# ---------------------------------------------------------------------------

def _check_blood_group(records: List[Patient]) -> Optional[ConflictRecord]:
    """Detect blood group mismatches (CRITICAL — transfusion safety)."""
    values = {r.source_hospital: r.blood_group for r in records}
    unique = set(values.values())

    if len(unique) > 1:
        return ConflictRecord(
            field="blood_group",
            severity=ConflictSeverity.CRITICAL,
            values_by_source=values,
            description=(
                f"Blood group mismatch across {len(values)} sources: "
                f"{', '.join(f'{src}={val}' for src, val in values.items())}. "
                f"CRITICAL: Wrong blood type can cause fatal transfusion reactions."
            ),
        )
    return None


def _check_gender(records: List[Patient]) -> Optional[ConflictRecord]:
    """Detect gender mismatches (HIGH — affects drug dosing, diagnoses)."""
    values = {r.source_hospital: r.gender for r in records}
    unique = set(values.values())

    if len(unique) > 1:
        return ConflictRecord(
            field="gender",
            severity=ConflictSeverity.HIGH,
            values_by_source=values,
            description=(
                f"Gender mismatch: "
                f"{', '.join(f'{src}={val}' for src, val in values.items())}."
            ),
        )
    return None


def _check_age(records: List[Patient]) -> Optional[ConflictRecord]:
    """Detect age discrepancies (LOW/MEDIUM — may indicate data entry error)."""
    values = {}
    for r in records:
        if r.age is not None:
            values[r.source_hospital] = r.age

    if len(values) < 2:
        return None

    ages = list(values.values())
    spread = max(ages) - min(ages)

    if spread > AGE_TOLERANCE:
        severity = ConflictSeverity.MEDIUM if spread > 3 else ConflictSeverity.LOW
        return ConflictRecord(
            field="age",
            severity=severity,
            values_by_source=values,
            description=(
                f"Age discrepancy of {spread} years: "
                f"{', '.join(f'{src}={val}' for src, val in values.items())}."
            ),
        )
    return None


def _check_allergies(records: List[Patient]) -> Optional[ConflictRecord]:
    """
    Detect allergy list discrepancies (CRITICAL — missing allergy = risk of
    administering a drug the patient is allergic to).
    """
    values = {r.source_hospital: sorted(r.allergies) for r in records}
    sets = {src: frozenset(v) for src, v in values.items()}
    unique = set(sets.values())

    if len(unique) > 1:
        return ConflictRecord(
            field="allergies",
            severity=ConflictSeverity.CRITICAL,
            values_by_source=values,
            description=(
                f"Allergy list conflict across sources. "
                f"Missing allergies could lead to adverse drug reactions."
            ),
        )
    return None


def _parse_medication(med_string: str) -> Tuple[str, str]:
    """
    Parse a medication string into (base_drug_name, strength).

    Examples:
        "Lisinopril 10mg"   -> ("lisinopril", "10mg")
        "Metformin 1000mg"  -> ("metformin", "1000mg")
        "Albuterol Inhaler" -> ("albuterol inhaler", "")
    """
    match = re.match(
        r'^(.+?)\s+(\d+\s*(?:mg|mcg|ml|units?|iu|g))\s*$',
        med_string.strip(), re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().lower(), match.group(2).strip().lower()
    return med_string.strip().lower(), ""


def _check_medications(records: List[Patient]) -> Optional[ConflictRecord]:
    """Detect medication list conflicts (HIGH — drug interaction risk)."""
    values = {r.source_hospital: sorted(r.medications) for r in records}
    sets = {src: frozenset(v) for src, v in values.items()}
    unique = set(sets.values())

    if len(unique) > 1:
        return ConflictRecord(
            field="medications",
            severity=ConflictSeverity.HIGH,
            values_by_source=values,
            description=(
                f"Medication list mismatch. Inconsistent medication records "
                f"may cause drug interaction risks or missed treatments."
            ),
        )
    return None


def _check_medication_dosage(records: List[Patient]) -> List[ConflictRecord]:
    """
    Detect same-drug-different-dose conflicts across hospital sources.

    Catches scenarios where a drug was titrated (e.g. Lisinopril 10mg
    at Hospital A -> 20mg at Metro Clinic) but the EHR systems don't
    know about each other's changes.
    """
    conflicts = []

    # Build per-source drug -> strength maps
    source_drug_maps: Dict[str, Dict[str, str]] = {}
    for r in records:
        drug_map: Dict[str, str] = {}
        for med in r.medications:
            base, strength = _parse_medication(med)
            if strength:
                drug_map[base] = strength
        source_drug_maps[r.source_hospital] = drug_map

    if len(source_drug_maps) < 2:
        return conflicts

    # Find drugs in 2+ sources with different strengths
    all_drug_names: Set[str] = set()
    for dm in source_drug_maps.values():
        all_drug_names.update(dm.keys())

    for drug_name in all_drug_names:
        dose_by_source: Dict[str, str] = {}
        for src, dm in source_drug_maps.items():
            if drug_name in dm:
                dose_by_source[src] = dm[drug_name]

        if len(dose_by_source) < 2:
            continue

        unique_doses = set(dose_by_source.values())
        if len(unique_doses) > 1:
            pairs = ", ".join(f"{src}={dose}" for src, dose in dose_by_source.items())
            conflicts.append(ConflictRecord(
                field="medication_dosage",
                severity=ConflictSeverity.HIGH,
                values_by_source=dose_by_source,
                description=(
                    f"{drug_name.title()} dosage conflict: {pairs}. "
                    f"This may indicate a legitimate dose titration for an "
                    f"uncontrolled condition, or a data entry error."
                ),
            ))

    return conflicts


def _check_diagnosis(records: List[Patient]) -> Optional[ConflictRecord]:
    """Detect diagnosis list conflicts (HIGH — treatment plan depends on it)."""
    values = {r.source_hospital: sorted(r.diagnosis) for r in records}
    sets = {src: frozenset(v) for src, v in values.items()}
    unique = set(sets.values())

    if len(unique) > 1:
        return ConflictRecord(
            field="diagnosis",
            severity=ConflictSeverity.HIGH,
            values_by_source=values,
            description=(
                f"Diagnosis conflict across sources. Different active "
                f"diagnoses may lead to incorrect treatment plans."
            ),
        )
    return None


def _check_lab_values(records: List[Patient]) -> List[ConflictRecord]:
    """
    Detect significant lab value discrepancies (MEDIUM severity).

    Only flags differences exceeding clinically relevant thresholds
    to avoid noise from normal measurement variance.
    """
    conflicts = []

    # Collect lab values per source
    lab_data: Dict[str, Dict] = {}
    for r in records:
        if r.lab_results:
            lab_data[r.source_hospital] = r.lab_results

    if len(lab_data) < 2:
        return conflicts

    # Check each lab metric
    for field_name, threshold in LAB_THRESHOLDS.items():
        values = {}
        for src, lab in lab_data.items():
            val = getattr(lab, field_name, None)
            if val is not None:
                values[src] = val

        if len(values) < 2:
            continue

        nums = list(values.values())
        spread = max(nums) - min(nums)

        if spread > threshold:
            conflicts.append(ConflictRecord(
                field=field_name,
                severity=ConflictSeverity.MEDIUM,
                values_by_source=values,
                description=(
                    f"{field_name} differs by {spread:.1f} across sources "
                    f"(threshold: {threshold}). "
                    f"Values: {', '.join(f'{s}={v}' for s, v in values.items())}."
                ),
            ))

    # Check blood pressure (string comparison)
    bp_values = {}
    for src, lab in lab_data.items():
        if lab.blood_pressure:
            bp_values[src] = lab.blood_pressure

    if len(bp_values) >= 2 and len(set(bp_values.values())) > 1:
        conflicts.append(ConflictRecord(
            field="blood_pressure",
            severity=ConflictSeverity.LOW,
            values_by_source=bp_values,
            description=(
                f"Blood pressure readings differ across sources: "
                f"{', '.join(f'{s}={v}' for s, v in bp_values.items())}."
            ),
        ))

    return conflicts


# ---------------------------------------------------------------------------
# Core Engine
# ---------------------------------------------------------------------------

# All single-result checkers (return Optional[ConflictRecord])
_SINGLE_CHECKERS = [
    _check_blood_group,
    _check_gender,
    _check_age,
    _check_allergies,
    _check_medications,
    _check_diagnosis,
]


def detect_conflicts_for_patient(records: List[Patient]) -> List[ConflictRecord]:
    """
    Run all conflict checks for a group of records belonging to
    the same patient across different hospitals.

    Args:
        records: List of Patient objects (same person, different sources).

    Returns:
        List of ConflictRecord objects for all detected discrepancies.
    """
    if len(records) < 2:
        return []

    conflicts: List[ConflictRecord] = []

    # Run single-result checkers
    for checker in _SINGLE_CHECKERS:
        result = checker(records)
        if result is not None:
            conflicts.append(result)

    # Run multi-result checkers (lab values + medication dosage)
    conflicts.extend(_check_lab_values(records))
    conflicts.extend(_check_medication_dosage(records))

    return conflicts


def detect_conflicts(patients: List[Patient]) -> ConflictSummary:
    """
    Main entry point: Detect all cross-hospital conflicts.

    Groups patients by identity (name), runs comprehensive conflict
    detection, and returns a full summary with severity breakdown.

    Args:
        patients: All patient records from all hospital sources
                  (output of data_pipeline.process_all_data()).

    Returns:
        ConflictSummary with per-patient reports and aggregate stats.
    """
    logger.info("Starting conflict detection on %d records...", len(patients))

    # Step 1: Group records by patient identity
    groups = group_patients_by_identity(patients)
    multi_source = {
        name: recs for name, recs in groups.items() if len(recs) > 1
    }

    logger.info(
        "Found %d unique patients, %d with multi-source records",
        len(groups), len(multi_source),
    )

    # Step 2: Detect conflicts for each multi-source patient
    patient_reports: List[PatientConflictReport] = []
    severity_counts: Dict[str, int] = defaultdict(int)
    field_counts: Dict[str, int] = defaultdict(int)
    total_conflicts = 0

    for name_key, records in sorted(multi_source.items()):
        conflicts = detect_conflicts_for_patient(records)

        if not conflicts:
            continue

        # Build the report
        matched_ids = {r.source_hospital: r.patient_id for r in records}
        has_critical = any(
            c.severity == ConflictSeverity.CRITICAL for c in conflicts
        )

        report = PatientConflictReport(
            patient_name=records[0].name,  # Use original casing
            matched_ids=matched_ids,
            total_sources=len(records),
            conflicts=conflicts,
            has_critical=has_critical,
        )
        patient_reports.append(report)

        # Update aggregate stats
        total_conflicts += len(conflicts)
        for c in conflicts:
            severity_counts[c.severity.value] += 1
            field_counts[c.field] += 1

    # Step 3: Enrich conflicts with clinical recommendations
    logger.info("Generating clinical recommendations...")
    enrich_conflicts_with_recommendations(patient_reports)

    # Step 4: Score hospital reliability
    logger.info("Computing hospital reliability scores...")
    reliability_scores = score_hospital_reliability(patient_reports)

    for score in reliability_scores:
        logger.info(
            "  %s: %.1f%% (Grade %s) — %d agreements, %d disagreements",
            score.hospital, score.overall_score, score.reliability_grade,
            score.agreements, score.disagreements,
        )

    # Step 5: Build summary
    patients_with_conflicts = len(patient_reports)
    total_unique = len(groups)
    conflict_rate = (
        round(patients_with_conflicts / total_unique * 100, 1)
        if total_unique > 0 else 0.0
    )

    summary = ConflictSummary(
        total_unique_patients=total_unique,
        patients_with_conflicts=patients_with_conflicts,
        conflict_rate_pct=conflict_rate,
        total_conflicts=total_conflicts,
        by_severity=dict(severity_counts),
        by_field=dict(field_counts),
        patient_reports=patient_reports,
        hospital_reliability=reliability_scores,
    )

    logger.info("Conflict detection complete:")
    logger.info("  Patients with conflicts: %d / %d (%.1f%%)",
                patients_with_conflicts, total_unique, conflict_rate)
    logger.info("  Total conflicts found: %d", total_conflicts)
    for sev, cnt in sorted(severity_counts.items()):
        logger.info("    %s: %d", sev, cnt)

    return summary


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys
    import os

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    from services.data_pipeline import process_all_data

    # Ingest all data
    patients = process_all_data()

    # Run conflict detection
    summary = detect_conflicts(patients)

    # Print results
    print(f"\n{'=' * 70}")
    print(f" CONFLICT DETECTION & RESOLUTION REPORT")
    print(f"{'=' * 70}")
    print(f" Unique patients:          {summary.total_unique_patients}")
    print(f" Patients with conflicts:  {summary.patients_with_conflicts}")
    print(f" Conflict rate:            {summary.conflict_rate_pct}%")
    print(f" Total conflicts:          {summary.total_conflicts}")
    print(f"{'=' * 70}")

    print(f"\n SEVERITY BREAKDOWN:")
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        count = summary.by_severity.get(sev, 0)
        bar = "#" * min(count, 40)
        print(f"   {sev:10s}: {count:3d}  {bar}")

    print(f"\n FIELD BREAKDOWN:")
    for field, count in sorted(summary.by_field.items(), key=lambda x: -x[1]):
        print(f"   {field:35s}: {count}")

    # --- Hospital Reliability Scores ---
    print(f"\n{'=' * 70}")
    print(f" HOSPITAL RELIABILITY SCORES")
    print(f"{'=' * 70}")
    for score in summary.hospital_reliability:
        grade_bar = "#" * int(score.overall_score / 2.5)
        print(f"\n   {score.hospital}")
        print(f"     Overall Score:  {score.overall_score:.1f}% (Grade: {score.reliability_grade})")
        print(f"     Agreements:     {score.agreements} / {score.total_fields_compared}")
        print(f"     Disagreements:  {score.disagreements}")
        if score.critical_disagreements > 0:
            print(f"     !! CRITICAL ERRORS: {score.critical_disagreements} (blood/allergy mismatches)")
        print(f"     Score Bar:      [{grade_bar:<40s}]")

        # Show per-field reliability
        if score.field_scores:
            print(f"     Field Scores:")
            for field, fscore in sorted(score.field_scores.items(), key=lambda x: x[1]):
                indicator = "OK" if fscore >= 80 else "!!" if fscore < 50 else "?"
                print(f"       {indicator} {field:30s}: {fscore:.0f}%")

    # --- Show CRITICAL conflicts with recommendations ---
    critical_reports = [r for r in summary.patient_reports if r.has_critical]
    if critical_reports:
        print(f"\n{'=' * 70}")
        print(f" CRITICAL CONFLICTS + DOCTOR RECOMMENDATIONS")
        print(f" ({len(critical_reports)} patients need immediate attention)")
        print(f"{'=' * 70}")
        for report in critical_reports[:10]:
            print(f"\n  Patient: {report.patient_name}")
            print(f"  IDs:     {report.matched_ids}")
            for c in report.conflicts:
                if c.severity == ConflictSeverity.CRITICAL:
                    print(f"\n    [{c.severity.value}] {c.field}:")
                    for src, val in c.values_by_source.items():
                        print(f"      {src}: {val}")
                    if c.recommendation:
                        print(f"\n    >> RECOMMENDATION:")
                        print(f"       Action:   {c.recommendation.action}")
                        print(f"       Urgency:  {c.recommendation.urgency}")
                        if c.recommendation.suggested_value is not None:
                            print(f"       Likely Correct Value: {c.recommendation.suggested_value}")
                            print(f"       Confidence: {c.recommendation.confidence}")
                            print(f"       Trusted Source: {c.recommendation.trusted_source}")
                        print(f"       Rationale: {c.recommendation.rationale[:120]}...")

    # --- Show a sample HIGH conflict with recommendation ---
    high_reports = [
        r for r in summary.patient_reports
        if any(c.severity == ConflictSeverity.HIGH for c in r.conflicts)
    ]
    if high_reports:
        print(f"\n{'=' * 70}")
        print(f" SAMPLE HIGH-SEVERITY CONFLICT + RECOMMENDATION")
        print(f"{'=' * 70}")
        sample = high_reports[0]
        print(f"\n  Patient: {sample.patient_name}")
        for c in sample.conflicts:
            if c.severity == ConflictSeverity.HIGH:
                print(f"\n    [{c.severity.value}] {c.field}:")
                for src, val in c.values_by_source.items():
                    print(f"      {src}: {val}")
                if c.recommendation:
                    print(f"\n    >> RECOMMENDATION:")
                    print(f"       Action:   {c.recommendation.action}")
                    print(f"       Urgency:  {c.recommendation.urgency}")
                    if c.recommendation.suggested_value is not None:
                        print(f"       Likely Correct Value: {c.recommendation.suggested_value}")
                        print(f"       Trusted Source: {c.recommendation.trusted_source}")
                break  # Just show one example

    # Export full report as JSON
    output_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "detected_conflicts.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(), f, indent=2, default=str)

    print(f"\n{'=' * 70}")
    print(f" Full report exported to: {output_path}")
    print(f"{'=' * 70}")
