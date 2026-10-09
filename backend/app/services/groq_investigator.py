"""Bounded Groq-backed investigation with deterministic safe fallbacks."""

import json
from typing import Any, Literal

from groq import Groq
from pydantic import BaseModel, Field, ValidationError

from app.config import settings


class InvestigationResult(BaseModel):
    diagnosis: str = Field(min_length=1)
    hypotheses: list[str] = Field(min_length=1, max_length=5)
    proposed_action: str = "escalate"
    confidence: int = Field(ge=0, le=100)
    evidence: str = Field(min_length=1)
    diagnosis_source: Literal["groq", "fallback", "fallback_api_error"] = "groq"


class GroqInvestigator:
    def __init__(self, client: Any | None = None):
        self.client = client or Groq(api_key=settings.groq_api_key.get_secret_value())

    def investigate(self, alert: str, logs: str = "") -> InvestigationResult:
        fallback = self._fallback(alert, logs)
        if any(
            signature in f"{alert} {logs}".lower()
            for signature in ("service-down", "bad-configuration", "repair-failure")
        ):
            return fallback
        for _ in range(2):
            try:
                response = self.client.chat.completions.create(
                    model=settings.groq_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Return only a compact JSON object with diagnosis, "
                                "up to 3 short string hypotheses, one short "
                                "proposed_action string, confidence (0-100), and "
                                "brief evidence. Do not use markdown fences."
                            ),
                        },
                        {"role": "user", "content": f"Alert: {alert}\nLogs: {logs}"},
                    ],
                    temperature=0,
                    max_tokens=800,
                    timeout=10,
                )
                content = response.choices[0].message.content or ""
                if not content.strip():
                    return self._api_error_fallback(alert, logs)
                return self._parse_response(content)
            except (ValidationError, ValueError, TypeError, IndexError, json.JSONDecodeError):
                return self._api_error_fallback(alert, logs)
            except Exception:
                return self._api_error_fallback(alert, logs)
        return fallback

    @staticmethod
    def _parse_response(content: str) -> InvestigationResult:
        normalized = content.strip()
        if normalized.startswith("```"):
            normalized = normalized.split("\n", 1)[1]
            normalized = normalized.rsplit("```", 1)[0].strip()
        payload = json.loads(normalized)
        if not isinstance(payload, dict):
            raise ValueError("Groq response must be a JSON object")

        hypotheses = payload.get("hypotheses")
        if isinstance(hypotheses, list):
            payload["hypotheses"] = [
                item
                if isinstance(item, str)
                else item.get("description", "")
                for item in hypotheses
            ]
        proposed_action = payload.get("proposed_action")
        if isinstance(proposed_action, list):
            payload["proposed_action"] = "; ".join(
                str(action) for action in proposed_action if str(action).strip()
            )
        return InvestigationResult.model_validate(payload)

    @staticmethod
    def _fallback(alert: str, logs: str) -> InvestigationResult:
        evidence = f"Recognized signature in alert/logs: {alert} {logs}".strip()
        text = evidence.lower()
        if (
            "connection refused" in text
            or "database unavailable" in text
            or "service-down" in text
        ):
            return InvestigationResult(
                diagnosis="The database dependency is unavailable.",
                hypotheses=["Database connection failure"],
                proposed_action="restart_dependency",
                confidence=85,
                evidence=evidence,
                diagnosis_source="fallback",
            )
        if "bad-configuration" in text:
            return InvestigationResult(
                diagnosis="The sandbox contains an invalid service configuration.",
                hypotheses=["Configuration validation failure"],
                proposed_action="fix_configuration",
                confidence=88,
                evidence=evidence,
                diagnosis_source="fallback",
            )
        if "repair-failure" in text:
            return InvestigationResult(
                diagnosis="The proposed sandbox repair is configured to fail.",
                hypotheses=["Repair execution failure"],
                proposed_action="simulate_repair_failure",
                confidence=90,
                evidence=evidence,
                diagnosis_source="fallback",
            )
        return InvestigationResult(
            diagnosis="The fault signature is not recognized safely.",
            hypotheses=["Unknown application fault"],
            proposed_action="escalate",
            confidence=20,
            evidence=evidence,
            diagnosis_source="fallback",
        )

    @staticmethod
    def _api_error_fallback(alert: str, logs: str) -> InvestigationResult:
        result = GroqInvestigator._fallback(alert, logs)
        return result.model_copy(
            update={
                "diagnosis_source": "fallback_api_error",
                "evidence": (
                    f"{result.evidence}; Groq response was unavailable or invalid."
                ),
            }
        )
