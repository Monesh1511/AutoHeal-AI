"""Independent recovery verification."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationOutcome:
    recovered: bool
    details: str


def verify_recovery(repair_succeeded: bool, current_alert: str = "") -> VerificationOutcome:
    if repair_succeeded and not current_alert.strip():
        return VerificationOutcome(True, "post-repair health check passed")
    return VerificationOutcome(False, "health check still reports an active fault")
