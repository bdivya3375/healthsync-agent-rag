"""
Dashboard Routes

Endpoints for aggregate stats, charts, and clinical recommendations.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import json
import os

from middleware.auth_middleware import get_current_doctor
from database.models import Doctor, ResolvedConflict
from database.connection import get_db

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/stats")
def get_dashboard_stats(
    current_doctor: Doctor = Depends(get_current_doctor),
    db: Session = Depends(get_db)
):
    """Get high-level metrics for the dashboard home."""
    try:
        conflicts_file = os.path.join("data", "detected_conflicts.json")
        with open(conflicts_file, "r") as f:
            data = json.load(f)
            
        total_conflicts = data.get("total_conflicts", 0)
        
        # Count critical/urgent conflicts
        critical_count = data.get("by_severity", {}).get("CRITICAL", 0)
        
        # Calculate resolution rate
        resolved_count = db.query(ResolvedConflict).count()
        resolution_rate = round((resolved_count / total_conflicts * 100) if total_conflicts > 0 else 0, 1)
        
        return {
            "status": "success",
            "data": {
                "total_patients": data.get("total_unique_patients", 0),
                "patients_with_conflicts": data.get("patients_with_conflicts", 0),
                "total_conflicts": total_conflicts,
                "critical_conflicts": critical_count,
                "resolved_conflicts": resolved_count,
                "resolution_rate_pct": resolution_rate
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading dashboard stats: {str(e)}")

@router.get("/recommendations")
def get_all_recommendations(current_doctor: Doctor = Depends(get_current_doctor)):
    """Get all clinical recommendations across all patients."""
    try:
        conflicts_file = os.path.join("data", "detected_conflicts.json")
        with open(conflicts_file, "r") as f:
            data = json.load(f)
            
        recommendations = []
        for report in data.get("patient_reports", []):
            patient_name = report.get("patient_name")
            for conflict in report.get("conflicts", []):
                rec = conflict.get("recommendation")
                if rec:
                    recommendations.append({
                        "patient_name": patient_name,
                        "field": conflict.get("field"),
                        "severity": conflict.get("severity"),
                        "recommendation": rec
                    })
                    
        return {"status": "success", "count": len(recommendations), "data": recommendations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading recommendations: {str(e)}")

@router.get("/recommendations/urgent")
def get_urgent_recommendations(current_doctor: Doctor = Depends(get_current_doctor)):
    """Get only IMMEDIATE urgency clinical recommendations."""
    try:
        conflicts_file = os.path.join("data", "detected_conflicts.json")
        with open(conflicts_file, "r") as f:
            data = json.load(f)
            
        urgent_recs = []
        for report in data.get("patient_reports", []):
            patient_name = report.get("patient_name")
            for conflict in report.get("conflicts", []):
                rec = conflict.get("recommendation")
                if rec and rec.get("urgency") == "IMMEDIATE":
                    urgent_recs.append({
                        "patient_name": patient_name,
                        "field": conflict.get("field"),
                        "severity": conflict.get("severity"),
                        "recommendation": rec
                    })
                    
        return {"status": "success", "count": len(urgent_recs), "data": urgent_recs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading urgent recommendations: {str(e)}")
