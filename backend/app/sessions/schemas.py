from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.curriculum.models import LearnerStatus, ProgressStatus
from backend.app.llm.contracts import LearnerTurnKind, LLMMode
from backend.app.tutor.domain import Action, EntryMode, SessionStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class StartSessionRequest(StrictModel):
    target_node_id: str = Field(min_length=1, max_length=120)
    entry_mode: EntryMode
    client_request_id: str = Field(min_length=1, max_length=120)


class SubmitTurnRequest(StrictModel):
    client_turn_id: str = Field(min_length=1, max_length=120)
    expected_session_version: int = Field(ge=1)
    expected_question_id: str | None = Field(default=None, max_length=120)
    kind: LearnerTurnKind
    text: str = Field(default="", max_length=4000)
    selected_option_id: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_payload_shape(self) -> SubmitTurnRequest:
        if self.kind == LearnerTurnKind.SIDE_QUESTION and not self.text.strip():
            raise ValueError("SIDE_QUESTION 必须包含问题文本")
        if self.kind != LearnerTurnKind.ANSWER and self.selected_option_id is not None:
            raise ValueError("只有 ANSWER 可以提交 option_id")
        return self


class AbandonSessionRequest(StrictModel):
    expected_session_version: int = Field(ge=1)


class ChoiceOptionView(StrictModel):
    option_id: str
    label: str


class QuestionView(StrictModel):
    question_id: str
    node_id: str
    prompt: str
    response_type: Literal["single_choice", "free_text"]
    options: list[ChoiceOptionView]


class SessionNodeView(StrictModel):
    node_id: str
    title: str
    learner_status: LearnerStatus
    progress_status: ProgressStatus


class MessageRole(StrEnum):
    LEARNER = "learner"
    TUTOR = "tutor"
    SYSTEM = "system"


class SessionMessageView(StrictModel):
    message_id: str
    sequence_number: int = Field(ge=1)
    role: MessageRole
    message_kind: str
    text: str
    question_id: str | None
    interaction_type: str | None
    client_turn_id: str | None
    created_at: datetime


class AvailableActions(StrictModel):
    can_submit_answer: bool
    can_ask_side_question: bool
    can_request_hint: bool
    can_request_answer: bool
    can_report_mastery: bool
    can_abandon: bool


class LearnerStateNodeSummary(StrictModel):
    node_id: str
    learner_status: LearnerStatus
    progress_status: ProgressStatus


class RoadmapDeltaItem(StrictModel):
    node_id: str
    learner_status: LearnerStatus


class RecoverableErrorView(StrictModel):
    code: str
    message: str
    source: Literal["assessor", "teacher", "session"]


class DemoInput(StrictModel):
    label: str
    text: str
    selected_option_id: str | None = None


class SessionDebugView(StrictModel):
    session_id: str
    session_version: int
    client_turn_id: str | None
    target_node_id: str
    current_node_id: str
    expected_question_id: str | None
    current_assistance_level: str
    canonical_assessment_summary: dict[str, Any] | None
    final_action: Action | None
    reason_codes: list[str]
    remediation_target: str | None
    return_stack: list[str]
    state_delta: dict[str, Any] | None
    state_before: dict[str, Any] | None
    active_misconception_ids: list[str]
    resolved_misconception_ids: list[str]
    decision_trace_id: str | None
    llm_metadata: list[dict[str, Any]]
    llm_mode: LLMMode
    recoverable_error_code: str | None
    demo_inputs: list[DemoInput]


class TutorSessionSnapshot(StrictModel):
    session_id: str
    version: int
    status: SessionStatus
    mode: EntryMode
    target_node: SessionNodeView
    current_node: SessionNodeView
    return_stack: list[SessionNodeView]
    expected_question: QuestionView | None
    messages: list[SessionMessageView]
    available_actions: AvailableActions
    learner_state_summary: list[LearnerStateNodeSummary]
    roadmap_delta: list[RoadmapDeltaItem]
    next_ready_node: SessionNodeView | None
    llm_mode: LLMMode
    recoverable_error: RecoverableErrorView | None
    debug: SessionDebugView | None = None


class ActiveSessionSummary(StrictModel):
    session_id: str
    target_node_id: str
    current_node_id: str
    version: int
    mode: EntryMode
