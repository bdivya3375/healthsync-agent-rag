"""
Patient Routes

Endpoints for retrieving merged patient data.
Requires authentication.
"""

from fastapi import APIRouter, Depends, HTTPException
import json
import os
from typing import List, Dict, Any

from middleware.auth_middleware import get_current_doctor
from database.models import Doctor

router = APIRouter(prefix="/patients", tags=["Patients"])

def get_merged_patients() -> List[Dict[str, Any]]:
    # Simple placeholder: reads the JSON output from conflict detector
    # Or processes it dynamically in a real scenario
    pass

@router.get("/")
def list_patients(current_doctor: Doctor = Depends(get_current_doctor)):
    """Return list of patients."""
    # In a full implementation, this would read the processed patient records.
    # We can use the processed patients from data_pipeline if cached, 
    # but for now we might just list patient names found in detected_conflicts.json
    try:
        conflicts_file = os.path.join("data", "detected_conflicts.json")
        with open(conflicts_file, "r") as f:
            data = json.load(f)
        
        # Extract unique patients
        patients = []
        for report in data.get("patient_reports", []):
            patients.append({
                "patient_name": report.get("patient_name"),
                "matched_ids": report.get("matched_ids"),
                "total_sources": report.get("total_sources"),
                "has_critical_conflicts": report.get("has_critical")
            })
            
        return {"status": "success", "count": len(patients), "data": patients}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading patient data: {str(e)}")

@router.get("/{patient_name}")
def get_patient(patient_name: str, current_doctor: Doctor = Depends(get_current_doctor)):
    """Get details for a specific patient."""
    try:
        conflicts_file = os.path.join("data", "detected_conflicts.json")
        with open(conflicts_file, "r") as f:
            data = json.load(f)
            
        for report in data.get("patient_reports", []):
            if report.get("patient_name").lower() == patient_name.lower():
                return {"status": "success", "data": report}
                
        raise HTTPException(status_code=404, detail="Patient not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading patient data: {str(e)}")
