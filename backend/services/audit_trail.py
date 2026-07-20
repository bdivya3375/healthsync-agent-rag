"""
Audit Trail Service
===================
HIPAA-compliant logging of all access and modifications to patient data.
Every view, audit, resolve, and export action is recorded with actor
identity, timestamp, and redacted patient information.
"""

import json
import logging
from typing import Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from database.models import AuditLog
from services.pii_redaction import redact_name, redact_patient_id

logger = logging.getLogger(__name__)


def log_audit_event(
    db: Session,
    actor_username: str,
    actor_role: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    resource_name: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """
    Record an audit event to the database.

    Actions: VIEW, MODIFY, AUDIT, RESOLVE, EXPORT, LOGIN, REGISTER
    Resource types: patient, conflict, admission, auth
    """
    # Redact PII in the audit log itself
    redacted_name = redact_name(resource_name) if resource_name else None
    redacted_id = redact_patient_id(resource_id) if resource_id else None

    entry = AuditLog(
        actor_username=actor_username,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=redacted_id,
        resource_name=redacted_name,
        details=json.dumps(details) if details else None,
        ip_address=ip_address,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()

    logger.info(
        "AUDIT | %s (%s) | %s %s | %s [%s]",
        actor_username, actor_role, action, resource_type,
        redacted_name or "-", redacted_id or "-",
    )


def get_audit_trail(
    db: Session,
    actor_username: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    limit: int = 100,
):
    """
    Retrieve audit trail entries with optional filtering.
    Returns the most recent entries first.
    """
    query = db.query(AuditLog)

    if actor_username:
        query = query.filter(AuditLog.actor_username == actor_username)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)

    entries = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

    return [
        {
            "id": e.id,
            "actor": e.actor_username,
            "role": e.actor_role,
            "action": e.action,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "resource_name": e.resource_name,
            "details": json.loads(e.details) if e.details else None,
            "ip_address": e.ip_address,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in entries
    ]
