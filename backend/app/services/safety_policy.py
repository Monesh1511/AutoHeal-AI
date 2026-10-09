"""Deterministic policy gate for proposed repairs."""

from dataclasses import dataclass


SAFE_ACTIONS = frozenset(
    {"restart_dependency", "fix_configuration", "clear_stale_cache", "simulate_repair_failure"}
)


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


def evaluate_action(action: str, confidence: int, retry_count: int) -> PolicyDecision:
    if retry_count >= 1:
        return PolicyDecision(False, "retry limit reached")
    if action not in SAFE_ACTIONS:
        return PolicyDecision(False, "action is not on the safe allowlist")
    if confidence < 70:
        return PolicyDecision(False, "diagnostic confidence is below the safety threshold")
    return PolicyDecision(True, "action is allowlisted and evidence is sufficient")
