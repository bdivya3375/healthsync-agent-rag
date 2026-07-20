"""
Healthcare Data Integration API -- FastAPI Application

Clinical Flow Endpoints:
    POST /api/v1/admit          -- Simulate a patient checking in with a new report
    GET  /api/v1/admissions     -- List pending patient reports in the admissions queue
    GET  /api/v1/admissions/{id}/audit -- Run Cooperative AI Agents to audit admission
    POST /api/v1/admissions/{id}/resolve -- Merge audited/resolved record and complete admission
    GET  /api/v1/export/{id}    -- Convert resolved patient back to JSON/XML/CSV
"""

import json
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone

from database.connection import init_db, get_db
from database.models import PatientRecord, ConflictRecord, PendingReport, HospitalAPatient, HospitalBPatient, HospitalCPatient, DoctorAuth, AuditLog
from passlib.context import CryptContext
from services.data_pipeline import process_all_data
from services.conflict_detector import detect_conflicts
from models.unified_schema import Patient, LabResults
from services.department_mapper import (
    map_conflict_to_department,
    get_confidence_score,
    ALL_DEPARTMENTS,
)
from services.hospital_simulator import admit_simulated_patient
from agents.orchestrator import ClinicalAIOrchestrator
from services.format_exporter import export_patient_by_format
from services.distributed_query import fetch_patient_history_across_hospitals
from services.nurse_joy import generate_joy_response
from services.auth_service import create_access_token, decode_access_token
from services.audit_trail import log_audit_event, get_audit_trail
from services.pii_redaction import redact_name, redact_patient_id
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import random

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "css").mkdir(exist_ok=True)
(STATIC_DIR / "js").mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        logger.info("[OK] Database initialized (PostgreSQL)")
    except Exception as e:
        logger.error("[WARN] Database init failed: %s", e)

    # Seed RAG medical knowledge base for Nurse Joy
    try:
        from services.rag_knowledge import seed_knowledge_base
        doc_count = seed_knowledge_base()
        if doc_count > 0:
            logger.info("[OK] RAG knowledge base seeded with %d medical documents", doc_count)
        else:
            logger.info("[OK] RAG knowledge base already loaded")
    except Exception as e:
        logger.warning("[WARN] RAG knowledge base init failed (Nurse Joy will work without RAG): %s", e)

    yield


