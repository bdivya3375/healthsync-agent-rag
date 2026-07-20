"""
FHIR R4 Compliance Layer
========================
Provides conversion utilities to transform internal HealthSync patient
records into HL7 FHIR R4-compliant JSON resources.

Supports:
- Patient resource
- Condition resource (per diagnosis)
- MedicationStatement resource (per medication)
- Bundle resource (wrapping all resources for a patient)

Reference: https://www.hl7.org/fhir/R4/
"""

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any


def _generate_fhir_id() -> str:
    """Generate a FHIR-compliant resource ID."""
    return str(uuid.uuid4())


def to_fhir_patient(
    patient_id: str,
    name: str,
    gender: str,
    dob: Optional[str] = None,
    blood_group: Optional[str] = None,
    allergies: Optional[List[str]] = None,
    source_hospital: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convert internal patient data to a FHIR R4 Patient resource.

    Reference: https://www.hl7.org/fhir/R4/patient.html
    """
    # Parse name into family + given
    name_parts = name.strip().split() if name else ["Unknown"]
    family_name = name_parts[-1] if len(name_parts) > 1 else name_parts[0]
    given_names = name_parts[:-1] if len(name_parts) > 1 else []

    # Map gender to FHIR codes
    gender_map = {
        "male": "male",
        "female": "female",
        "m": "male",
        "f": "female",
        "other": "other",
    }
    fhir_gender = gender_map.get(gender.lower(), "unknown") if gender else "unknown"

    resource = {
        "resourceType": "Patient",
        "id": patient_id,
        "meta": {
            "versionId": "1",
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "source": source_hospital or "HealthSync",
            "profile": ["http://hl7.org/fhir/StructureDefinition/Patient"],
        },
        "identifier": [
            {
                "system": "urn:healthsync:patient-id",
                "value": patient_id,
            }
        ],
        "active": True,
        "name": [
            {
                "use": "official",
                "family": family_name,
                "given": given_names,
                "text": name,
            }
        ],
        "gender": fhir_gender,
    }

    if dob:
        resource["birthDate"] = dob

    # Blood group as an extension (no standard FHIR field for this)
    if blood_group:
        resource["extension"] = [
            {
                "url": "http://hl7.org/fhir/StructureDefinition/patient-bloodGroup",
                "valueCodeableConcept": {
                    "coding": [
                        {
                            "system": "http://loinc.org",
                            "code": "883-9",
                            "display": blood_group,
                        }
                    ],
                    "text": blood_group,
                },
            }
        ]

    return resource


def to_fhir_condition(
    patient_id: str,
    diagnosis: str,
    source_hospital: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convert a diagnosis string to a FHIR R4 Condition resource.

    Reference: https://www.hl7.org/fhir/R4/condition.html
    """
    return {
        "resourceType": "Condition",
        "id": _generate_fhir_id(),
        "meta": {
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "source": source_hospital or "HealthSync",
            "profile": ["http://hl7.org/fhir/StructureDefinition/Condition"],
        },
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                    "display": "Active",
                }
            ]
        },
        "verificationStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                    "code": "confirmed",
                    "display": "Confirmed",
                }
            ]
        },
        "code": {
            "text": diagnosis,
        },
        "subject": {
            "reference": f"Patient/{patient_id}",
        },
        "recordedDate": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def to_fhir_medication_statement(
    patient_id: str,
    medication: str,
    source_hospital: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convert a medication string to a FHIR R4 MedicationStatement resource.

    Reference: https://www.hl7.org/fhir/R4/medicationstatement.html
    """
    return {
        "resourceType": "MedicationStatement",
        "id": _generate_fhir_id(),
        "meta": {
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "source": source_hospital or "HealthSync",
            "profile": ["http://hl7.org/fhir/StructureDefinition/MedicationStatement"],
        },
        "status": "active",
        "medicationCodeableConcept": {
            "text": medication,
        },
        "subject": {
            "reference": f"Patient/{patient_id}",
        },
        "dateAsserted": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def to_fhir_allergy_intolerance(
    patient_id: str,
    allergy: str,
    source_hospital: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convert an allergy string to a FHIR R4 AllergyIntolerance resource.

    Reference: https://www.hl7.org/fhir/R4/allergyintolerance.html
    """
    return {
        "resourceType": "AllergyIntolerance",
        "id": _generate_fhir_id(),
        "meta": {
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "source": source_hospital or "HealthSync",
        },
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                    "code": "active",
                    "display": "Active",
                }
            ]
        },
        "verificationStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
                    "code": "confirmed",
                    "display": "Confirmed",
                }
            ]
        },
        "code": {
            "text": allergy,
        },
        "patient": {
            "reference": f"Patient/{patient_id}",
        },
        "recordedDate": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def to_fhir_bundle(
    patient_id: str,
    name: str,
    gender: str,
    dob: Optional[str] = None,
    blood_group: Optional[str] = None,
    allergies: Optional[List[str]] = None,
    diagnoses: Optional[List[str]] = None,
    medications: Optional[List[str]] = None,
    source_hospital: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a complete FHIR R4 Bundle containing Patient + Conditions +
    MedicationStatements + AllergyIntolerances for a single patient.

    Reference: https://www.hl7.org/fhir/R4/bundle.html
    """
    entries = []

    # Patient resource
    patient_resource = to_fhir_patient(
        patient_id, name, gender, dob, blood_group, allergies, source_hospital
    )
    entries.append({
        "fullUrl": f"urn:uuid:{patient_id}",
        "resource": patient_resource,
    })

    # Condition resources (one per diagnosis)
    for dx in (diagnoses or []):
        condition = to_fhir_condition(patient_id, dx, source_hospital)
        entries.append({
            "fullUrl": f"urn:uuid:{condition['id']}",
            "resource": condition,
        })

    # MedicationStatement resources (one per medication)
    for med in (medications or []):
        med_stmt = to_fhir_medication_statement(patient_id, med, source_hospital)
        entries.append({
            "fullUrl": f"urn:uuid:{med_stmt['id']}",
            "resource": med_stmt,
        })

    # AllergyIntolerance resources (one per allergy)
    for allergy in (allergies or []):
        allergy_resource = to_fhir_allergy_intolerance(patient_id, allergy, source_hospital)
        entries.append({
            "fullUrl": f"urn:uuid:{allergy_resource['id']}",
            "resource": allergy_resource,
        })

    bundle = {
        "resourceType": "Bundle",
        "id": _generate_fhir_id(),
        "meta": {
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
        },
        "type": "collection",
        "total": len(entries),
        "entry": entries,
    }

    return bundle
