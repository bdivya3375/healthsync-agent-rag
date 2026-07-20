"""
Department Mapper -- Map conflicts to hospital departments

Maps conflict types and diagnosis values to the appropriate
medical department so that conflicts are routed to the right doctors.

Mapping rules:
    - Blood group issues         -> general
    - Heart-related diagnoses    -> cardiology
    - Bone/joint diagnoses       -> orthopedics
    - Brain/nerve diagnoses      -> neurology
    - Lung/breathing diagnoses   -> pulmonology
    - Kidney diagnoses           -> nephrology
    - Diabetes/hormone diagnoses -> endocrinology
    - Cancer diagnoses           -> oncology
    - Medication conflicts       -> pharmacy
    - Default                    -> general
"""

# Keywords that map a diagnosis string to a department
DIAGNOSIS_KEYWORDS = {
    "cardiology": [
        "heart", "cardiac", "cardiovascular", "hypertension",
        "arrhythmia", "angina", "myocardial", "coronary",
        "atrial", "ventricular", "murmur", "palpitation",
    ],
    "orthopedics": [
        "bone", "fracture", "joint", "arthritis", "osteo",
        "spinal", "spine", "scoliosis", "ligament", "tendon",
        "musculoskeletal", "hip replacement", "knee",
    ],
    "neurology": [
        "brain", "neuro", "seizure", "epilepsy", "migraine",
        "stroke", "parkinson", "alzheimer", "dementia", "neuropathy",
        "multiple sclerosis",
    ],
    "pulmonology": [
        "lung", "pulmonary", "asthma", "copd", "bronchitis",
        "pneumonia", "respiratory", "breathing", "emphysema",
    ],
    "nephrology": [
        "kidney", "renal", "dialysis", "nephritis", "ckd",
    ],
    "endocrinology": [
        "diabetes", "thyroid", "insulin", "hormonal", "endocrine",
        "pituitary", "adrenal", "metabolic",
    ],
    "oncology": [
        "cancer", "tumor", "malignant", "carcinoma", "lymphoma",
        "leukemia", "oncology", "chemotherapy",
    ],
    "gastroenterology": [
        "liver", "hepat", "gastric", "intestinal", "bowel",
        "crohn", "colitis", "pancreatitis", "cirrhosis",
    ],
}

# All valid departments for the frontend dropdown
ALL_DEPARTMENTS = [
    "general",
    "cardiology",
    "orthopedics",
    "neurology",
    "pulmonology",
    "nephrology",
    "endocrinology",
    "oncology",
    "gastroenterology",
    "pharmacy",
]

# Hospital reliability scores (simple rule-based)
HOSPITAL_RELIABILITY = {
    # Default scores -- new hospitals get 0.7
    "_default": 0.7,
}


def map_conflict_to_department(conflict_field: str, conflict_values: list = None) -> str:
    """
    Map a conflict to the appropriate department.

    Args:
        conflict_field: The field with the conflict (e.g. "blood_group", "diagnosis")
        conflict_values: The conflicting values (used for diagnosis keyword matching)

    Returns:
        Department name string
    """
    # Blood group conflicts always go to general
    if conflict_field == "blood_group":
        return "general"

    # Medication conflicts go to pharmacy
    if conflict_field == "medications":
        return "pharmacy"

    # For diagnosis conflicts, scan the values for department keywords
    if conflict_field == "diagnosis" and conflict_values:
        for val in conflict_values:
            if isinstance(val, list):
                # Flatten lists of diagnoses
                for item in val:
                    dept = _match_diagnosis(str(item))
                    if dept:
                        return dept
            else:
                dept = _match_diagnosis(str(val))
                if dept:
                    return dept

    # Default
    return "general"


def _match_diagnosis(text: str) -> str:
    """Check a diagnosis string against keyword lists."""
    text_lower = text.lower()
    for department, keywords in DIAGNOSIS_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                return department
    return ""


def get_confidence_score(hospitals: list) -> float:
    """
    Calculate confidence score for a conflict based on hospital reliability.

    Uses simple rule: confidence = max(reliability scores of involved hospitals).
    """
    scores = []
    for h in hospitals:
        score = HOSPITAL_RELIABILITY.get(h, HOSPITAL_RELIABILITY["_default"])
        scores.append(score)
    return max(scores) if scores else 0.5