app = FastAPI(
    title="HealthSync-AgentRAG: Cooperative Multi-Agent Clinical Reconciliation & RAG-Knowledge Base",
    description="Ingest, normalize, and resolve conflicts in multi-hospital clinical data using cooperative AI agents and a local RAG medical knowledge base.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# SSE Broadcast Infrastructure (lightweight, memory-backed)
# ---------------------------------------------------------------------------

sse_clients: List[asyncio.Queue] = []

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    hospital: str
    department: str

class LoginRequest(BaseModel):
    identifier: str
    password: str

# ---------------------------------------------------------------------------
# JWT Auth Dependency (RBAC)
# ---------------------------------------------------------------------------

security_scheme = HTTPBearer(auto_error=False)

def get_current_doctor(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Optional[DoctorAuth]:
    """
    Extracts the current doctor from the JWT Bearer token.
    Returns None if no token is provided (for backward compatibility).
    Raises 401 if token is invalid.
    """
    if credentials is None:
        return None
    
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    doctor = db.query(DoctorAuth).filter(DoctorAuth.username == username).first()
    if not doctor:
        raise HTTPException(status_code=401, detail="Doctor not found")
    
    return doctor


def require_role(*allowed_roles):
    """Dependency factory: require the doctor to have one of the allowed roles."""
    def _check(doctor: DoctorAuth = Depends(get_current_doctor)):
        if doctor is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        if doctor.role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Requires role: {', '.join(allowed_roles)}")
        return doctor
    return _check


@app.post("/api/v1/auth/register")
def register_doctor(req: RegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(DoctorAuth).filter(DoctorAuth.username == req.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
        
    existing_email = db.query(DoctorAuth).filter(DoctorAuth.email == req.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed = get_password_hash(req.password)
    doc = DoctorAuth(
        username=req.username,
        email=req.email,
        password_hash=hashed,
        hospital=req.hospital,
        department=req.department,
        role="doctor",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    log_audit_event(
        db, actor_username=req.username, actor_role="doctor",
        action="REGISTER", resource_type="auth",
    )

    return {"status": "success", "message": "Registered successfully"}

@app.post("/api/v1/auth/login")
def login_doctor(req: LoginRequest, db: Session = Depends(get_db)):
    from sqlalchemy import or_
    doc = db.query(DoctorAuth).filter(
        or_(DoctorAuth.username == req.identifier, DoctorAuth.email == req.identifier)
    ).first()
    if not doc or not verify_password(req.password, doc.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate JWT token
    access_token = create_access_token(data={"sub": doc.username, "role": doc.role})

    log_audit_event(
        db, actor_username=doc.username, actor_role=doc.role,
        action="LOGIN", resource_type="auth",
    )

    return {
        "status": "success",
        "access_token": access_token,
        "token_type": "bearer",
        "doctor": {
            "name": doc.username,
            "hospital": doc.hospital,
            "department": doc.department,
            "role": doc.role,
        }
    }


# ---------------------------------------------------------------------------
# GET /api/v1/audit-trail -- Admin-only audit log viewer
# ---------------------------------------------------------------------------

@app.get("/api/v1/audit-trail")
def view_audit_trail(
    actor: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    doctor: DoctorAuth = Depends(get_current_doctor),
):
    """View the HIPAA audit trail. Restricted to admin and doctor roles."""
    if doctor and doctor.role not in ("admin", "doctor"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    trail = get_audit_trail(db, actor_username=actor, action=action, resource_type=resource_type, limit=limit)
    return {"status": "success", "count": len(trail), "data": trail}


async def broadcast_admission(admission_data: dict):
    """Push a new admission event to all connected SSE clients."""
    disconnected = []
    for queue in sse_clients:
        try:
            await queue.put(admission_data)
        except Exception:
            disconnected.append(queue)
    for q in disconnected:
        sse_clients.remove(q)


# ---------------------------------------------------------------------------
# Recommendation templates (plain text, no auto-resolve)
# ---------------------------------------------------------------------------

RECOMMENDATION_MAP = {
    "blood_group": "Re-test blood group in lab before any transfusion or procedure.",
    "diagnosis": "Schedule clinical review with attending physician to confirm diagnosis.",
    "medications": "Perform medication reconciliation with patient interview.",
    "allergies": "Conduct comprehensive allergy assessment (skin prick / IgE panel).",
    "gender": "Verify patient demographics against government-issued ID.",
    "age": "Verify date of birth from patient's official ID document.",
}


# ---------------------------------------------------------------------------
# Helper: Convert DB records to Patient objects for conflict detection
# ---------------------------------------------------------------------------

def _db_records_to_patients(db: Session) -> list:
    """Read all PatientRecord rows from DB and convert to Patient objects."""
    records = db.query(PatientRecord).all()
    patients = []
    for r in records:
        patients.append(Patient(
            patient_id=r.patient_id,
            name=r.name,
            dob=r.dob or "",
            gender=r.gender,
            blood_group=r.blood_group,
            diagnosis=json.loads(r.diagnosis),
            medications=json.loads(r.medications),
            source_hospital=r.source_hospital,
        ))
    return patients


def _run_conflict_detection(patients: list, db: Session) -> int:
    """
    Run conflict detection on a list of Patient objects,
    clear old conflicts, and store new ones in DB.
    Returns the number of conflicts detected.
    """
    db.query(ConflictRecord).delete()

    summary = detect_conflicts(patients)
    logger.info("Pipeline: Found %d conflicts across %d patients",
                summary.total_conflicts, len(patients))

    conflict_count = 0
    for report in summary.patient_reports:
        for conflict in report.conflicts:
            hospitals_list = list(conflict.values_by_source.keys())
            values_list = list(conflict.values_by_source.values())

            department = map_conflict_to_department(conflict.field, values_list)
            confidence = get_confidence_score(hospitals_list)
            rec_text = RECOMMENDATION_MAP.get(
                conflict.field,
                f"Review and verify {conflict.field} with clinical team."
            )
            conflict_type = conflict.field.replace("_", " ").title() + " Mismatch"

            db_conflict = ConflictRecord(
                patient_id=report.matched_ids.get(hospitals_list[0], ""),
                patient_name=report.patient_name,
                conflict_type=conflict_type,
                hospitals=json.dumps(hospitals_list),
                values=json.dumps(
                    {h: (", ".join(v) if isinstance(v, list) else str(v))
                     for h, v in conflict.values_by_source.items()}
                ),
                department=department,
                confidence_score=round(confidence, 2),
                recommendation=rec_text,
            )
            db.add(db_conflict)
            conflict_count += 1

    db.commit()
    return conflict_count


# ---------------------------------------------------------------------------
# POST /api/v1/process -- Seed files + run conflict detection on ALL DB data
# ---------------------------------------------------------------------------

@app.post("/api/v1/process")
def run_pipeline(db: Session = Depends(get_db)):
    """
    Full pipeline:
    1. If DB has no patients yet, seed from data files (one-time)
    2. Run conflict detection on ALL patient records in the DB
    3. Store conflicts in DB
    """
    try:
        # Step 1: Seed from files only if DB is empty
        existing_count = db.query(PatientRecord).count()
        seeded = 0

        if existing_count == 0:
            file_patients = process_all_data()
            for p in file_patients:
                hosp = random.choice(["Hospital A", "Hospital B", "Hospital C"])
                db_model = None
                if hosp == "Hospital A":
                    db_model = HospitalAPatient
                elif hosp == "Hospital B":
                    db_model = HospitalBPatient
                else:
                    db_model = HospitalCPatient

                db.add(db_model(
                    patient_id=p.patient_id,
                    name=p.name,
                    dob=p.dob or "",
                    gender=p.gender,
                    blood_group=p.blood_group,
                    diagnosis=json.dumps(p.diagnosis),
                    medications=json.dumps(p.medications),
                    source_hospital=hosp,
                ))
            db.commit()
            seeded = len(file_patients)
            logger.info("Pipeline: Seeded %d patients from data files into distributed tables", seeded)

        # Step 2: Load ALL patients from DB and run conflict detection
        all_patients = _db_records_to_patients(db)
        total_patients = len(all_patients)
        hospitals_in_db = len(set(p.source_hospital for p in all_patients))

        conflict_count = _run_conflict_detection(all_patients, db)

        return {
            "status": "success",
            "message": "Pipeline completed successfully",
            "patients_in_db": total_patients,
            "hospitals_in_db": hospitals_in_db,
            "newly_seeded": seeded,
            "conflicts_detected": conflict_count,
        }

    except Exception as e:
        db.rollback()
        logger.error("Pipeline failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


# ---------------------------------------------------------------------------
# POST /api/v1/simulate -- Simulate a new hospital sending data
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# CLINICAL ADMISSIONS QUEUE & COOPERATIVE AI AGENTS
# ---------------------------------------------------------------------------

class ResolveAdmissionRequest(BaseModel):
    doctor_name: str
    blood_group: str
    diagnosis: List[str]
    medications: List[str]

from fastapi import FastAPI, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

class ChatRequest(BaseModel):
    message: str
    patient_context: dict

@app.post("/api/v1/chat")
def chat_with_nurse_joy(req: ChatRequest):
    """
    Ultra-low latency endpoint for the Nurse Joy chatbot.
    Relies on the frontend passing the audited patient context.
    """
    try:
        reply = generate_joy_response(req.message, req.patient_context)
        return {"status": "success", "reply": reply}
    except Exception as e:
        logger.error("Nurse Joy error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Nurse Joy is currently offline.")

@app.websocket("/api/v1/chat/stream")
async def chat_with_nurse_joy_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time Nurse Joy streaming.
    The client sends a JSON payload with 'message' and 'patient_context'.
    The server yields tokens continuously.
    """
    from services.nurse_joy import stream_joy_response
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            patient_context = data.get("patient_context", {})
            
            async for token in stream_joy_response(message, patient_context):
                if token:
                    await websocket.send_text(token)
            
            # Send a specific end-of-message signal
            await websocket.send_text("[DONE]")
            
    except WebSocketDisconnect:
        logger.info("Nurse Joy chat disconnected")
    except Exception as e:
        logger.error("Nurse Joy streaming error: %s", e, exc_info=True)
        try:
            await websocket.send_text(f" [Error: {str(e)}][DONE]")
        except:
            pass


@app.post("/api/v1/admit")
async def admit_patient(db: Session = Depends(get_db)):
    """
    Simulate a patient walk-in admission.
    Generates a new patient report (often overlapping with an existing patient)
    containing realistic clinical discrepancies, and inserts it into the admissions queue.
    Pushes the new admission to all connected SSE clients.
    """
    try:
        pending = admit_simulated_patient(db)
        admission_data = {
            "id": pending.id,
            "patient_id": pending.patient_id,
            "name": pending.name,
            "dob": pending.dob,
            "gender": pending.gender,
            "source_hospital": pending.source_hospital,
            "created_at": pending.created_at.isoformat()
        }

        # Push to SSE broadcast
        await broadcast_admission(admission_data)

        return {
            "status": "success",
            "message": f"Admission queued: {pending.name} from {pending.source_hospital}",
            "admission": admission_data
        }
    except Exception as e:
        db.rollback()
        logger.error("Failed to queue admission: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Admission error: {str(e)}")


@app.get("/api/v1/admissions/stream")
async def admissions_stream():
    """SSE endpoint: streams new admission events to connected dashboard clients."""
    queue: asyncio.Queue = asyncio.Queue()
    sse_clients.append(queue)

    async def event_generator():
        try:
            while True:
                data = await queue.get()
                yield f"event: new_admission\ndata: {json.dumps(data)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in sse_clients:
                sse_clients.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/v1/admissions")
def list_admissions(hospital: str = None, db: Session = Depends(get_db)):
    """List pending admissions waiting for clinical audit, optionally filtered by hospital."""
    query = db.query(PendingReport).filter(PendingReport.status == "Pending")
    if hospital:
        query = query.filter(func.lower(PendingReport.source_hospital) == hospital.lower())
    admissions = query.order_by(PendingReport.created_at.desc()).all()
    data = []
    for adm in admissions:
        data.append({
            "id": adm.id,
            "patient_id": adm.patient_id,
            "name": adm.name,
            "dob": adm.dob,
            "gender": adm.gender,
            "blood_group": adm.blood_group,
            "diagnosis": json.loads(adm.diagnosis),
            "medications": json.loads(adm.medications),
            "source_hospital": adm.source_hospital,
            "status": adm.status,
            "created_at": adm.created_at.isoformat()
        })
    return {"status": "success", "count": len(data), "data": data}


@app.get("/api/v1/admissions/{admission_id}/audit")
def audit_admission(admission_id: int, db: Session = Depends(get_db), doctor: DoctorAuth = Depends(get_current_doctor)):
    """
    Run Cooperative AI Agents to audit the pending report against PostgreSQL history:
    1. IngestionAgent validates the report structures.
    2. AuditorAgent compares report against existing PostgreSQL records.
    3. ClinicalChiefAgent maps departments, computes reliability, and creates rationale.
    """
    pending = db.query(PendingReport).filter(PendingReport.id == admission_id).first()
    if not pending:
        raise HTTPException(status_code=404, detail="Admission record not found")

    # Fetch existing patient database records for name-linkage from distributed hospitals
    normalized_name = pending.name.strip().lower()
    raw_history_records = fetch_patient_history_across_hospitals(db, normalized_name)

    # Convert dictionaries to pseudo PatientRecord objects so orchestrator.py doesn't break
    history_records = []
    for r in raw_history_records:
        history_records.append(PatientRecord(
            source_hospital=r["source_hospital"],
            blood_group=r["blood_group"],
            diagnosis=r["diagnosis"],
            medications=r["medications"]
        ))

    # Pack pending report raw map
    raw_report = {
        "patient_id": pending.patient_id,
        "name": pending.name,
        "dob": pending.dob,
        "gender": pending.gender,
        "blood_group": pending.blood_group,
        "diagnosis": json.loads(pending.diagnosis),
        "medications": json.loads(pending.medications),
        "source_hospital": pending.source_hospital,
    }

    # Execute Multi-Agent Orchestrator (3 cooperative agents)
    orchestrator = ClinicalAIOrchestrator()
    result = orchestrator.process_incoming_admission(raw_report, history_records)

    # Extract per-agent outputs
    conflict_records = result["conflict_records"]
    agent_conflicts = result["conflicts"]

    # Format output conflicts for the front-end
    conflicts_data = []
    for c in agent_conflicts:
        conflicts_data.append({
            "field": c.get("field", ""),
            "conflict_type": c.get("conflict_type", ""),
            "hospitals": list(c.get("values", {}).keys()),
            "values": c.get("values", {}),
            "department": map_conflict_to_department(
                c.get("field", ""), list(c.get("values", {}).values())
            ),
            "confidence_score": get_confidence_score(list(c.get("values", {}).keys())),
            "recommendation": result["agent_3_recommendations"],
            # Dose-specific metadata (if present)
            "drug_name": c.get("drug_name"),
            "dose_old": c.get("dose_old"),
            "dose_new": c.get("dose_new"),
        })

    # Historical values summary
    history_data = []
    for h in history_records:
        history_data.append({
            "source_hospital": h.source_hospital,
            "blood_group": h.blood_group,
            "diagnosis": json.loads(h.diagnosis),
            "medications": json.loads(h.medications),
        })

    # Log audit event
    if doctor:
        log_audit_event(
            db, actor_username=doctor.username, actor_role=doctor.role,
            action="AUDIT", resource_type="admission",
            resource_id=pending.patient_id, resource_name=pending.name,
            details={"conflicts_found": len(agent_conflicts), "admission_id": admission_id},
        )

    return {
        "status": "success",
        "admission_id": admission_id,
        "patient_id": pending.patient_id,
        "name": pending.name,
        "incoming_report": raw_report,
        "history": history_data,
        "conflicts": conflicts_data,
        # Per-agent reasoning (new — drives the UI agent cards)
        "agent_1_assessment": result["agent_1_assessment"],
        "agent_2_reasoning": result["agent_2_reasoning"],
        "agent_3_recommendations": result["agent_3_recommendations"],
    }


@app.post("/api/v1/admissions/{admission_id}/resolve")
def resolve_admission(
    admission_id: int, req: ResolveAdmissionRequest, db: Session = Depends(get_db)
):
    """
    Doctor resolves the audited conflicts.
    1. Updates or creates standard clean patient records in the main database table.
    2. Marks the pending walk-in report as 'Audited'.
    3. Adds a resolved ConflictRecord logs.
    """
    try:
        pending = db.query(PendingReport).filter(PendingReport.id == admission_id).first()
        if not pending:
            raise HTTPException(status_code=404, detail="Admission record not found")

        # Update existing records or insert a clean new consolidated PatientRecord in the database
        normalized_name = pending.name.strip().lower()
        existing_record = db.query(PatientRecord).filter(
            func.lower(PatientRecord.name) == normalized_name
        ).first()

        if existing_record:
            # Update the unified patient record with the doctor's chosen correct fields
            existing_record.blood_group = req.blood_group
            existing_record.diagnosis = json.dumps(req.diagnosis)
            existing_record.medications = json.dumps(req.medications)
            existing_record.created_at = datetime.now(timezone.utc)
            patient_id = existing_record.patient_id
        else:
            # Insert a brand-new patient record
            new_rec = PatientRecord(
                patient_id=pending.patient_id or f"PT{datetime.now().strftime('%f')}",
                name=pending.name,
                dob=pending.dob,
                gender=pending.gender,
                blood_group=req.blood_group,
                diagnosis=json.dumps(req.diagnosis),
                medications=json.dumps(req.medications),
                source_hospital=pending.source_hospital
            )
            db.add(new_rec)
            patient_id = new_rec.patient_id

        # Update pending report state
        pending.status = "Audited"

        # Log conflict resolution log in DB
        log_entry = ConflictRecord(
            patient_id=patient_id,
            patient_name=pending.name,
            conflict_type="Clinical Resolution Audit",
            hospitals=json.dumps([pending.source_hospital]),
            values=json.dumps({"resolved": req.blood_group}),
            department="general",
            confidence_score=1.0,
            recommendation=f"Conflict resolved by attending physician: {req.doctor_name}",
            is_reviewed=True,
            reviewed_by=req.doctor_name,
            reviewed_at=datetime.now(timezone.utc)
        )
        db.add(log_entry)
        db.commit()

        # Log audit trail for the resolution
        log_audit_event(
            db, actor_username=req.doctor_name, actor_role="doctor",
            action="RESOLVE", resource_type="admission",
            resource_id=patient_id, resource_name=pending.name,
            details={"admission_id": admission_id, "blood_group": req.blood_group},
        )

        return {
            "status": "success",
            "message": "Clinical conflicts resolved and record synchronized successfully!",
            "patient_id": patient_id
        }

    except Exception as e:
        db.rollback()
        logger.error("Failed to resolve admission: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Resolution error: {str(e)}")


@app.get("/api/v1/export/{patient_id}")
def export_resolved_record(
    patient_id: str, format: str = Query(..., description="Export format: json, xml, csv"), db: Session = Depends(get_db)
):
    """
    Bi-directional exporter:
    Converts a standardized patient record from PostgreSQL back into the requested custom hospital format!
    """
    record = db.query(PatientRecord).filter(PatientRecord.patient_id == patient_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Patient record not found")

    # Reconstruct unified Patient pydantic model
    patient_model = Patient(
        patient_id=record.patient_id,
        name=record.name,
        age=None,  # Not stored as individual column
        gender=record.gender,
        blood_group=record.blood_group,
        allergies=[],
        diagnosis=json.loads(record.diagnosis),
        medications=json.loads(record.medications),
        visit_history=[],
        source_hospital=record.source_hospital,
        last_updated=datetime.now().isoformat()
    )

    try:
        formatted_str = export_patient_by_format(patient_model, format)
        
        # Set appropriate clinical content types
        ext = format.lower()
        if ext == "json":
            media_type = "application/json"
        elif ext == "xml":
            media_type = "application/xml"
        else:
            media_type = "text/csv"

        return Response(
            content=formatted_str,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename=patient_{patient_id}_resolved.{ext}"}
        )
    except Exception as e:
        logger.error("Export failed: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/v1/export/{patient_id}/fhir -- FHIR R4 Bundle Export
# ---------------------------------------------------------------------------

@app.get("/api/v1/export/{patient_id}/fhir")
def export_fhir_bundle(
    patient_id: str,
    db: Session = Depends(get_db),
    doctor: DoctorAuth = Depends(get_current_doctor),
):
    """
    Export a patient record as an HL7 FHIR R4 Bundle.
    Contains Patient + Condition + MedicationStatement + AllergyIntolerance resources.
    """
    from models.fhir_schema import to_fhir_bundle

    record = db.query(PatientRecord).filter(PatientRecord.patient_id == patient_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Patient record not found")

    bundle = to_fhir_bundle(
        patient_id=record.patient_id,
        name=record.name,
        gender=record.gender,
        dob=record.dob,
        blood_group=record.blood_group,
        allergies=[],
        diagnoses=json.loads(record.diagnosis),
        medications=json.loads(record.medications),
        source_hospital=record.source_hospital,
    )

    # Log FHIR export event
    if doctor:
        log_audit_event(
            db, actor_username=doctor.username, actor_role=doctor.role,
            action="EXPORT", resource_type="patient",
            resource_id=patient_id, resource_name=record.name,
            details={"format": "fhir_r4_bundle"},
        )

    return Response(
        content=json.dumps(bundle, indent=2),
        media_type="application/fhir+json",
        headers={"Content-Disposition": f"attachment; filename=patient_{patient_id}_fhir_bundle.json"},
    )


# ---------------------------------------------------------------------------
# GET /api/v1/conflicts -- Filtered by doctor hospital + department
# ---------------------------------------------------------------------------

@app.get("/api/v1/conflicts")
def get_conflicts(
    hospital: str = Query(..., description="Doctor's hospital"),
    department: str = Query(..., description="Doctor's department"),
    db: Session = Depends(get_db),
):
    """
    Return ONLY conflicts where:
      - doctor.hospital is IN the conflict's hospitals list
      AND
      - doctor.department == conflict.department

    This is the CRITICAL filtering logic from the spec.
    """
    all_conflicts = db.query(ConflictRecord).filter(
        ConflictRecord.department == department
    ).all()

    # Further filter: doctor's hospital must be in the conflict's hospitals (case-insensitive)
    hospital_lower = hospital.lower()
    filtered = []
    for c in all_conflicts:
        conflict_hospitals = json.loads(c.hospitals)
        if any(h.lower() == hospital_lower for h in conflict_hospitals):
            filtered.append({
                "id": c.id,
                "patient_id": c.patient_id,
                "patient_name": c.patient_name,
                "conflict_type": c.conflict_type,
                "hospitals": conflict_hospitals,
                "values": json.loads(c.values),
                "department": c.department,
                "confidence_score": c.confidence_score,
                "recommendation": c.recommendation,
                "is_reviewed": c.is_reviewed,
                "reviewed_by": c.reviewed_by,
            })

    return {"status": "success", "count": len(filtered), "data": filtered}


# ---------------------------------------------------------------------------
# GET /api/v1/patients -- Filtered by doctor's hospital
# ---------------------------------------------------------------------------

@app.get("/api/v1/patients")
def get_patients(
    hospital: str = Query(..., description="Doctor's hospital"),
    db: Session = Depends(get_db),
):
    """Return patients related to the doctor's hospital."""
    records = db.query(PatientRecord).filter(
        func.lower(PatientRecord.source_hospital) == hospital.lower()
    ).all()

    patients = []
    for r in records:
        patients.append({
            "id": r.id,
            "patient_id": r.patient_id,
            "name": r.name,
            "dob": r.dob,
            "gender": r.gender,
            "blood_group": r.blood_group,
            "diagnosis": json.loads(r.diagnosis),
            "medications": json.loads(r.medications),
            "source_hospital": r.source_hospital,
        })

    return {"status": "success", "count": len(patients), "data": patients}


# ---------------------------------------------------------------------------
# POST /api/v1/conflicts/{id}/review -- Mark as reviewed
# ---------------------------------------------------------------------------

@app.post("/api/v1/conflicts/{conflict_id}/review")
def review_conflict(
    conflict_id: int,
    doctor_name: str = Query(..., description="Doctor's name"),
    db: Session = Depends(get_db),
):
    """Mark a conflict as reviewed by a doctor."""
    conflict = db.query(ConflictRecord).filter(ConflictRecord.id == conflict_id).first()
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")

    conflict.is_reviewed = True
    conflict.reviewed_by = doctor_name
    conflict.reviewed_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "success", "message": "Conflict marked as reviewed"}


# ---------------------------------------------------------------------------
# GET /api/v1/departments -- List of valid departments
# ---------------------------------------------------------------------------

@app.get("/api/v1/departments")
def get_departments():
    """Return list of valid medical departments."""
    return {"departments": ALL_DEPARTMENTS}


# ---------------------------------------------------------------------------
# GET /api/v1/hospitals -- List of hospitals from DB
# ---------------------------------------------------------------------------

@app.get("/api/v1/hospitals")
def get_hospitals(db: Session = Depends(get_db)):
    """Return list of unique hospitals from patient records."""
    results = db.query(PatientRecord.source_hospital).distinct().all()
    hospitals = [r[0] for r in results]
    return {"hospitals": hospitals}


# ---------------------------------------------------------------------------
# Health check + Frontend
# ---------------------------------------------------------------------------

@app.get("/api/v1/health")
def health_check():
    return {"status": "ok", "message": "Healthcare System API running"}


@app.get("/")
def serve_index():
    return FileResponse(str(TEMPLATES_DIR / "index.html"))

@app.get("/login")
def serve_login():
    return FileResponse(str(TEMPLATES_DIR / "login.html"))