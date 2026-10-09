from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    source: Mapped[str] = mapped_column(String(100), default="manual")
    alert_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    diagnostic_checks = relationship(
        "DiagnosticCheck", back_populates="incident", cascade="all, delete-orphan"
    )
    hypotheses = relationship(
        "Hypothesis", back_populates="incident", cascade="all, delete-orphan"
    )
    repair_attempts = relationship(
        "RepairAttempt", back_populates="incident", cascade="all, delete-orphan"
    )
    verification_results = relationship(
        "VerificationResult", back_populates="incident", cascade="all, delete-orphan"
    )
    escalations = relationship(
        "Escalation", back_populates="incident", cascade="all, delete-orphan"
    )
    audit_logs = relationship(
        "AuditLog", back_populates="incident", cascade="all, delete-orphan"
    )
