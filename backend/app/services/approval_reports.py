from email.message import EmailMessage
import smtplib
from pathlib import Path

from app.config import settings
from app.models.approval_report import ApprovalReport


def _value(value: object | None) -> str:
    return str(value) if value is not None and str(value).strip() else "Not available"


def build_report_content(approval, incident, patch, project, test_execution=None) -> str:
    alert_details = _value(incident.alert_details)
    test_result = (
        f"{test_execution.status}\n\n{_value(test_execution.output)}"
        if test_execution
        else "Not available"
    )
    return f"""# AutoHeal Repair Approval Report

## Incident summary
- Incident ID: {incident.id}
- Incident title: {_value(incident.title)}
- Project: {_value(project.name if project else None)}
- Severity: {_value(incident.severity)}
- Created: {_value(incident.created_at)}
- Approval status: {_value(approval.status)}
- Approval request created: {_value(approval.requested_at)}

## Actual error and evidence
{alert_details}

## Diagnosis
{_value(patch.diagnosis if patch else None)}

## Proposed solution
{_value(patch.proposed_solution if patch else None)}

## Affected file and stack trace
{alert_details}

## Before-and-after code diff
```diff
{_value(patch.diff if patch else None)}
```

## Tests and results
{test_result}

## Notification
- Recipient: {settings.approval_email}
- Delivery status: dashboard_only unless SMTP delivery is configured and confirmed
"""


def create_or_update_report(db, approval, incident, patch, project, test_execution=None):
    ApprovalReport.__table__.create(bind=db.get_bind(), checkfirst=True)
    report = db.query(ApprovalReport).filter_by(approval_id=approval.id).one_or_none()
    if report is None:
        report = ApprovalReport(
            approval_id=approval.id,
            filename=f"autoheal-approval-{approval.id}.md",
            recipient_email=settings.approval_email,
            notification_status="dashboard_only",
            content="",
        )
        db.add(report)
    report.content = build_report_content(
        approval, incident, patch, project, test_execution
    )
    return report


def try_send_email(report: ApprovalReport, subject: str) -> str:
    if not all(
        (
            settings.smtp_host,
            settings.smtp_username,
            settings.smtp_password.get_secret_value(),
            settings.smtp_from,
        )
    ):
        return "dashboard_only"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = report.recipient_email
    message.set_content(report.content)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(
                settings.smtp_username,
                settings.smtp_password.get_secret_value(),
            )
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        return "email_failed_dashboard_available"
    return "email_sent"
