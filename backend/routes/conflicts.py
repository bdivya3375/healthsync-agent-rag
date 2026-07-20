"""
Conflicts Routes

Endpoints for viewing and resolving conflicts.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
import json
import os
from typing import Optional

from middleware.auth_middleware import get_current_doctor
from database.models import Doctor, ResolvedConflict
from database.connection import get_db

router = APIRouter(prefix="/conflicts", tags=["Conflicts"])

class ResolveRequest(BaseModel):
    patient_name: str
    field: str
    resolved_value: str
    notes: Optional[str] = None

@router.get("/")
def list_conflicts(
    severity: Optional[str] = None,
    field: Optional[str] = None,
    current_doctor: Doctor = Depends(get_current_doctor)
):
    """List all patient conflicts, optionally filtered."""
    try:
        conflicts_file = os.path.join("data", "detected_conflicts.json")
        with open(conflicts_file, "r") as f:
            data = json.load(f)
            
        reports = data.get("patient_reports", [])
        
        filtered_reports = []
        for report in reports:
            filtered_conflicts = []
            for c in report.get("conflicts", []):
                # Apply filters
                if severity and c.get("severity") != severity:
                    continue
                if field and c.get("field") != field:
                    continue
                filtered_conflicts.append(c)
                
            if filtered_conflicts:
                filtered_report = report.copy()
                filtered_report["conflicts"] = filtered_conflicts
                filtered_reports.append(filtered_report)
                
        return {"status": "success", "count": len(filtered_reports), "data": filtered_reports}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading conflict data: {str(e)}")

@router.get("/summary")
def conflicts_summary(current_doctor: Doctor = Depends(get_current_doctor)):
    """Get aggregate conflict statistics."""
    try:
        conflicts_file = os.path.join("data", "detected_conflicts.json")
        with open(conflicts_file, "r") as f:
            data = json.load(f)
            
        return {
            "status": "success",
            "data": {
                "total_unique_patients": data.get("total_unique_patients"),
                "patients_with_conflicts": data.get("patients_with_conflicts"),
                "conflict_rate_pct": data.get("conflict_rate_pct"),
                "total_conflicts": data.get("total_conflicts"),
                "by_severity": data.get("by_severity"),
                "by_field": data.get("by_field")
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading conflict summary: {str(e)}")

@router.post("/resolve")
def resolve_conflict(
    request: ResolveRequest, 
    current_doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db)
):
    """Mark a conflict as resolved by the doctor."""
    # Check if already resolved
    existing = db.query(ResolvedConflict).filter(
        ResolvedConflict.patient_name == request.patient_name,
        ResolvedConflict.field == request.field
    ).first()
    
    if existing:
        # Update existing resolution
        existing.resolved_value = request.resolved_value
        existing.doctor_id = current_doctor.id
        existing.notes = request.notes
        resolution = existing
    else:
        # Create new resolution
        resolution = ResolvedConflict(
            patient_name=request.patient_name,
            field=request.field,
            resolved_value=request.resolved_value,
            doctor_id=current_doctor.id,
            notes=request.notes
        )
        db.add(resolution)
        
    db.commit()
    db.refresh(resolution)
    
    return {"status": "success", "message": "Conflict resolved successfully", "data": {
        "id": resolution.id,
        "patient_name": resolution.patient_name,
        "field": resolution.field,
        "resolved_value": resolution.resolved_value
    }}
