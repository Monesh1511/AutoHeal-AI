"""Pydantic request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    source: str = Field(default="manual", max_length=100)
    alert_details: str | None = None


class IncidentRead(IncidentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    database: str


class RecoveryResponse(BaseModel):
    incident_id: int
    status: str
    diagnosis_source: str


class EscalationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    reason: str
    status: str
    created_at: datetime


class DiagnosticCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    check_name: str
    status: str
    result: str | None
    checked_at: datetime


class HypothesisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    confidence: int
    status: str
    evidence: str | None
    created_at: datetime


class RepairAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    status: str
    output: str | None
    attempted_at: datetime


class VerificationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    check_name: str
    status: str
    details: str | None
    verified_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    message: str
    created_at: datetime


class IncidentDetail(IncidentRead):
    diagnostic_checks: list[DiagnosticCheckRead] = []
    hypotheses: list[HypothesisRead] = []
    repair_attempts: list[RepairAttemptRead] = []
    verification_results: list[VerificationResultRead] = []
    escalations: list[EscalationRead] = []
    audit_logs: list[AuditLogRead] = []


class MetricsResponse(BaseModel):
    total_incidents: int
    recovered_incidents: int
    escalated_incidents: int
    recovery_success_rate: float
    total_projects: int = 0
    open_errors: int = 0
    critical_errors: int = 0
    awaiting_approval: int = 0
    failed_repairs: int = 0


class SandboxState(BaseModel):
    active_fault: str | None
    service_status: str
    configuration_status: str
    last_action: str | None


class SandboxActionResponse(BaseModel):
    state: SandboxState
    message: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class SetupRequest(LoginRequest):
    full_name: str = Field(min_length=1, max_length=160)
    setup_token: str = Field(min_length=1)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    identifier: str
    name: str
    language: str
    description: str
    status: str
    last_analyzed_at: datetime | None
    github_url: str | None = None


class ProjectRepositoryUpdate(BaseModel):
    github_url: str = Field(min_length=1, max_length=500)

    @field_validator("github_url")
    @classmethod
    def validate_github_url(cls, value: str) -> str:
        from urllib.parse import urlparse

        candidate = value.strip()
        parsed = urlparse(candidate)
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != "github.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or len([part for part in parsed.path.split("/") if part]) != 2
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("github_url must be an HTTPS GitHub repository URL")
        parts = [part for part in parsed.path.split("/") if part]
        if any(part in parsed.path for part in ("@", ":", "\\", "..")) or any(
            part in {".", ".."} for part in parts
        ):
            raise ValueError("github_url must not contain credentials or unsafe path segments")
        return f"https://github.com/{'/'.join(parts)}"


class ErrorReport(BaseModel):
    source: str = Field(min_length=1, max_length=100)
    repository_id: str = Field(pattern=r"^[a-z0-9-]+$")
    language: str = Field(min_length=1, max_length=40)
    error_type: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)
    file: str = Field(pattern=r"^[^\\/][^\\/]*$")
    line: int = Field(ge=1, le=100000)
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    traceback: str = Field(min_length=1, max_length=20000)


class ApprovalAction(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class ApprovalRead(BaseModel):
    id: int
    incident_id: int
    patch_id: int
    status: str
    message: str
    reason: str | None
    requested_at: datetime
    decided_at: datetime | None
    recipient_email: str = "aarthi@gmail.com"
    notification_status: str = "dashboard_only"
    report_filename: str | None = None
    incident_title: str | None = None
    project_name: str | None = None


class ApprovalReportRead(BaseModel):
    id: int
    approval_id: int
    filename: str
    recipient_email: str
    notification_status: str
    content: str
    created_at: datetime
    updated_at: datetime


class PatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    incident_id: int
    project_id: int
    patch_version: int
    diagnosis: str
    proposed_solution: str
    diff: str
    safety_status: str
    status: str
    created_at: datetime
