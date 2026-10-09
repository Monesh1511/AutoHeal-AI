from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class PatchProposal(Base):
    __tablename__ = "patch_proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    patch_version: Mapped[int] = mapped_column(Integer, default=1)
    diagnosis: Mapped[str] = mapped_column(Text)
    proposed_solution: Mapped[str] = mapped_column(Text)
    diff: Mapped[str] = mapped_column(Text)
    safety_status: Mapped[str] = mapped_column(String(30), default="passed")
    status: Mapped[str] = mapped_column(String(30), default="awaiting_approval")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
