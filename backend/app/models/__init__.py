"""Database models."""

from app.database import Base
from app.models.audit_log import AuditLog
from app.models.diagnostic_check import DiagnosticCheck
from app.models.escalation import Escalation
from app.models.hypothesis import Hypothesis
from app.models.incident import Incident
from app.models.repair_attempt import RepairAttempt
from app.models.verification_result import VerificationResult
from app.models.user import User
from app.models.project import Project
from app.models.patch_proposal import PatchProposal
from app.models.approval_request import ApprovalRequest
from app.models.test_execution import TestExecution
from app.models.approval_report import ApprovalReport

BaseModelRegistry = Base

__all__ = [
    "AuditLog",
    "BaseModelRegistry",
    "DiagnosticCheck",
    "Escalation",
    "Hypothesis",
    "Incident",
    "RepairAttempt",
    "VerificationResult",
    "User",
    "Project",
    "PatchProposal",
    "ApprovalRequest",
    "TestExecution",
    "ApprovalReport",
]
