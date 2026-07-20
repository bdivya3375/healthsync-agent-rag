# HealthSync: Cooperative AI Agents & Real-Time Sync Framework

Welcome to the comprehensive technical architecture guide for **HealthSync**. This document explains the full end-to-end framework, clinical logic patterns, real-time broadcast pipelines, and modern glassmorphic design systems implemented to make HealthSync a state-of-the-art Clinical Decision Support System (CDSS).

---

## 📖 Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Project Repository Structure](#2-project-repository-structure)
3. [File-by-File Breakdown](#3-file-by-file-breakdown)
4. [Data Architecture & Database Schema](#4-data-architecture--database-schema)
5. [Clinical Simulation & Conflict Injection Pipeline](#5-clinical-simulation--conflict-injection-pipeline)
6. [Cooperative 3-Agent Clinical Crew](#6-cooperative-3-agent-clinical-crew)
7. [Dose Escalation Simulation & Mismatch Detection](#7-dose-escalation-simulation--mismatch-detection)
8. [Real-Time SSE Event Stream Infrastructure](#8-real-time-sse-event-stream-infrastructure)
9. [Premium Glassmorphic UI & Visual Design System](#9-premium-glassmorphic-ui--visual-design-system)
10. [Resilient Fallbacks & Offline Capabilities](#10-resilient-fallbacks--offline-capabilities)
11. [Verification & Testing Suite](#11-verification--testing-suite)

---

## 1. Executive Summary

Historically, many clinical software systems relied on simple deterministic rules (such as checking if two strings match) combined with flat LLM prompts to write long clinical summaries. While useful, these pipelines lacked the ability to perform **collaborative multi-stage clinical reasoning**—specifically distinguishing legitimate patient treatment progressions (like dose titrations) from data quality or entry errors.

**HealthSync** solves this by establishing a **3-Agent Cooperative Pipeline** using CrewAI and FastAPI:
- **Upstream Validation**: Before data is compared, it is validated for clinical plausibility.
- **Context-Aware Auditing**: Mismatches are audited dynamically using clinical reasoning to differentiate errors from medication dose adjustments.
- **Executive Synthesis**: Attending physicians receive synthesized, high-confidence, actionable instructions instead of massive paragraphs of raw text.
- **Synchronized Visual Flow**: A Server-Sent Events (SSE) queue broadcasts real-time admission check-ins directly to dashboard terminals.

```
                  ┌────────────────────────────────────────────────┐
                  │           EHR Admissions Simulator             │
                  └───────────────────────┬────────────────────────┘
                                          │
                                   SSE [new_admission]
                                          │
                                          ▼
                         ┌──────────────────────────────────┐
                         │   GET /admissions/stream (SSE)   │
                         └────────────────┬─────────────────┘
                                          │
                                          ▼
 ┌─────────────────────────────────────────────────────────────────────────────────┐
 │                       3-AGENT COOPERATIVE AI PIPELINE                           │
 ├─────────────────────────────────────────────────────────────────────────────────┤
 │                                                                                 │
 │  Step 1: Clinical Ingestion Validator (Plausibility Assessment)                 │
 │          │                                                                      │
 │          ▼                                                                      │
 │  Step 2: Conflict Auditor Analyst (Dose Titration vs. Data Entry Error)         │
 │          │                                                                      │
 │          ▼                                                                      │
 │  Step 3: Chief Medical Decision Advisor (Concise Clinical Actions Synthesis)     │
 │                                                                                 │
 └──────────────────────────────────────┬──────────────────────────────────────────┘
                                        │
                                        ▼
                  ┌────────────────────────────────────────────────┐
                  │       Interactive Merging & Resolution Desk    │
                  └───────────────────────┬────────────────────────┘
                                          │
                         [Sign & Sync to Central PostgreSQL]
                                          │
                                          ▼
                  ┌────────────────────────────────────────────────┐
                  │     Standardized Exports (JSON, XML, CSV)      │
                  └────────────────────────────────────────────────┘
```

---

## 2. Project Repository Structure

HealthSync is clean, modular, and organized, separating clinical business logic from API endpoints, database structures, and static frontend assets:

```
healthcare mark V/
├── backend/
│   ├── agents/
│   │   ├── __init__.py
│   │   └── orchestrator.py           # CrewAI sequential cooperative agent pipeline & fallbacks
│   ├── data/                         # Directory for raw historical clinic data seeds
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py             # SQLAlchemy engine creation & thread-safe sessions
│   │   ├── healthcare.db             # PostgreSQL (SQLite simulation dev file) main database
│   │   └── models.py                 # SQLAlchemy schemas: PatientRecord, ConflictRecord, PendingReport
│   ├── middleware/
│   ├── models/
│   │   ├── __init__.py
│   │   ├── conflict_models.py        # Pydantic schemas for structured reports
│   │   └── unified_schema.py         # Unified FHIR Pydantic schema for Patient, LabResults
│   ├── routes/
│   ├── services/
│   │   ├── __init__.py
│   │   ├── conflict_detector.py      # Core cross-hospital pairing algorithm & lab checks
│   │   ├── conflict_resolver.py      # Doctor-level field merging & update executors
│   │   ├── data_pipeline.py          # Seeding parser reading data/ files into SQLite
│   │   ├── department_mapper.py      # Specialty routing (cardiology, etc.) & confidence scores
│   │   ├── format_exporter.py        # Bi-directional file conversion (JSON, XML, CSV)
│   │   └── hospital_simulator.py     # Walk-in generator, dose titration & conflict injector
│   ├── templates/
│   │   └── index.html                # Mounted static fallback file copy
│   └── main.py                       # FastAPI entrypoint, SSE endpoint, API routing
├── data/                             # Raw seed CSV/JSON/XML data files representing external clinics
├── static/
│   ├── css/
│   │   └── styles.css                # Premium glassmorphic styling system & animations
│   └── js/
│       └── app.js                    # SSE EventSource listener, dashboard UI drivers, DOM handlers
├── templates/
│   └── index.html                    # Unified UI console dashboard (Login, Audits, Database)
├── test_admit.py                     # Command-line integration test tool
└── healthsync_agent_framework.md     # Full architectural documentation (This File)
```

---

## 3. File-by-File Breakdown

### 🖥️ API & Routing Layer
*   **[`backend/main.py`](file:///c:/Users/banda/healthcare%20mark%20V/backend/main.py)**: The central backbone of HealthSync. It boots the FastAPI application, initializes database tables via an asynchronous lifespan context, sets up CORS rules, mounts the static asset directory, and serves the central endpoints:
    *   `POST /api/v1/process`: Seeds patient databases from local files on first-run and runs the main conflict detection pipeline.
    *   `POST /api/v1/admit`: Triggers the walk-in admission simulator and broadcasts the result.
    *   `GET /api/v1/admissions`: Lists pending, waiting walk-in admissions.
    *   `GET /api/v1/admissions/{id}/audit`: Audits a patient by fetching history and running the cooperative **3-Agent CrewAI** pipeline.
    *   `POST /api/v1/admissions/{id}/resolve`: Resolves medical conflicts by merging doctor choices into a standardized PostgreSQL record.
    *   `GET /api/v1/admissions/stream`: The **Server-Sent Events (SSE)** channel that streams real-time admissions using async queues.
    *   `GET /api/v1/export/{patient_id}`: Converts records back to JSON, XML, or CSV on-demand.

### 🧠 Cooperative Clinical AI Agent Layer
*   **[`backend/agents/orchestrator.py`](file:///c:/Users/banda/healthcare%20mark%20V/backend/agents/orchestrator.py)**: Configures the CrewAI cooperative agents. It initializes the local Ollama LLM (`llama3`) and binds the three custom agents: **Ingestion Validator**, **Conflict Auditor**, and **Clinical Chief**. It constructs sequential task configurations (`Process.sequential`), passes upstream output context downstream, cleans up raw markdown formatting using a regex post-processor (`_clean_llm_output`), and provides deterministic, formatted medical backups if the local LLM is offline.

### 💾 Database & Storage Layer
*   **[`backend/database/models.py`](file:///c:/Users/banda/healthcare%20mark%20V/backend/database/models.py)**: Maps database tables to SQLAlchemy models:
    *   `PatientRecord`: Represents unified patient data (ID, name, DOB, gender, blood group, diagnoses, medications, source hospital, timestamp).
    *   `ConflictRecord`: Stores active conflict logs (hospitals, values, department, confidence scores, Chief's recommendation, signatures).
    *   `PendingReport`: Holds incoming, un-audited walk-in patient admissions.
*   **[`backend/database/connection.py`](file:///c:/Users/banda/healthcare%20mark%20V/backend/database/connection.py)**: Establishes SQLite engine parameters and exposes thread-safe, transactional SQLAlchemy sessions (`get_db`) to API endpoints.

### 💊 Clinical Business Logic Services
*   **[`backend/services/hospital_simulator.py`](file:///c:/Users/banda/healthcare%20mark%20V/backend/services/hospital_simulator.py)**: Simulates real-time walk-in admissions. It chooses a patient, pulls historical records, and has an 80% chance of injecting a conflict (blood mismatch, diagnosis shift, medication swap, or a **dose titration**). The simulated report is then saved to the pending queue and broadcasted via SSE.
*   **[`backend/services/conflict_detector.py`](file:///c:/Users/banda/healthcare%20mark%20V/backend/services/conflict_detector.py)**: Executes identity matches across hospitals. It groups patients by normalized name, performs pairwise checks across all connected sources, parses medications using regex, and flags discrepancies (critical blood groups, high-severity medications/diagnoses, and lab values exceeding safety thresholds).
*   **[`backend/services/conflict_resolver.py`](file:///c:/Users/banda/healthcare%20mark%20V/backend/services/conflict_resolver.py)**: Merges doctor-reviewed fields into standardized unified profiles and updates database records.
*   **[`backend/services/department_mapper.py`](file:///c:/Users/banda/healthcare%20mark%20V/backend/services/department_mapper.py)**: Routes audited conflicts to correct specialties (e.g. blood group mismatches to `cardiology` or `general`, medications to `pharmacy`) and computes source reliability scores based on hospital credibility.
*   **[`backend/services/format_exporter.py`](file:///c:/Users/banda/healthcare%20mark%20V/backend/services/format_exporter.py)**: Performs bi-directional conversion. It formats standardized records back into custom JSON, XML, or CSV structures to mimic third-party hospital formats.

### 🎨 User Interface & Frontend Layout
*   **[`templates/index.html`](file:///c:/Users/banda/healthcare%20mark%20V/templates/index.html)**: The unified single-page dashboard. Designed with premium glassmorphism, it hosts:
    *   *Login Gate*: Clean authentication screen with demographic hints.
    *   *Sidebar Nav*: Interactive tabs for Admissions Queue, Audit Trail Logs, and EHR Database tables.
    *   *Admissions Table & Simulation Console*: Controls for simulated check-ins and queue management.
    *   *Clinical AI Audit Panel*: Real-time slide-over desk showing the 3-Agent steps, action cards, and interactive merging controls.
*   **[`static/js/app.js`](file:///c:/Users/banda/healthcare%20mark%20V/static/js/app.js)**: The browser controller. It manages local sessions, initiates persistent SSE connection channels (`connectSSE`), renders dynamic tables, updates alert banners, displays agent cards, and handles form syncs.
*   **[`static/css/styles.css`](file:///c:/Users/banda/healthcare%20mark%20V/static/css/styles.css)**: The styling core. Uses a premium modern color palette, sleek dark-mode glass panels, turquoise glows, amber titration highlights (`.med-dose-conflict`), left-border agent cards, and responsive CSS keyframe animations.

---

## 4. Data Architecture & Database Schema

HealthSync utilizes a dual-model schema design representing patient lifecycles: **Historical EHR Records** (consolidated sources), **Admission Queue Records** (incoming walk-ins), and **Audit Trail Logs** (resolved history).

```
                      DATABASE SCHEMAS
 ┌────────────────────────────────────────────────────────┐
 │ 1. PatientRecord Table (Main standard EHR pool)        │
 ├────────────────────────────────────────────────────────┤
 │ - id (INT, PK)                                         │
 │ - patient_id (VARCHAR, e.g. "PT_1084")                 │
 │ - name (VARCHAR, normalized for linkages)              │
 │ - dob (VARCHAR, ISO-8601 date, e.g., "1978-04-12")     │
 │ - gender (VARCHAR, "Male" / "Female")                  │
 │ - blood_group (VARCHAR, e.g., "AB+")                   │
 │ - diagnosis (JSON Text, e.g., '["Hypertension"]')      │
 │ - medications (JSON Text, e.g., '["Lisinopril 10mg"]') │
 │ - source_hospital (VARCHAR, e.g., "St. Jude Medical")  │
 │ - created_at / last_updated (TIMESTAMP)                │
 └────────────────────────────────────────────────────────┘
                             ▲
                             │ [Merged & Consolidated]
                             │
 ┌────────────────────────────────────────────────────────┐
 │ 2. PendingReport Table (Incoming Walk-in queue)        │
 ├────────────────────────────────────────────────────────┤
 │ - id (INT, PK)                                         │
 │ - patient_id (VARCHAR)                                 │
 │ - name (VARCHAR)                                       │
 │ - dob (VARCHAR)                                        │
 │ - gender (VARCHAR)                                     │
 │ - blood_group (VARCHAR)                                │
 │ - diagnosis (JSON Text)                                │
 │ - medications (JSON Text)                              │
 │ - source_hospital (VARCHAR)                            │
 │ - status (VARCHAR, "Pending" / "Audited")              │
 │ - created_at (TIMESTAMP)                               │
 └────────────────────────────────────────────────────────┘
```

### 📊 Raw Data Formats
Clinics input data in diverse formats to simulate real-world integrations:
- **XML Feed** (from *Metro Health Clinic*):
  ```xml
  <Patient>
      <Demographics>
          <Name>Robert Patel</Name>
          <DOB>1980-11-22</DOB>
          <Gender>Male</Gender>
          <BloodGroup>O+</BloodGroup>
      </Demographics>
      <Clinical>
          <Diagnoses><Diagnosis>Hypertension</Diagnosis></Diagnoses>
          <Medications><Medication>Lisinopril 20mg</Medication></Medications>
      </Clinical>
  </Patient>
  ```
- **JSON Feed** (from *St. Jude Medical*):
  ```json
  {
      "id": "PT_8803",
      "patient_name": "Robert Patel",
      "demographics": { "dob": "1980-11-22", "gender": "Male", "blood": "O+" },
      "active_diagnoses": ["Hypertension"],
      "prescriptions": ["Lisinopril 10mg"]
  }
  ```

---

## 5. Clinical Simulation & Conflict Injection Pipeline

To demonstrate the system's power without requiring complex manual setup, HealthSync is equipped with a high-fidelity walk-in simulator:

```
           SIMULATOR WALK-IN & CONFLICT PIPELINE
             [Clinician clicks 'Simulate Admission']
                               │
                               ▼
            [Fetch random PatientRecord from PostgreSQL]
                               │
                               ▼
          [Generate external source clinic (e.g. Hospital A)]
                               │
            ┌──────────────────┴──────────────────┐
     (20% Pass)                           (80% Mismatch)
            │                                     │
            ▼                                     ▼
   [Admit with identical]                [Inject Mismatch Choice]
         EHR fields                               ├── 25%: Blood mismatch
                                                  ├── 25%: Diagnosis shift
                                                  ├── 25%: Medication swap
                                                  └── 25%: Dose Escalation
                                                               │
                                                               ▼
                                                  [_apply_dose_escalation()]
                                                  (Metformin 500mg -> 1000mg)
                                                               │
                                                               ▼
                                                  [Save to PendingReport Queue]
                                                               │
                                                               ▼
                                                  [Broadcast via SSE Event]
```

### 🔄 How Data Flows on Simulation:
1.  The clinician clicks the **Simulate Admission** button on the top console bar.
2.  The script triggers a `POST` request to `/api/v1/admit`, invoking `admit_simulated_patient(db)` in `hospital_simulator.py`.
3.  **Base Record Selection**: The system searches for existing patient histories. If none are found, it generates a fresh profile. Otherwise, it picks a random profile (e.g., *Robert Patel*) to serve as the historic reference.
4.  **Conflict Injection (80% Probability)**: It sets up an incoming report, introducing a mismatch based on four clinical scenarios:
    *   *Blood group mismatch* (25%): Injects a different blood type (e.g., historical record is `A+`, incoming is `B-`).
    *   *Diagnosis variation* (25%): Swaps or injects a different diagnosis (e.g. replacing `Type 2 Diabetes` with `COPD`).
    *   *Medication swap* (25%): Replaces active medications with unrelated drugs.
    *   *Dose escalation* (25%): Identifies chronic medications and scales the dosage to the next therapeutic tier (e.g. `Lisinopril 10mg` becomes `Lisinopril 20mg`).
5. **Queue Insertion**: The walk-in report is written to the database with a status of `Pending`.
6. **SSE Dispatch**: The database record is formatted and broadcasted asynchronously, instantly updating all active client dashboards.

### 🏥 The Role of Third-Party Clinics (Mercy Family Care, City General, etc.)

In real-world healthcare networks or Health Information Exchanges (HIEs), patient data is highly fragmented. A single patient frequently receives care from multiple unrelated institutions:
1. **Primary Care Clinics** (e.g., *Mercy Family Care*, *Metro Health Clinic*): Where chronic conditions are managed, routine blood works are drawn, and daily prescriptions (such as Lisinopril 10mg) are established.
2. **Acute Care Hospitals** (e.g., *City General Hospital*, *St. Jude Medical*): Where patients present during emergencies or acute episodes (such as hypertensive crises) requiring specialized escalations (such as Lisinopril 20mg).
3. **Outpatient & Diagnostic Centers** (e.g., *Trinity Outpatient*, *Northside Diagnostics*): Where laboratory profiles, imaging, and specialty referrals are generated.

#### How We Simulate These Hospitals:
To model this realistic fragmentation and create cross-hospital mismatches:
*   **Clinic Pool**: In [hospital_simulator.py](file:///c:/Users/banda/healthcare%20mark%20V/backend/services/hospital_simulator.py), we define a list of third-party clinical entities (`CLINIC_NAMES`).
*   **Source Allocation**: Every patient record in the database is tagged with a `source_hospital` string showing where that specific transaction occurred.
*   **Conflict Scenarios**: During simulation, if a patient has a history recorded by `St. Jude Medical`, and then "walks into" a clinic like `Mercy Family Care`, the simulator creates a walk-in report using `Mercy Family Care` as the active `source_hospital`.
*   **Deterministic Filtering**: In [main.py](file:///c:/Users/banda/healthcare%20mark%20V/backend/main.py) under `GET /api/v1/conflicts`, when a physician logs in (e.g., Dr. Sarah Chen from *Hospital B* / *St. Jude Medical*), the system filters conflicts to **only display records that involve the doctor's specific hospital**. This mirrors real-world security standards where doctors only see clinical discrepancies that concern their own network!

---

## 6. Cooperative 3-Agent Clinical Crew

The core intelligence of HealthSync resides in `backend/agents/orchestrator.py`. Rather than relying on a single generalist LLM prompt, the system deploys **three specialized, cooperative agents** that run sequentially. The output of upstream agents is fed dynamically into downstream tasks.

### 🕵️ Agent 1: Clinical Ingestion Validator
*   **Role**: Senior Clinical Data Quality Specialist
*   **Goal**: Assess incoming walk-in records for clinical plausibility before records enter standard clinical queues.
*   **Prompt Reasoning**:
    *   Does the patient's medication list align with their active diagnoses? (e.g., patient is diagnosed with Type 2 Diabetes but is only taking Amlodipine).
    *   Are there clinical contradictions or demographic mismatches (such as a toddler taking geriatric doses)?
*   **Output**: Structured JSON assessment including a `Quality Score` (0–100), `Flags` list, and brief clinical `Notes`.

### 🔍 Agent 2: Conflict Auditor Analyst
*   **Role**: Clinical Pharmacist & Senior Data Auditor
*   **Goal**: Evaluate discrepancies isolated by deterministic checks, specifically distinguishing true clinical updates from data discrepancies.
*   **Prompt Reasoning**:
    *   Uses medical history context to classify medication differences.
    *   Identifies chronological dose progressions (e.g., historical record is `Lisinopril 10mg`, but the new walk-in record is `Lisinopril 20mg`).
    *   Determines if this represents a **legitimate clinical titration** (uncontrolled hypertension) or a **data duplication entry error** (e.g., identical medications recorded under different brand names).
*   **Output**: A clean, per-conflict classification (`LIKELY TITRATION`, `LIKELY ERROR`, or `NEEDS VERIFICATION`) with supportive medical rationales.

### 👑 Agent 3: Chief Medical Decision Advisor
*   **Role**: Chief Medical Officer & Decision Advisor
*   **Goal**: Consolidate upstream findings into precise, high-urgency action items.
*   **Prompt Reasoning**:
    *   Weighs Agent 1's report quality and Agent 2's titration rationales.
    *   **Cooperative Chaining Constraint**: If Agent 1 flags a report as low quality, the Chief adopts a defensive clinical posture (recommending confirmation tests). If Agent 2 confirms a dose titration, the Chief skips recommending diagnostic recheck labs and instead directs the clinician to verify and sync the updated treatment regimen.
*   **Output**: High-fidelity, concise action items mapping `Action`, `Urgency` (`IMMEDIATE`, `SOON`, `ROUTINE`), and `Risk`.

---

## 7. Dose Escalation Simulation & Mismatch Detection

To support advanced auditing, we added a dedicated conflict pathway to simulate and detect same-drug-different-dosage variations.

### 🧪 Dose Escalation Simulation (`services/hospital_simulator.py`)
A `DOSE_ESCALATION_MAP` maps standard chronic medication strengths to their respective next-step treatment doses:
```python
DOSE_ESCALATION_MAP = {
    "Metformin 500mg":     "Metformin 1000mg",      # Uncontrolled Type 2 Diabetes
    "Lisinopril 10mg":     "Lisinopril 20mg",       # Uncontrolled Hypertension
    "Amlodipine 5mg":      "Amlodipine 10mg",       # Persistent high blood pressure
    "Atorvastatin 20mg":   "Atorvastatin 40mg",     # Refractory Hypercholesterolemia
    "Metoprolol 50mg":     "Metoprolol 100mg",      # Tachycardia / Arrhythmia
    "Losartan 50mg":       "Losartan 100mg",        # Advanced Hypertension
    "Sertraline 50mg":     "Sertraline 100mg",      # Clinical Depression progression
    "Levothyroxine 50mcg": "Levothyroxine 75mcg",   # Elevated Thyroid Stimulating Hormone (TSH)
}
```
When simulating admissions, if a walk-in is triggered for an existing patient, the simulator has a 25% chance of selecting this pathway, escalating the patient's existing medication, and queuing the new record.

### 🔬 Regex Mismatch Parsing (`backend/agents/orchestrator.py` / `conflict_detector.py`)
The system parses unstructured medication text using robust regular expressions to split drug names from active strengths:
```python
def _parse_med(med_str: str):
    match = re.match(
        r'^(.+?)\s+(\d+\s*(?:mg|mcg|ml|units?|iu|g))\s*$',
        med_str.strip(), re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().lower(), match.group(2).strip().lower()
    return med_str.strip().lower(), ""
```
This isolates base molecules (e.g., `lisinopril`) and allows the system to compare incoming strengths against historic records. If the drug name matches but the strength differs, it flags a specialized `Medication Dosage Mismatch` conflict.

---

## 8. Real-Time SSE Event Stream Infrastructure

HealthSync utilizes a lightweight, high-performance Server-Sent Events (SSE) broadcast queue to sync client dashboards in real-time without polling overhead.

### 📡 The Broadcast Queue (`backend/main.py`)
Incoming walk-ins are broadcasted asynchronously using an in-memory queue registry:
```python
sse_clients: List[asyncio.Queue] = []

async def broadcast_admission(admission_data: dict):
    disconnected = []
    for queue in sse_clients:
        try:
            await queue.put(admission_data)
        except Exception:
            disconnected.append(queue)
    for q in disconnected:
        sse_clients.remove(q)
```
Dashboard clients connect to the streaming channel via `GET /api/v1/admissions/stream`, spawning a persistent `StreamingResponse` that yields new admissions as structured SSE frames.

### 💻 Client Consumption (`static/js/app.js`)
On initial dashboard load, the client instantiates an `EventSource` stream connection:
```javascript
function connectSSE(session) {
    if (sseSource) sseSource.close();
    sseSource = new EventSource(`${API}/admissions/stream`);

    sseSource.addEventListener('new_admission', (e) => {
        const data = JSON.parse(e.data);
        handleNewAdmissionSSE(data, session);
    });

    sseSource.onerror = (err) => {
        sseSource.close();
        setTimeout(() => connectSSE(session), 3000); // 3-second recovery loop
    };
}
```
Upon receiving `new_admission`, the DOM dynamically prepends the row to the admissions queue table, wiggles the notification count badge, and renders a floating alert banner.

---

## 9. Premium Glassmorphic UI & Visual Design System

HealthSync uses a premium **glassmorphism-themed medical console layout** that is fast, modern, and clean.

```
┌────────────────────────────────────────────────────────────────────────┐
│  HealthSync Portal                                    [Dr. Wilson] [V]  │
├────────────────────────────────────────────────────────────────────────┤
│  [ Admissions Desk (3) ]       [ Ingestion Validator Agent ]           │
│  [ Audit Trail Log     ]       - Quality: 85/100 (GOOD)                │
│  [ Central EHR Pool    ]       - Plausible medication-diagnosis link.  │
│                                                                        │
│  Admissions Queue:             [ Conflict Auditor Analyst ]            │
│  ┌───────────────────────┐     - Classification: LIKELY TITRATION      │
│  │ Name: Robert Patel    │     - Reasoning: Progression of Lisinopril  │
│  │ Source: Metro Clinic  │       from 10mg to 20mg is a titration.     │
│  │ Status: WAITING AUDIT │                                             │
│  └───────────────────────┘     [ Chief Medical Officer ]               │
│                                - Action: Confirm dose with patient.    │
│  Interactive Merging:          - Urgency: SOON | Risk: Under-treatment │
│  [x] Lisinopril 20mg (TITRATION WARNING)                               │
└────────────────────────────────────────────────────────────────────────┘
```

### 🎨 Visual & Aesthetic Features:
*   **Interactive Merging Desk**: Medications flagged with dosage mismatches render inside the checklist grid with dedicated amber outline borders (`.med-dose-conflict`), micro-shadow glows, and pulsing alert icons.
*   **Distinct Left-Border Agent Cards**: Each agent's reasoning block uses specialized vertical left borders to differentiate analysis stages:
    *   *Ingestion Agent*: Solid Turquoise (`#00f5d4`)
    *   *Conflict Auditor Agent*: Warning Amber (`#ffb703`)
    *   *Clinical Chief Agent*: Deep Clinical Purple (`#7209b7`)
*   **Out-of-Box FontAwesome Icons**: No plain text fields are left bare; every action pill, hospital label, and specialty route is supported by dynamic icons.
*   **Cache-Busted Deliveries**: To prevent outdated JS/CSS files from remaining cached in clinician browsers, script/stylesheet imports are versioned dynamically:
    ```html
    <link rel="stylesheet" href="/static/css/styles.css?v=2.0.1">
    <script src="/static/js/app.js?v=2.0.1"></script>
    ```

---

## 10. Resilient Fallbacks & Offline Capabilities

To prevent system lockups during local network outages or when the local Ollama LLM service is offline, we implemented **Clinical Fallback Engines** in `ClinicalAIOrchestrator`:

1.  **Ingestion Validator Fallback**: Performs structural checking on lists. If diagnoses exist but medication sets are entirely empty, it flags the report as `SUSPICIOUS` and logs: *"Expected at least one prescribed medication for active conditions."*
2.  **Conflict Auditor Fallback**: Evaluates conflict types deterministically. If `medication_dosage` is audited, it writes: *"NEEDS VERIFICATION: Medication dosage difference detected. Recommend manual pharmacist review."*
3.  **Clinical Chief Fallback**: Maps the isolated discrepancies to standardized urgency recommendations (e.g., immediate typing tests for blood groups, primary consults for dosage adjustments) to deliver precise clinical directives.

---

## 11. Verification & Testing Suite

### 1. Automated Command-Line Testing
To test the pipeline end-to-end, execute:
```bash
python test_admit.py
```
This utility simulates walk-ins automatically until it generates a conflict, runs the full cooperative agent crew, and prints the chained clinical assessments:
```
============================================================
Simulating admissions until we find a conflict...
============================================================
  Walk-in #18: Smit Joshi from Trinity Outpatient
  Walk-in #19: Robert Patel from Northside Diagnostics

  CONFLICT FOUND for Robert Patel!
  History records: 1
  Conflicts: 1

  Type: Medication Dosage Mismatch
  Values: {
    "St. Jude Medical": "Lisinopril 10mg",
    "Northside Diagnostics": "Lisinopril 20mg"
  }
  
  === CrewAI RECOMMENDATION ===
  Clinical Ingestion Validator Assessment:
  • Quality Score: 85/100
  • High Plausibility: Prescribing Lisinopril 20mg makes clinical sense for the patient's existing history of Hypertension.
  
  Conflict Auditor Reasoning:
  The medication dosage mismatch (Lisinopril 10mg vs Lisinopril 20mg) likely represents a legitimate clinical dose titration/escalation for uncontrolled Hypertension rather than a data entry error, given the chronological progression.
  
  Chief Medical Recommendation:
  • Confirm with the patient if they are currently taking Lisinopril 20mg.
  • Update the primary EHR to reflect the escalated dosage of Lisinopril 20mg.
```

### 2. Manual UI Verification
1.  Launch your browser and go to `http://127.0.0.1:8000`.
2.  Log in as **Dr. Sarah Chen** (specialty: `cardiology`, clinic: `Hospital B`).
3.  Click **Simulate Admission** to queue a new walk-in report.
4.  Observe the real-time **Admissions Alert Banner** slide down and watch the Admissions Queue count increment.
5.  Click **Audit Report** on the newly added patient to open the **AI Agents Audit Desk**.
6.  Verify that all three agent card panels load distinct clinical reasoning steps.
7.  Check the **Interactive Merging Desk** to confirm dosage-mismatched medications are highlighted with amber glow containers and warning indicators.
8.  Select your preferred parameters and click **Sign & Sync to EHR** to write a clean, resolved patient record back to the PostgreSQL database.
