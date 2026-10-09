"""Persistence helper for the in-app human escalation queue."""

from sqlalchemy.orm import Session

from app.models.escalation import Escalation


def create_escalation(db: Session, incident_id: int, reason: str) -> Escalation:
    escalation = Escalation(incident_id=incident_id, reason=reason)
    db.add(escalation)
    db.commit()
    db.refresh(escalation)
    return escalation
