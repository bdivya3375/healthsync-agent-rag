# Antigravity Context Export: Healthcare Data Integration System

> **Note to the receiving Antigravity Assistant:**
> Please read this document to understand the context, architecture, and current progress of the project. This acts as our shared memory. 

## Project Overview
We are building an AI-powered middleware system that collects, normalizes, and validates patient data from multiple simulated Electronic Health Record (EHR) systems. It utilizes a multi-agent orchestration approach (CrewAI) to process data, detect duplicates/conflicts, and identify anomalies.

### Tech Stack
- **Backend**: Python, FastAPI
- **AI Orchestration**: CrewAI (using Groq or Ollama as the LLM)
- **Data Validation**: Pydantic
- **Frontend**: React (Planned)

## Current Workspace Structure
```text
healthcare_system/
├── backend/
│   ├── agents/             # CrewAI agent and task definitions
│   │   └── __init__.py
│   ├── data/               # Simulated hospital data folders (ALREADY GENERATED)
│   │   ├── conflict_manifest.json
│   │   ├── hospital_A.json
│   │   ├── hospital_B.xml
│   │   └── hospital_C.csv
│   ├── models/             # Pydantic schemas (FHIR-like)
│   │   └── __init__.py
│   └── services/           # ML anomaly detection & parsing logic
│       └── __init__.py
├── implementation_plan.md  # Detailed project plan and phases
```

## Progress So Far (Exact Actions Taken)
1. **Phase 1 (Project Setup & Data Simulation)**: **[COMPLETED]**
   - **Data Generation**: We ran a script to generate synthetic patient profiles and planted intentional duplicates/conflicts.
   - **Directory Creation**: We explicitly created the following directories in the project root:
     - `backend/agents/`
     - `backend/models/`
     - `backend/services/`
     - `backend/data/`
   - **Python Package Initialization**: We added empty `__init__.py` files inside `agents/`, `models/`, and `services/` to make them proper Python packages.
   - **Data Migration**: We moved the generated mock data files into the `backend/data/` directory. The exact files that exist in `backend/data/` right now are:
     - `hospital_A.json`
     - `hospital_B.xml`
     - `hospital_C.csv`
     - `conflict_manifest.json`

By having this exact file and folder structure, both AI assistants will see the identical state of the codebase.

## Immediate Next Steps (Where we paused)
We are currently entering **Phase 2: Core Data Models (Schema Definition)**.
- The next immediate task is to define a unified FHIR-like schema using Pydantic inside the `backend/models/` directory.
- The schema needs minimum fields: `patient_id`, `name`, `dob`, `gender`, `blood_group`, `diagnosis`, `medications`, `source_hospital`.

## Architecture & Phases (For Reference)

### Phase 2: Core Data Models (Schema Definition)
Define a simple, unified FHIR-like schema using Pydantic. It is critical that all parsed data is mapped to this exact schema to prevent downstream breakage.

### Phase 3: Multi-Agent System (CrewAI)
- **Ingestion & Conversion Agent**: Reads files from `backend/data/` and maps raw data into the Pydantic schema.
- **Validation Agent**: Checks for missing fields or invalid formats.
- **Conflict Detection Agent (CORE)**: Matches patients based on `patient_id` or `(name + dob)`. Flags conflicts (e.g., different blood group/medications) and assigns an AI-driven confidence score.
- **Insight Agent**: Applies a basic ML model (e.g., `IsolationForest`) to flag statistical anomalies.

### Phase 4: API Layer (FastAPI)
- `POST /api/v1/process`: Triggers CrewAI pipeline.
- `GET /api/v1/conflicts`: Returns detected conflicts.
- `GET /api/v1/patients`: Returns deduplicated records.

### Phase 5: Dashboard (React)
- A dashboard connecting to the FastAPI backend to visualize metrics and conflicts.

---
**End of Context. The receiving assistant can now resume work from Phase 2.**
