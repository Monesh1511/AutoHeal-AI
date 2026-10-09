"""Read-only diagnostic evidence checks."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HypothesisEvidence:
    hypothesis: str
    supported: bool
    evidence: str


def test_hypothesis(hypothesis: str, alert: str, logs: str = "") -> HypothesisEvidence:
    text = f"{alert} {logs}".lower()
    supported = "connection refused" in text or "database unavailable" in text
    return HypothesisEvidence(
        hypothesis=hypothesis,
        supported=supported,
        evidence="matching dependency error signature" if supported else "no safe match",
    )
