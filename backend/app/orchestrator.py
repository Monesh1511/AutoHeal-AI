"""Small, auditable incident recovery workflow."""

from sqlalchemy.orm import Session
from dataclasses import dataclass

from app.models.audit_log import AuditLog
from app.models.hypothesis import Hypothesis
from app.models.incident import Incident
from app.models.repair_attempt import RepairAttempt
from app.models.verification_result import VerificationResult
from app.services.escalation import create_escalation
from app.services.groq_investigator import GroqInvestigator
from app.services.hypothesis_tester import test_hypothesis
from app.services.recovery_verifier import verify_recovery
from app.services.repair_executor import execute_repair
from app.services.safety_policy import evaluate_action


@dataclass(frozen=True)
class RecoveryOutcome:
    status: str
    diagnosis_source: str


def run_recovery(db: Session, incident: Incident, logs: str = "") -> RecoveryOutcome:
    investigation = GroqInvestigator().investigate(incident.alert_details or incident.title, logs)
    for hypothesis_text in investigation.hypotheses:
        evidence = test_hypothesis(
            hypothesis_text, incident.alert_details or incident.title, logs
        )
        db.add(
            Hypothesis(
                incident_id=incident.id,
                description=hypothesis_text,
                confidence=investigation.confidence,
                status="supported" if evidence.supported else "rejected",
                evidence=evidence.evidence,
            )
        )

    decision = evaluate_action(investigation.proposed_action, investigation.confidence, 0)
    if not decision.allowed:
        create_escalation(db, incident.id, decision.reason)
        incident.status = "escalated"
        db.add(AuditLog(incident_id=incident.id, event_type="escalated", message=decision.reason))
        db.commit()
        return RecoveryOutcome("escalated", investigation.diagnosis_source)

    outcome = execute_repair(investigation.proposed_action)
    db.add(
        RepairAttempt(
            incident_id=incident.id,
            action=outcome.action,
            status="succeeded" if outcome.succeeded else "failed",
            output=outcome.output,
        )
    )
    verification = verify_recovery(outcome.succeeded)
    db.add(
        VerificationResult(
            incident_id=incident.id,
            check_name="post_repair_health",
            status="passed" if verification.recovered else "failed",
            details=verification.details,
        )
    )
    incident.status = "recovered" if verification.recovered else "escalated"
    if not verification.recovered:
        create_escalation(db, incident.id, verification.details)
    db.add(
        AuditLog(
            incident_id=incident.id,
            event_type=incident.status,
            message=verification.details,
        )
    )
    db.commit()
    return RecoveryOutcome(incident.status, investigation.diagnosis_source)
