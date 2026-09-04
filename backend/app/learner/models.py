from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Learner(Base):
    __tablename__ = "learners"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    target_role: Mapped[str] = mapped_column(String(160))
    background_assumptions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    teaching_preferences_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    active_seed: Mapped[str] = mapped_column(String(40), default="clean")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    node_states: Mapped[list[LearnerNodeState]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )
    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )
    misconceptions: Mapped[list[LearnerMisconception]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )


class LearnerNodeState(Base):
    __tablename__ = "learner_node_states"

    learner_id: Mapped[str] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True
    )
    node_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    progress_status: Mapped[str] = mapped_column(String(32))
    mastery_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_weight: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ever_mastered: Mapped[bool] = mapped_column(Boolean, default=False)
    is_seeded_assumption: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    learner: Mapped[Learner] = relationship(back_populates="node_states")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    learner_id: Mapped[str] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    node_id: Mapped[str] = mapped_column(String(120), index=True)
    question_id: Mapped[str] = mapped_column(String(120))
    evidence_type: Mapped[str] = mapped_column(String(40))
    score: Mapped[float] = mapped_column(Float)
    weight: Mapped[float] = mapped_column(Float)
    assistance_level: Mapped[str] = mapped_column(String(40))
    rubric_results_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    misconception_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    learner: Mapped[Learner] = relationship(back_populates="evidence")


class LearnerMisconception(Base):
    __tablename__ = "learner_misconceptions"

    learner_id: Mapped[str] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), primary_key=True
    )
    misconception_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    node_id: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(24))
    evidence_ids_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    learner: Mapped[Learner] = relationship(back_populates="misconceptions")


class ImmutableEvidenceError(RuntimeError):
    pass


@event.listens_for(Evidence, "before_update")
def _reject_evidence_update(*_: object) -> None:
    raise ImmutableEvidenceError("Evidence 是不可变记录，不能更新")


@event.listens_for(Evidence, "before_delete")
def _reject_evidence_delete(*_: object) -> None:
    raise ImmutableEvidenceError("Evidence 是不可变记录，不能删除；仅 reset 可重建演示数据")
