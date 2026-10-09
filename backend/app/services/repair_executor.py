"""Safe, bounded repair execution without arbitrary shell commands."""

from dataclasses import dataclass

from app.services.safety_policy import SAFE_ACTIONS


@dataclass(frozen=True)
class RepairOutcome:
    action: str
    succeeded: bool
    output: str


def execute_repair(action: str) -> RepairOutcome:
    if action == "simulate_repair_failure":
        return RepairOutcome(action, False, "simulated repair failure")
    if action not in SAFE_ACTIONS:
        return RepairOutcome(action, False, "repair blocked by safety policy")
    return RepairOutcome(action, True, f"{action} completed in sandbox mode")
