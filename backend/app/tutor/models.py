from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.learner.models import utc_now


class LearningSession(Base):
    __tablename__ = "learning_sessions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    learner_id: Mapped[str] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[str] = mapped_column(String(24))
    target_node_id: Mapped[str] = mapped_column(String(120))
    current_node_id: Mapped[str] = mapped_column(String(120))
    expected_question_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    return_stack_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24))
    last_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    current_assistance_level: Mapped[str] = mapped_column(String(32), default="none")
    used_target_diagnostic_probes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    current_question_is_diagnostic_probe: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DecisionTraceRecord(Base):
    __tablename__ = "decision_traces"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), index=True
    )
    session_input_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    assessment_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    state_before_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    candidate_actions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    final_action: Mapped[str] = mapped_column(String(40))
    target_node_id: Mapped[str] = mapped_column(String(120))
    reason_codes_json: Mapped[list[str]] = mapped_column(JSON)
    state_delta_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    next_expected_question_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
