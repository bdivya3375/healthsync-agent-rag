# Healthcare Data Integration Middleware

## Overview
The **Healthcare Data Integration Middleware** is a system designed to solve a major problem in modern healthcare: fragmented and inconsistent patient data across different hospital systems. When a patient visits multiple hospitals, their medical records are often scattered across different formats, systems, and databases.

This system ingests data from multiple hospitals, standardizes it into a unified schema, detects conflicting medical information (like differing blood types or allergy lists), and provides a clean dashboard for healthcare professionals to review and resolve these conflicts safely.

## Key Features
- **Multi-Format Data Ingestion**: Parses disparate data formats from different hospital sources (JSON, XML, CSV).
- **Unified Schema Standardization**: Converts all incoming data into a single, clean standard using Pydantic.
- **Intelligent Conflict Detection**: Groups records by patient and mathematically compares lists and fields, checking for clinical tolerances to detect true medical discrepancies.
- **Resolution Advisor**: Algorithms that score hospital reliability and generate clinical recommendations for conflict resolution.
- **Doctor Dashboard**: A premium, responsive SPA (Single Page Application) built with Vanilla JS, HTML, and CSS (glassmorphism design) for doctors to review and resolve data conflicts.
- **Secure API**: FastAPI backend with JWT authentication and bcrypt password hashing.

## Tech Stack
- **Backend**: Python, FastAPI, Pydantic, SQLAlchemy, Uvicorn
- **Database**: PostgreSQL (via SQLAlchemy) / SQLite (for development)
- **Security**: JWT (JSON Web Tokens), bcrypt
- **Frontend**: Vanilla HTML5, CSS3, JavaScript, Chart.js

## Project Structure
```text
healthcare_system/
├── backend/
│   ├── agents/          # AI reasoning layer (CrewAI - upcoming)
│   ├── data/            # Mock hospital data files (JSON, XML, CSV)
│   ├── database/        # Database configuration and connection
│   ├── middleware/      # Auth and security middleware
│   ├── models/          # Pydantic schemas and database models
│   ├── parsers/         # Data ingestion scripts for different formats
│   ├── routes/          # FastAPI endpoint definitions
│   ├── services/        # Core business logic (Conflict Engine, Advisor)
│   ├── static/          # Frontend CSS, JS, and assets
│   ├── templates/       # Frontend HTML files
│   └── main.py          # FastAPI application entry point
└── README.md            # Project documentation
```

## Setup & Installation

### Prerequisites
- Python 3.9+
- A C/C++ compiler (required for some dependencies like `numpy` / `crewai` in future phases)

### Installation Steps

1. **Clone or navigate to the project directory:**
   ```bash
   cd path/to/HealthcareProject
   ```

2. **Set up a virtual environment (recommended):**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install the dependencies:**
   Make sure you are in the directory containing your requirements (or install the main packages directly).
   ```bash
   pip install fastapi uvicorn pydantic sqlalchemy bcrypt pyjwt
   ```
   *(Note: For Phase 5 CrewAI features, additional dependencies will be required and may need build tools configured).*

## Usage

1. **Start the Backend Server:**
   Navigate to the `healthcare_system/backend` directory and run the FastAPI server using Uvicorn.
   ```bash
   cd healthcare_system/backend
   uvicorn main:app --reload
   ```

2. **Access the Dashboard:**
   Open your web browser and navigate to:
   ```
   http://127.0.0.1:8000
   ```
   This will serve the frontend SPA where doctors can log in, view the triage dashboard, and resolve conflicts.

3. **API Documentation:**
   FastAPI automatically generates interactive API documentation. You can access it at:
   - Swagger UI: `http://127.0.0.1:8000/docs`
   - ReDoc: `http://127.0.0.1:8000/redoc`

## Future Development (Upcoming Phases)
- **Manual Data Upload**: A feature to upload and convert data files directly through the UI.
- **AI Reasoning Layer (CrewAI)**: Implementing LLM agents to perform advanced analysis on medical data, read unstructured notes, and provide deeper insights during conflict resolution.
