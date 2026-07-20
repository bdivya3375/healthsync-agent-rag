"""
SQLAlchemy Database Models

Tables:
- patients:           Unified patient records stored after pipeline ingestion
- conflicts:          Detected conflicts with department mapping + recommendations
- resolved_conflicts: Tracks which conflicts a doctor has reviewed
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from database.connection import Base


class PatientRecord(Base):
    """A single patient record from one hospital source."""
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, index=True)        # e.g. "PT1001"
    name = Column(String, index=True)
    dob = Column(String, nullable=True)
    gender = Column(String)
    blood_group = Column(String)
    diagnosis = Column(Text, default="[]")          # JSON string list
    medications = Column(Text, default="[]")        # JSON string list
    source_hospital = Column(String, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ConflictRecord(Base):
    """A detected conflict between hospital records for the same patient."""
    __tablename__ = "conflicts"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, index=True)
    patient_name = Column(String, index=True)
    conflict_type = Column(String)                  # e.g. "Blood Group Mismatch"
    hospitals = Column(Text)                        # JSON list of hospital names
    values = Column(Text)                           # JSON list of conflicting values
    department = Column(String, index=True)          # mapped department
    confidence_score = Column(Float)                 # 0.0 - 1.0
    recommendation = Column(String)                  # text recommendation
    is_reviewed = Column(Boolean, default=False)
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PendingReport(Base):
    """A new patient report brought during admission, waiting to be audited against history."""
    __tablename__ = "pending_reports"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, index=True, nullable=True)
    name = Column(String, index=True)
    dob = Column(String, nullable=True)
    gender = Column(String)
    blood_group = Column(String)
    diagnosis = Column(Text, default="[]")          # JSON string list
    medications = Column(Text, default="[]")        # JSON string list
    source_hospital = Column(String, index=True)
    status = Column(String, default="Pending")       # Pending / Audited / Dismissed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class HospitalAPatient(Base):
    """Raw patient record stored in Hospital A's silo."""
    __tablename__ = "hospital_a_patients"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, index=True)
    name = Column(String, index=True)
    dob = Column(String, nullable=True)
    gender = Column(String)
    blood_group = Column(String)
    diagnosis = Column(Text, default="[]")
    medications = Column(Text, default="[]")
    source_hospital = Column(String, default="Hospital A")


class HospitalBPatient(Base):
    """Raw patient record stored in Hospital B's silo."""
    __tablename__ = "hospital_b_patients"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, index=True)
    name = Column(String, index=True)
    dob = Column(String, nullable=True)
    gender = Column(String)
    blood_group = Column(String)
    diagnosis = Column(Text, default="[]")
    medications = Column(Text, default="[]")
    source_hospital = Column(String, default="Hospital B")


class HospitalCPatient(Base):
    """Raw patient record stored in Hospital C's silo."""
    __tablename__ = "hospital_c_patients"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, index=True)
    name = Column(String, index=True)
    dob = Column(String, nullable=True)
    gender = Column(String)
    blood_group = Column(String)
    diagnosis = Column(Text, default="[]")
    medications = Column(Text, default="[]")
    source_hospital = Column(String, default="Hospital C")


class DoctorAuth(Base):
    """Secure Doctor Login Credentials with Role-Based Access Control."""
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    hospital = Column(String)
    department = Column(String)
    role = Column(String, default="doctor")  # admin, doctor, nurse
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AuditLog(Base):
    """
    HIPAA-compliant Audit Trail.
    Logs every access and modification to patient records.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_username = Column(String, index=True)       # Who performed the action
    actor_role = Column(String)                        # admin / doctor / nurse
    action = Column(String, index=True)                # VIEW, MODIFY, AUDIT, RESOLVE, EXPORT
    resource_type = Column(String)                     # patient, conflict, admission
    resource_id = Column(String, nullable=True)        # Patient ID or Conflict ID
    resource_name = Column(String, nullable=True)      # Patient name (redacted in logs)
    details = Column(Text, nullable=True)              # Additional context (JSON)
    ip_address = Column(String, nullable=True)         # Request source IP
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


