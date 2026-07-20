"""
PII Redaction Service
=====================
Provides utilities for masking Personally Identifiable Information (PII)
in log outputs and audit trails. Ensures patient names, IDs, and other
sensitive data are not exposed in plain text in system logs.
"""

import re
from typing import Optional


def redact_name(name: str) -> str:
    """
    Redact a patient name for safe logging.
    'James Das' -> 'J***s D*s'
    """
    if not name or len(name) < 2:
        return "***"

    parts = name.strip().split()
    redacted_parts = []
    for part in parts:
        if len(part) <= 2:
            redacted_parts.append(part[0] + "*")
        else:
            redacted_parts.append(part[0] + "*" * (len(part) - 2) + part[-1])
    return " ".join(redacted_parts)


def redact_patient_id(patient_id: str) -> str:
    """
    Redact a patient ID for safe logging.
    'PT1001' -> 'PT***1'
    '14ecdbe1' -> '14***e1'
    """
    if not patient_id or len(patient_id) < 4:
        return "***"
    return patient_id[:2] + "***" + patient_id[-2:]


def redact_dob(dob: str) -> str:
    """
    Redact date of birth.
    '1990-05-14' -> '1990-**-**'
    """
    if not dob:
        return "***"
    # Try to keep just the year
    match = re.match(r'^(\d{4})', dob)
    if match:
        return match.group(1) + "-**-**"
    return "***"


def redact_dict_for_logging(data: dict, fields_to_redact: Optional[list] = None) -> dict:
    """
    Create a redacted copy of a dictionary for safe logging.
    By default redacts: name, patient_name, patient_id, dob, email.
    """
    if fields_to_redact is None:
        fields_to_redact = ["name", "patient_name", "fullName", "patient_id", "dob", "email"]

    redacted = {}
    for key, value in data.items():
        if key in fields_to_redact:
            if isinstance(value, str):
                if key in ("name", "patient_name", "fullName"):
                    redacted[key] = redact_name(value)
                elif key == "patient_id":
                    redacted[key] = redact_patient_id(value)
                elif key == "dob":
                    redacted[key] = redact_dob(value)
                elif key == "email":
                    redacted[key] = _redact_email(value)
                else:
                    redacted[key] = "***"
            else:
                redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted


def _redact_email(email: str) -> str:
    """
    Redact an email address.
    'doctor@hospital.com' -> 'd***r@h***l.com'
    """
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    redacted_local = local[0] + "***" + local[-1] if len(local) > 2 else "***"
    domain_parts = domain.split(".")
    if len(domain_parts) >= 2:
        redacted_domain = domain_parts[0][0] + "***" + domain_parts[0][-1] + "." + ".".join(domain_parts[1:])
    else:
        redacted_domain = "***"
    return f"{redacted_local}@{redacted_domain}"
