import pytest
from types import SimpleNamespace

from app.database import check_database_connection
from app.models.incident import Incident
from app.models.approval_report import ApprovalReport
from app.models.approval_request import ApprovalRequest
from app.models.patch_proposal import PatchProposal
from app.models.project import Project
from app.models.user import User
from app.schemas import IncidentCreate
from app.services.safety_policy import evaluate_action
from app.services.groq_investigator import GroqInvestigator


def test_configured_database_connection():
    if not check_database_connection():
        pytest.skip("configured PostgreSQL instance is unavailable")
    assert check_database_connection()


def test_incident_schema_rejects_invalid_severity():
    try:
        IncidentCreate(title="database outage", severity="urgent")
    except Exception as exc:
        assert "severity" in str(exc)
    else:
        raise AssertionError("invalid severity should be rejected")


def test_incident_persistence(db_session):
    incident = Incident(title="connection refused", severity="high")
    db_session.add(incident)
    db_session.commit()
    db_session.refresh(incident)

    assert incident.id is not None
    assert db_session.get(Incident, incident.id).title == "connection refused"


def test_health_and_incident_history(client):
    assert client.get("/api/health").json() == {"status": "ok"}

    created = client.post(
        "/api/incidents",
        json={"title": "worker crash", "severity": "critical"},
    )
    assert created.status_code == 201
    assert created.json()["status"] == "open"

    history = client.get("/api/incidents")
    assert history.status_code == 200
    assert history.json()[0]["title"] == "worker crash"


def test_safety_policy_blocks_unknown_actions():
    decision = evaluate_action("delete_database", confidence=100, retry_count=0)
    assert decision.allowed is False


def test_groq_response_is_marked_as_groq_and_uses_configured_model(monkeypatch):
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"diagnosis":"worker fault","hypotheses":["worker crash"],"proposed_action":"escalate","confidence":75,"evidence":"log evidence"}'
                        )
                    )
                ]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    result = GroqInvestigator(client=client).investigate("worker crashed")

    assert result.diagnosis_source == "groq"
    assert calls[0]["model"] == "openai/gpt-oss-20b"


def test_groq_markdown_json_with_structured_hypotheses_is_normalized():
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=(
                                    "```json\n"
                                    '{"diagnosis":"queue bottleneck",'
                                    '"hypotheses":[{"description":"broker saturation"}],'
                                    '"proposed_action":["collect metrics"],'
                                    '"confidence":70,"evidence":"retry logs"}\n'
                                    "```"
                                )
                            )
                        )
                    ]
                )
            )
        )
    )

    result = GroqInvestigator(client=client).investigate("queue retries")

    assert result.diagnosis_source == "groq"
    assert result.hypotheses == ["broker saturation"]
    assert result.proposed_action == "collect metrics"


def test_empty_groq_response_is_marked_as_api_error():
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=""))]
                )
            )
        )
    )

    result = GroqInvestigator(client=client).investigate("unknown worker fault")

    assert result.diagnosis_source == "fallback_api_error"
    assert "unavailable or invalid" in result.evidence


def test_unknown_incident_is_escalated(client, monkeypatch):
    from app import orchestrator
    from app.services.groq_investigator import InvestigationResult

    class FakeInvestigator:
        def investigate(self, alert, logs=""):
            return InvestigationResult(
                diagnosis="unknown",
                hypotheses=["unknown fault"],
                proposed_action="escalate",
                confidence=10,
                evidence="no match",
                diagnosis_source="fallback",
            )

    monkeypatch.setattr(orchestrator, "GroqInvestigator", FakeInvestigator)
    created = client.post("/api/incidents", json={"title": "unknown fault"})
    response = client.post(f"/api/incidents/{created.json()['id']}/recover")
    assert response.status_code == 200
    assert response.json()["status"] == "escalated"
    assert len(client.get("/api/escalations").json()) == 1


def test_authentication_and_project_access(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "setup_token", "one-time-test-token")
    setup = client.post(
        "/api/auth/setup",
        json={
            "username": "aarthi",
            "full_name": "Aarthi G D",
            "password": "test-password",
            "setup_token": "one-time-test-token",
        },
    )
    assert setup.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"username": "aarthi", "password": "test-password"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert client.get("/api/projects").status_code == 401
    projects = client.get("/api/projects", headers={"Authorization": f"Bearer {token}"})
    assert projects.status_code == 200
    assert projects.json()[0]["identifier"] == "sample-python-calculator"


