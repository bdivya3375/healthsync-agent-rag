# AI-Powered Healthcare Data Integration & Conflict Detection System

This project aims to build a middleware AI system that collects, normalizes, and validates patient data from multiple simulated Electronic Health Record (EHR) systems. It utilizes a multi-agent orchestration approach (CrewAI) to process data, detect duplicates/conflicts, and identify anomalies using basic ML.

## Proposed Architecture & Phases

### Phase 1: Project Setup & Data Simulation
- Initialize a structured Python backend project and a React frontend project.
- Create a `data/` directory with 4 subfolders representing different hospitals.
- Write a data generation script (`scripts/generate_synthetic_data.py`) to populate these folders with synthetic patient profiles (JSON, XML, CSV). We will intentionally introduce duplicates, conflicting diagnoses, and medication mismatches to test the system.

### Phase 2: Core Data Models (Schema Definition)
We will define a simple, unified FHIR-like schema using Pydantic. It is critical that all parsed data is mapped to this exact schema to prevent downstream breakage.
**Minimum Fields:**
- `patient_id`
- `name`
- `dob` (Date of Birth)
- `gender`
- `blood_group`
- `diagnosis`
- `medications`
- `source_hospital`

### Phase 3: Multi-Agent System (CrewAI)
We will use **Groq** (or **Ollama** for local execution) as the primary LLM to drive the agents.
The following agents and tasks will be defined:
- **Ingestion & Conversion Agent**: Reads files from the simulated hospital directories (JSON/XML/CSV) and maps the raw data into the unified Pydantic schema.
- **Validation Agent**: Checks for missing fields or invalid formats (e.g., missing DOB, invalid dates).
- **Conflict Detection Agent (CORE INNOVATION)**: This is the brain of the system.
  - **Matching Logic**: Identifies duplicate records by checking for the `same patient_id` OR matching `(name + dob)`.
  - **Conflict Logic**: Flags conflicts when matched patients have a different `blood_group`, `diagnosis`, or `medications`.
  - **Confidence Scoring**: Applies an AI-driven confidence score to the detected conflicts to move beyond basic rules. For example, recent data receives a higher weight, and more complete records receive a higher weight when resolving or flagging the severity of a mismatch.
- **Insight Agent**: Applies a basic ML model (e.g., `IsolationForest` via scikit-learn) on the aggregated data to flag statistical anomalies in numerical data (e.g., unusual lab result values, if added later).

### Phase 4: API Layer (FastAPI)
- Develop a FastAPI application (`main.py`) to serve as the backend entry point.
- **Endpoints**:
  - `POST /api/v1/process`: Triggers the CrewAI pipeline to process the current data folders.
  - `GET /api/v1/conflicts`: Returns the list of detected conflicts, complete with their confidence scores.
  - `GET /api/v1/patients`: Returns the unified, deduplicated patient records.

### Phase 5: Dashboard (React)
- Build a React frontend (`frontend/`) that connects to the FastAPI backend.
- It will feature:
  - A dashboard to trigger the integration pipeline.
  - Metrics showing total records processed vs. conflicts found.
  - A detailed view highlighting specific conflicts (Patient ID, Conflict Type, Source Systems, Confidence Score).

## Directory Structure
```text
healthcare_system/
├── backend/
│   ├── agents/             # CrewAI agent and task definitions
│   ├── data/               # Simulated hospital data folders
│   ├── models/             # Pydantic schemas (FHIR-like)
│   ├── scripts/            # Synthetic data generators
│   ├── services/           # ML anomaly detection & parsing logic
│   ├── main.py             # FastAPI application
│   └── requirements.txt
└── frontend/               # React application
    ├── src/
    ├── package.json
    └── ...
```

## Verification Plan

### Automated & Manual Verification
- Run the synthetic data generator and manually verify the variations in formats and intentional conflicts.
- Start the FastAPI server and trigger the pipeline.
- Inspect the FastAPI responses to ensure the Conflict Detection Agent correctly identified the planted duplicates and mismatched medications, and verify the confidence score logic.
- Launch the React frontend and verify that the metrics and conflict alerts are correctly visualized and easily readable.
