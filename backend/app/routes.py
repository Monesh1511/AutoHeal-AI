"""Initial API routes for health and incident history."""

from typing import Annotated
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.database import check_database_connection, get_db
from app.auth import get_authenticated_user, hash_password, issue_token, require_admin, verify_password
from app.config import settings
from app.models.user import User
from app.models.project import Project
from app.models.patch_proposal import PatchProposal
from app.models.approval_request import ApprovalRequest
from app.models.test_execution import TestExecution
from app.models.approval_report import ApprovalReport
from app.models.audit_log import AuditLog
from app.models.incident import Incident
from app.models.escalation import Escalation
from app.orchestrator import run_recovery
from app.schemas import (
    EscalationRead,
    HealthResponse,
    IncidentCreate,
    IncidentRead,
    ReadyResponse,
    RecoveryResponse,
    AuditLogRead,
    DiagnosticCheckRead,
    IncidentDetail,
    MetricsResponse,
    SandboxActionResponse,
    SandboxState,
    LoginRequest, LoginResponse, SetupRequest, UserRead, ProjectRead, ErrorReport,
    ApprovalAction, ApprovalRead, PatchRead, ProjectRepositoryUpdate,
    ApprovalReportRead,
)
from app.services.approval_reports import create_or_update_report, try_send_email

router = APIRouter(prefix="/api")
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_authenticated_user)]
AdminUser = Annotated[User, Depends(require_admin)]
_sandbox = SandboxState(
    active_fault=None,
    service_status="healthy",
    configuration_status="valid",
    last_action=None,
)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=ReadyResponse)
def readiness() -> ReadyResponse:
    if not check_database_connection():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "database": "unavailable"},
        )
    return ReadyResponse(status="ok", database="connected")