def test_auth_routes_are_registered_and_invalid_login_is_unauthorized(client):
    auth_paths = {
        path
        for path in client.get("/openapi.json").json()["paths"]
        if path.startswith("/api/auth/")
    }
    assert auth_paths == {
        "/api/auth/login",
        "/api/auth/me",
        "/api/auth/setup",
    }

    response = client.post(
        "/api/auth/login",
        json={"username": "missing-user", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_default_admin_seed_is_idempotent_and_login_returns_role(db_session, client, monkeypatch):
    from app.config import settings
    from app.seed import seed_default_admin
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "admin_email", "admin@gmail.com")
    monkeypatch.setattr(settings, "admin_password", SecretStr("admin@123"))
    monkeypatch.setattr(settings, "admin_display_name", "Aarthi GD")
    first = seed_default_admin(db_session)
    original_hash = first.password_hash
    second = seed_default_admin(db_session)

    assert first.id == second.id
    assert second.password_hash == original_hash
    assert second.role == "admin"
    assert db_session.query(Incident).count() == 0

    response = client.post(
        "/api/auth/login",
        json={"username": "admin@gmail.com", "password": "admin@123"},
    )
    assert response.status_code == 200
    assert response.json()["user"] == {
        "id": first.id,
        "username": "admin@gmail.com",
        "full_name": "Aarthi GD",
        "role": "admin",
    }
    assert client.post(
        "/api/auth/login",
        json={"username": "admin@gmail.com", "password": "wrong"},
    ).status_code == 401


def test_approval_queue_requires_admin_role(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "setup_token", "one-time-test-token")
    client.post(
        "/api/auth/setup",
        json={
            "username": "user@example.com",
            "full_name": "Regular User",
            "password": "test-password",
            "setup_token": "one-time-test-token",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "user@example.com", "password": "test-password"},
    )
    token = login.json()["access_token"]
    assert client.get(
        "/api/approvals", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 403


def test_approval_report_contains_real_data_and_is_downloadable(
    db_session, client, monkeypatch
):
    from app.auth import hash_password, issue_token
    from app.config import settings
    from app.services.approval_reports import create_or_update_report

    admin = User(
        username="report-admin",
        full_name="Report Admin",
        role="admin",
        password_hash=hash_password("password"),
    )
    project = Project(
        identifier="report-project",
        name="Report Project",
        language="Python",
        description="Test project",
        workspace_path=str(settings.approved_workspace),
    )
    incident = Incident(
        title="Division failed",
        severity="high",
        source="pytest",
        alert_details="calculator.py:4\nZeroDivisionError: division by zero",
    )
    db_session.add_all([admin, project, incident])
    db_session.flush()
    patch = PatchProposal(
        incident_id=incident.id,
        project_id=project.id,
        diagnosis="The divisor is not checked.",
        proposed_solution="Raise a clear ValueError.",
        diff="@@ -1 +1 @@\n- return a / b\n+ if b == 0: raise ValueError",
    )
    db_session.add(patch)
    db_session.flush()
    approval = ApprovalRequest(
        incident_id=incident.id,
        patch_id=patch.id,
        requested_for_user_id=admin.id,
        message="Approval required",
    )
    db_session.add(approval)
    db_session.flush()
    create_or_update_report(db_session, approval, incident, patch, project)
    db_session.commit()

    token = issue_token(admin)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get(
        f"/api/approvals/{approval.id}/report", headers=headers
    )
    assert response.status_code == 200
    assert "ZeroDivisionError" in response.json()["content"]
    assert "The divisor is not checked." in response.json()["content"]

    download = client.get(
        f"/api/approvals/{approval.id}/report/download", headers=headers
    )
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/markdown")
    assert "Division failed" in download.text


def test_rejecting_pending_approval_records_decision_without_applying_patch(
    db_session, client
):
    from app.auth import hash_password, issue_token

    admin = User(
        username="reject-admin",
        full_name="Reject Admin",
        role="admin",
        password_hash=hash_password("password"),
    )
    project = Project(
        identifier="reject-project",
        name="Reject Project",
        language="Python",
        description="Test project",
        workspace_path="not-used",
    )
    incident = Incident(title="Pending repair", alert_details="actual error")
    db_session.add_all([admin, project, incident])
    db_session.flush()
    patch = PatchProposal(
        incident_id=incident.id,
        project_id=project.id,
        diagnosis="Actual diagnosis",
        proposed_solution="Actual solution",
        diff="actual diff",
    )
    db_session.add(patch)
    db_session.flush()
    approval = ApprovalRequest(
        incident_id=incident.id,
        patch_id=patch.id,
        requested_for_user_id=admin.id,
        message="Approval required",
    )
    db_session.add(approval)
    db_session.commit()

    response = client.post(
        f"/api/approvals/{approval.id}/reject",
        headers={"Authorization": f"Bearer {issue_token(admin)}"},
        json={"reason": "Not approved"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert db_session.get(PatchProposal, patch.id).status == "awaiting_approval"


def test_failed_approval_validation_restores_original_source(
    db_session, client, monkeypatch, tmp_path
):
    from app.auth import hash_password, issue_token
    from app import routes

    target = tmp_path / "calculator.py"
    original = "def divide(a, b):\n    return a / b\n"
    target.write_text(original, encoding="utf-8")
    admin = User(
        username="failure-admin",
        full_name="Failure Admin",
        role="admin",
        password_hash=hash_password("password"),
    )
    project = Project(
        identifier="failure-project",
        name="Failure Project",
        language="Python",
        description="Test project",
        workspace_path=str(tmp_path),
    )
    incident = Incident(title="Validation failure", alert_details="test failure")
    db_session.add_all([admin, project, incident])
    db_session.flush()
    patch = PatchProposal(
        incident_id=incident.id,
        project_id=project.id,
        diagnosis="Diagnosis",
        proposed_solution="Solution",
        diff="Diff",
    )
    db_session.add(patch)
    db_session.flush()
    approval = ApprovalRequest(
        incident_id=incident.id,
        patch_id=patch.id,
        requested_for_user_id=admin.id,
        message="Approval required",
    )
    db_session.add(approval)
    db_session.commit()

    monkeypatch.setattr(
        routes.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout="FAILED", stderr="assertion failed"
        ),
    )
    response = client.post(
        f"/api/approvals/{approval.id}/approve",
        headers={"Authorization": f"Bearer {issue_token(admin)}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert target.read_text(encoding="utf-8") == original


def test_admin_can_persist_valid_github_repository_and_remove_it(db_session, client):
    from app.auth import hash_password, issue_token

    admin = User(
        username="github-admin",
        full_name="GitHub Admin",
        role="admin",
        password_hash=hash_password("password"),
    )
    project = Project(
        identifier="github-project",
        name="GitHub Project",
        language="Python",
        description="Test project",
        workspace_path="not-used",
    )
    db_session.add_all([admin, project])
    db_session.commit()
    headers = {"Authorization": f"Bearer {issue_token(admin)}"}

    saved = client.put(
        f"/api/projects/{project.id}/github",
        headers=headers,
        json={"github_url": "https://github.com/octocat/Hello-World"},
    )
    assert saved.status_code == 200
    assert saved.json()["github_url"] == "https://github.com/octocat/Hello-World"
    assert db_session.get(Project, project.id).github_url == "https://github.com/octocat/Hello-World"

    projects = client.get("/api/projects", headers=headers)
    assert projects.json()[0]["github_url"] == "https://github.com/octocat/Hello-World"

    removed = client.delete(f"/api/projects/{project.id}/github", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["github_url"] is None


def test_github_repository_rejects_invalid_urls_and_non_admin_updates(db_session, client):
    from app.auth import hash_password, issue_token

    admin = User(
        username="github-validator",
        full_name="GitHub Validator",
        role="admin",
        password_hash=hash_password("password"),
    )
    user = User(
        username="github-user",
        full_name="GitHub User",
        role="user",
        password_hash=hash_password("password"),
    )
    project = Project(
        identifier="github-security-project",
        name="GitHub Security Project",
        language="Python",
        description="Test project",
        workspace_path="not-used",
    )
    db_session.add_all([admin, user, project])
    db_session.commit()
    headers = {"Authorization": f"Bearer {issue_token(user)}"}

    assert client.put(
        f"/api/projects/{project.id}/github",
        headers=headers,
        json={"github_url": "https://github.com/owner/repo"},
    ).status_code == 403

    invalid_headers = {"Authorization": f"Bearer {issue_token(admin)}"}
    invalid = client.put(
        f"/api/projects/{project.id}/github",
        headers=invalid_headers,
        json={"github_url": "https://example.com/owner/repo"},
    )
    assert invalid.status_code == 422
    assert client.put(
        f"/api/projects/{project.id}/github",
        headers=invalid_headers,
        json={"github_url": "http://github.com/owner/repo"},
    ).status_code == 422
    assert client.put(
        f"/api/projects/{project.id}/github",
        headers=invalid_headers,
        json={"github_url": "https://user:pass@github.com/owner/repo"},
    ).status_code == 422
