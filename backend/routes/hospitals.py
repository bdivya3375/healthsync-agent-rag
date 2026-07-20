"""
Hospital Routes

Endpoints for hospital reliability scores.
"""

from fastapi import APIRouter, Depends, HTTPException
import json
import os

from middleware.auth_middleware import get_current_doctor
from database.models import Doctor

router = APIRouter(prefix="/hospitals", tags=["Hospitals"])

@router.get("/scores")
def get_hospital_scores(current_doctor: Doctor = Depends(get_current_doctor)):
    """Get reliability scores for all hospitals."""
    try:
        conflicts_file = os.path.join("data", "detected_conflicts.json")
        with open(conflicts_file, "r") as f:
            data = json.load(f)
            
        scores = data.get("hospital_reliability", [])
        return {"status": "success", "data": scores}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading hospital scores: {str(e)}")

@router.get("/{hospital_name}/score")
def get_single_hospital_score(hospital_name: str, current_doctor: Doctor = Depends(get_current_doctor)):
    """Get detailed reliability score for a single hospital."""
    try:
        conflicts_file = os.path.join("data", "detected_conflicts.json")
        with open(conflicts_file, "r") as f:
            data = json.load(f)
            
        for score in data.get("hospital_reliability", []):
            # Case-insensitive match for hospital names
            if score.get("hospital").lower() == hospital_name.lower():
                return {"status": "success", "data": score}
                
        raise HTTPException(status_code=404, detail="Hospital not found in scores data")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading hospital score: {str(e)}")