@router.post(
    "/incidents",
    response_model=IncidentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_incident(payload: IncidentCreate, db: DbSession) -> Incident:
    incident = Incident(**payload.model_dump())
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


@router.get("/incidents", response_model=list[IncidentRead])
def incident_history(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Incident]:
    return list(
        db.scalars(
            select(Incident).order_by(Incident.created_at.desc()).limit(limit)
        ).all()
    )


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
def incident_detail(incident_id: int, db: DbSession) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.get("/metrics", response_model=MetricsResponse)
def metrics(db: DbSession) -> MetricsResponse:
    total = db.scalar(select(func.count(Incident.id))) or 0
    recovered = db.scalar(
        select(func.count(Incident.id)).where(Incident.status == "recovered")
    ) or 0
    escalated = db.scalar(
        select(func.count(Incident.id)).where(Incident.status == "escalated")
    ) or 0
    completed = recovered + escalated
    total_projects = db.scalar(select(func.count(Project.id))) or 0
    open_errors = db.scalar(select(func.count(Incident.id)).where(Incident.status == "open")) or 0
    critical_errors = db.scalar(select(func.count(Incident.id)).where(Incident.severity == "critical")) or 0
    awaiting_approval = db.scalar(select(func.count(ApprovalRequest.id)).where(ApprovalRequest.status == "pending")) or 0
    failed_repairs = db.scalar(select(func.count(TestExecution.id)).where(TestExecution.status == "failed")) or 0
    return MetricsResponse(
        total_incidents=total,
        recovered_incidents=recovered,
        escalated_incidents=escalated,
        recovery_success_rate=round(recovered / completed * 100, 1) if completed else 0,
        total_projects=total_projects,
        open_errors=open_errors,
        critical_errors=critical_errors,
        awaiting_approval=awaiting_approval,
        failed_repairs=failed_repairs,
    )


@router.get("/sandbox", response_model=SandboxState)
def sandbox_state() -> SandboxState:
    return _sandbox


@router.post("/sandbox/faults/{fault}", response_model=SandboxActionResponse)
def inject_fault(fault: str) -> SandboxActionResponse:
    if fault not in {"service-down", "bad-configuration", "unknown", "repair-failure"}:
        raise HTTPException(status_code=400, detail="Unsupported sandbox fault")
    _sandbox.active_fault = fault
    _sandbox.last_action = f"Injected {fault}"
    _sandbox.service_status = "down" if fault == "service-down" else "degraded"
    _sandbox.configuration_status = "invalid" if fault == "bad-configuration" else "valid"
    return SandboxActionResponse(state=_sandbox, message=f"{fault} fault injected")


@router.post("/sandbox/reset", response_model=SandboxActionResponse)
def reset_sandbox() -> SandboxActionResponse:
    _sandbox.active_fault = None
    _sandbox.service_status = "healthy"
    _sandbox.configuration_status = "valid"
    _sandbox.last_action = "Sandbox reset"
    return SandboxActionResponse(state=_sandbox, message="Sandbox reset")


@router.post("/incidents/{incident_id}/recover", response_model=RecoveryResponse)
def recover_incident(incident_id: int, db: DbSession) -> RecoveryResponse:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    result = run_recovery(db, incident)
    return RecoveryResponse(
        incident_id=incident.id,
        status=result.status,
        diagnosis_source=result.diagnosis_source,
    )


@router.get("/escalations", response_model=list[EscalationRead])
def escalation_queue(db: DbSession) -> list[Escalation]:
    return list(
        db.scalars(select(Escalation).order_by(Escalation.created_at.desc())).all()
    )


@router.post("/auth/setup", response_model=UserRead, status_code=201)
def setup_user(payload: SetupRequest, db: DbSession) -> User:
    if not settings.setup_token or not hmac_compare(payload.setup_token, settings.setup_token):
        raise HTTPException(status_code=403, detail="Valid AUTOHEAL_SETUP_TOKEN is required")
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(
        username=payload.username,
        full_name=payload.full_name,
        role="user",
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: DbSession) -> LoginResponse:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return LoginResponse(access_token=issue_token(user), user=user)


@router.get("/auth/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user


@router.get("/projects", response_model=list[ProjectRead])
def projects(user: CurrentUser, db: DbSession) -> list[Project]:
    ensure_demo_project(db)
    return list(db.scalars(select(Project).order_by(Project.name)).all())


@router.put("/projects/{project_id}/github", response_model=ProjectRead)
def update_project_github(
    project_id: int,
    payload: ProjectRepositoryUpdate,
    user: AdminUser,
    db: DbSession,
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project.github_url = payload.github_url
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}/github", response_model=ProjectRead)
def remove_project_github(
    project_id: int, user: AdminUser, db: DbSession
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project.github_url = None
    db.commit()
    db.refresh(project)
    return project


@router.get("/approvals", response_model=list[ApprovalRead])
def approvals(user: AdminUser, db: DbSession) -> list[ApprovalRead]:
    records = list(
        db.scalars(
            select(ApprovalRequest).order_by(ApprovalRequest.requested_at.desc())
        ).all()
    )
    return [_approval_response(db, approval) for approval in records]


@router.get("/approvals/{approval_id}/report", response_model=ApprovalReportRead)
def approval_report(approval_id: int, user: AdminUser, db: DbSession) -> ApprovalReport:
    report = db.scalar(
        select(ApprovalReport).where(ApprovalReport.approval_id == approval_id)
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Approval report not found")
    return report


@router.get("/approvals/{approval_id}/report/download")
def download_approval_report(
    approval_id: int, user: AdminUser, db: DbSession
) -> Response:
    report = db.scalar(
        select(ApprovalReport).where(ApprovalReport.approval_id == approval_id)
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Approval report not found")
    return Response(
        content=report.content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{report.filename}"'
        },
    )


@router.get("/patches/{patch_id}", response_model=PatchRead)
def patch_detail(patch_id: int, user: AdminUser, db: DbSession) -> PatchProposal:
    patch = db.get(PatchProposal, patch_id)
    if patch is None:
        raise HTTPException(status_code=404, detail="Patch not found")
    return patch


@router.post("/ingest/alerts", response_model=IncidentRead, status_code=201)
def ingest_alert(payload: ErrorReport, user: CurrentUser, db: DbSession) -> Incident:
    project = db.scalar(select(Project).where(Project.identifier == payload.repository_id))
    if project is None or Path(project.workspace_path).resolve() != Path(settings.approved_workspace).resolve():
        raise HTTPException(status_code=403, detail="Repository is not an approved workspace")
    duplicate = db.scalar(
        select(Incident).where(
            Incident.source == payload.source,
            Incident.alert_details.contains(payload.message),
            Incident.status == "open",
        )
    )
    if duplicate:
        return duplicate
    incident = Incident(
        title=f"{payload.error_type}: {payload.message}",
        severity=payload.severity,
        source=payload.source,
        alert_details=f"{payload.file}:{payload.line}\n{payload.traceback[:12000]}",
    )
    db.add(incident)
    db.flush()
    diagnosis = "The divide function does not handle a zero divisor."
    diff = "--- a/calculator.py\n+++ b/calculator.py\n@@\n def divide(a, b):\n+    if b == 0:\n+        raise ValueError(\"Divisor cannot be zero\")\n     return a / b\n"
    patch = PatchProposal(
        incident_id=incident.id, project_id=project.id, diagnosis=diagnosis,
        proposed_solution="Raise a clear application-level ValueError for zero divisors.",
        diff=diff, safety_status="passed",
    )
    db.add(patch)
    db.flush()
    approval = ApprovalRequest(
        incident_id=incident.id, patch_id=patch.id, requested_for_user_id=user.id,
        message=f"Repair approval required for {project.name}.\n\nError: {payload.error_type} — {payload.message}.\nFile: {payload.file}, line {payload.line}.\nDiagnosis: {diagnosis}\nProposed fix: Raise a clear ValueError for zero divisors.\nRequested reviewer: {user.full_name} (@{user.username}).",
    )
    db.add(approval)
    db.flush()
    report = create_or_update_report(db, approval, incident, patch, project)
    report.notification_status = try_send_email(
        report, f"AutoHeal repair approval for incident #{incident.id}"
    )
    report.content = report.content.replace(
        "dashboard_only unless SMTP delivery is configured and confirmed",
        report.notification_status,
    )
    db.add(AuditLog(incident_id=incident.id, event_type="approval_requested", message=approval.message))
    db.commit()
    db.refresh(incident)
    return incident


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRead)
def reject_approval(approval_id: int, payload: ApprovalAction, user: AdminUser, db: DbSession) -> ApprovalRead:
    approval = db.get(ApprovalRequest, approval_id)
    if approval is None or approval.status != "pending":
        raise HTTPException(status_code=404, detail="Pending approval not found")
    approval.status, approval.reason, approval.decided_by_user_id = "rejected", payload.reason, user.id
    approval.decided_at = datetime.now(timezone.utc)
    _refresh_approval_report(db, approval)
    db.add(AuditLog(incident_id=approval.incident_id, event_type="repair_rejected", message=payload.reason or "Patch rejected"))
    db.commit()
    db.refresh(approval)
    return _approval_response(db, approval)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRead)
def approve_approval(approval_id: int, user: AdminUser, db: DbSession) -> ApprovalRead:
    approval = db.get(ApprovalRequest, approval_id)
    if approval is None or approval.status != "pending":
        raise HTTPException(status_code=404, detail="Pending approval not found")
    patch = db.get(PatchProposal, approval.patch_id)
    project = db.get(Project, patch.project_id) if patch else None
    if patch is None or project is None or patch.safety_status != "passed":
        raise HTTPException(status_code=409, detail="Patch is not safe to apply")
    target = Path(project.workspace_path) / "calculator.py"
    original = target.read_text(encoding="utf-8")
    updated = 'def divide(a, b):\n    if b == 0:\n        raise ValueError("Divisor cannot be zero")\n    return a / b\n'
    if target.name != "calculator.py" or original == updated:
        raise HTTPException(status_code=409, detail="Patch version is stale or already applied")
    target.write_text(updated, encoding="utf-8")
    try:
        run = subprocess.run([sys.executable, "-m", "pytest", "test_calculator.py", "-q"], cwd=project.workspace_path, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        target.write_text(original, encoding="utf-8")
        raise HTTPException(status_code=502, detail=f"Validation failed: {type(exc).__name__}") from exc
    if run.returncode != 0:
        target.write_text(original, encoding="utf-8")
    db.add(TestExecution(incident_id=approval.incident_id, patch_id=patch.id, status="passed" if run.returncode == 0 else "failed", output=(run.stdout + run.stderr)[:12000]))
    approval.status = "approved" if run.returncode == 0 else "failed"
    approval.decided_by_user_id, approval.decided_at = user.id, datetime.now(timezone.utc)
    patch.status = "applied" if run.returncode == 0 else "validation_failed"
    incident = db.get(Incident, approval.incident_id)
    if incident and run.returncode == 0:
        incident.status = "recovered"
    db.add(AuditLog(incident_id=approval.incident_id, event_type="repair_applied" if run.returncode == 0 else "repair_failed", message=f"Patch validation return code {run.returncode}"))
    _refresh_approval_report(db, approval)
    db.commit()
    db.refresh(approval)
    return _approval_response(db, approval)


def _approval_response(db: Session, approval: ApprovalRequest) -> ApprovalRead:
    incident = db.get(Incident, approval.incident_id)
    patch = db.get(PatchProposal, approval.patch_id)
    project = db.get(Project, patch.project_id) if patch else None
    report = db.scalar(
        select(ApprovalReport).where(ApprovalReport.approval_id == approval.id)
    )
    return ApprovalRead(
        id=approval.id,
        incident_id=approval.incident_id,
        patch_id=approval.patch_id,
        status=approval.status,
        message=approval.message,
        reason=approval.reason,
        requested_at=approval.requested_at,
        decided_at=approval.decided_at,
        recipient_email=report.recipient_email if report else settings.approval_email,
        notification_status=report.notification_status if report else "dashboard_only",
        report_filename=report.filename if report else None,
        incident_title=incident.title if incident else None,
        project_name=project.name if project else None,
    )


def _refresh_approval_report(db: Session, approval: ApprovalRequest) -> None:
    incident = db.get(Incident, approval.incident_id)
    patch = db.get(PatchProposal, approval.patch_id)
    project = db.get(Project, patch.project_id) if patch else None
    execution = db.scalar(
        select(TestExecution)
        .where(TestExecution.patch_id == approval.patch_id)
        .order_by(TestExecution.created_at.desc())
    )
    if incident:
        create_or_update_report(db, approval, incident, patch, project, execution)


def ensure_demo_project(db: Session) -> Project:
    project = db.scalar(select(Project).where(Project.identifier == "sample-python-calculator"))
    if project is None:
        project = Project(identifier="sample-python-calculator", name="Sample Python Calculator", language="Python", description="Approved local calculator workspace", workspace_path=settings.approved_workspace)
        db.add(project)
        db.commit()
        db.refresh(project)
    return project


def hmac_compare(left: str, right: str) -> bool:
    import hmac
    return hmac.compare_digest(left, right)
