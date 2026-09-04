from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.learner.models import utc_now


class TutorTurnRecord(Base):
    __tablename__ = "tutor_turn_records"
    __table_args__ = (
        UniqueConstraint("session_id", "client_turn_id", name="uq_turn_session_client_id"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), index=True
    )
    client_turn_id: Mapped[str] = mapped_column(String(120))
    learner_turn_kind: Mapped[str] = mapped_column(String(40))
    learner_text: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    option_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expected_question_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    session_version_before: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    assessment_result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    decision_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    decision_trace_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tutor_message_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    recoverable_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    recoverable_error_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SessionMessage(Base):
    __tablename__ = "session_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence_number", name="uq_message_session_sequence"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))
    message_kind: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(String(4000))
    question_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    interaction_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    client_turn_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
