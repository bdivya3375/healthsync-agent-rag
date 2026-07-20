"""
Authentication Middleware

FastAPI dependencies to extract and validate the JWT token
from requests, and retrieve the current Doctor object from the database.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Annotated

from database.connection import get_db
from database.models import Doctor
from services.auth_service import decode_access_token

# OAuth2 scheme: expects token in "Authorization: Bearer <token>" header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_doctor(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db)
) -> Doctor:
    """
    Dependency that extracts the JWT token, decodes it,
    and returns the corresponding Doctor database object.
    Throws HTTP 401 if token is invalid or user doesn't exist.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Decode token
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
        
    email: str = payload.get("sub")
    if email is None:
        raise credentials_exception
        
    # Find doctor in database
    doctor = db.query(Doctor).filter(Doctor.email == email).first()
    if doctor is None or not doctor.is_active:
        raise credentials_exception
        
    return doctor


def get_current_admin(
    current_doctor: Annotated[Doctor, Depends(get_current_doctor)]
) -> Doctor:
    """
    Dependency that enforces the user must be an admin.
    Builds on top of get_current_doctor.
    """
    if current_doctor.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges"
        )
    return current_doctor
