# HealthSync Conflict Injection & Audit Flow Explanation

This document explains the code we created and modified to ensure that the Clinical AI Agents can reliably test and audit conflicted patient data. We follow the logical flow of how a patient enters the system, how conflicts are injected, and how the AI retrieves history to audit them.

## 1. Simulating an Admission (Frontend to Backend)
**Files:** `static/js/app.js` and `backend/main.py`

When you click **Simulate Admission** in the dashboard, the frontend calls the `POST /api/v1/admit` endpoint in `backend/main.py`. This endpoint immediately routes the request to our core simulation engine:
```python
@app.post("/api/v1/admit")
async def admit_patient(db: Session = Depends(get_db)):
    try:
        # Passes control to the hospital simulator
        pending = admit_simulated_patient(db)
```

## 2. The Conflict Injector Engine
**File:** `backend/services/hospital_simulator.py`

This is where the majority of our new logic lives. We restructured the simulator to guarantee a 90% conflict rate by reading directly from `conflict_manifest.json`.

**The Router:**
We created a router function that decides whether to inject a conflict or pass a standard patient.
```python
def admit_simulated_patient(db: Session) -> PendingReport:
    # 90% of the time, route to the new manifest logic to ensure a conflict.
    if random.random() < 0.90:
        return admit_from_manifest(db)
    # 10% of the time, fallback to standard pseudo-random reports.
    return _admit_standard_patient(db)
```

**The Manifest Injection Logic:**
```python
def admit_from_manifest(db: Session) -> PendingReport:
    # 1. Load the manifest file from disk
    manifest_path = os.path.join(os.path.dirname(__file__), "..", "data", "conflict_manifest.json")
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    
    # 2. Pick a random conflicted patient from the manifest (e.g., Carlos Joshi)
    conflicted_patients = manifest.get("conflicts", [])
    cp = random.choice(conflicted_patients)
    
    # 3. Find their original "clean" record in the central database using their PID
    base = db.query(PatientRecord).filter(PatientRecord.patient_id == cp["pid"]).first()
    if not base:
        return _admit_standard_patient(db)
```

To create a believable conflict, we package a new `PendingReport` that pretends to come from a different hospital and explicitly overrides the clean fields using the manifest data:
```python
    # Set up the base raw dictionary
    raw = {
        "patient_id": base.patient_id,
        "name": base.name,
        ...
    }

    # 4. Inject the specific conflicts defined in the JSON file
    for conflict in cp.get("conflicts", []):
        field = conflict.get("field")
        # Pretend the incoming conflicting report is from Hospital B or C
        source_hosp = random.choice(["hospital_B", "hospital_C"])
        raw["source_hospital"] = source_hosp.replace("_", " ").title()
        
        # Override the base data with the conflicting data from the manifest
        if field == "blood_group":
            raw["blood_group"] = conflict.get(source_hosp, raw["blood_group"])
        elif field == "medications":
            raw["medications"] = json.dumps(conflict.get(source_hosp, base_meds))
        elif field == "diagnosis":
            raw["diagnosis"] = json.dumps(conflict.get(source_hosp, base_dx))
```
Finally, this `raw` dictionary is saved to the database as a new `PendingReport`.

## 3. The Clinical AI Audit Trigger
**File:** `backend/main.py`

When you click **"Audit Report"**, the frontend hits `GET /api/v1/admissions/{id}/audit`. The AI Orchestrator needs to gather all historical records to compare against the incoming `PendingReport`. It calls the distributed query engine to find history matching the patient's normalized name.

## 4. The Distributed Query Engine (The Bug Fix)
**File:** `backend/services/distributed_query.py`

Previously, the AI failed to detect conflicts because it strictly queried `HospitalAPatient`, `HospitalBPatient`, and `HospitalCPatient` tables, which were entirely empty. The AI assumed the patient was brand new, so there was nothing to conflict against!

We added a critical fallback mechanism to ensure the AI always finds the history:
```python
def fetch_patient_history_across_hospitals(db: Session, normalized_name: str) -> List[dict]:
    # ... (attempts to query Hospital A, B, and C tables)
    
    # THE FIX: If the siloed tables are empty, fall back to the main PatientRecord table
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
```
By adding this fallback, `fetch_patient_history_across_hospitals` successfully pulls the original clean base record we used during the injection phase.

## 5. Conflict Resolution by Agents
**File:** `backend/agents/orchestrator.py`

Because the history is now successfully retrieved:
1. `_detect_conflicts_rule_based()` compares the incoming `PendingReport` (which has the injected conflict from Hospital B) against the `history_records` (which has the original data).
2. The discrepancies (like `B+` vs `B-`) are caught deterministically.
3. These detected conflicts are passed directly into the prompt for **Agent 2 (Conflict Auditor)**.
4. Agent 2 (powered by Ollama) successfully reasons about the context of the conflict and the **Clinical Chief (Agent 3)** synthesizes the final action items for the dashboard.
