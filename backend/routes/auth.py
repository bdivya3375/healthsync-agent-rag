"""
Auth Routes

Endpoints for registering new doctors and logging in to receive a JWT.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from database.connection import get_db
from database.models import Doctor
from services.auth_service import get_password_hash, verify_password, create_access_token
from middleware.auth_middleware import get_current_doctor

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Pydantic schemas for requests/responses
class DoctorCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    hospital: str
    specialisation: Optional[str] = None

class DoctorResponse(BaseModel):
    id: int
    full_name: str
    email: str
    hospital: str
    role: str
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str


@router.post("/register", response_model=DoctorResponse, status_code=status.HTTP_201_CREATED)
def register_doctor(doctor: DoctorCreate, db: Session = Depends(get_db)):
    """Register a new doctor account."""
    # Check if email exists
    db_doctor = db.query(Doctor).filter(Doctor.email == doctor.email).first()
    if db_doctor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
        
    # Create new doctor
    hashed_password = get_password_hash(doctor.password)
    new_doctor = Doctor(
        full_name=doctor.full_name,
        email=doctor.email,
        password_hash=hashed_password,
        hospital=doctor.hospital,
        specialisation=doctor.specialisation
    )
    
    db.add(new_doctor)
    db.commit()
    db.refresh(new_doctor)
    
    return new_doctor


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Login endpoint. Requires username (email) and password in form-data.
    Returns a JWT Bearer token.
    """
    # Authenticate user
    doctor = db.query(Doctor).filter(Doctor.email == form_data.username).first()
    if not doctor or not verify_password(form_data.password, doctor.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not doctor.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account"
        )
        
    # Generate token
    access_token = create_access_token(data={"sub": doctor.email})
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=DoctorResponse)
def get_current_user_profile(current_doctor: Doctor = Depends(get_current_doctor)):
    """Return the profile of the currently logged-in doctor."""
    return current_doctor
