from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.curriculum.models import AccessStatus, LearnerStatus, ProgressStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class Action(StrEnum):
    ORIENT = "ORIENT"
    TEACH = "TEACH"
    ASK = "ASK"
    ASSESS = "ASSESS"
    HINT = "HINT"
    RETRY = "RETRY"
    REMEDIATE = "REMEDIATE"
    REVIEW = "REVIEW"
    ADVANCE = "ADVANCE"
    ANSWER_SIDE_QUESTION = "ANSWER_SIDE_QUESTION"


class ReasonCode(StrEnum):
    TARGET_LOCKED = "TARGET_LOCKED"
    TARGET_DIAGNOSTIC_PROBE = "TARGET_DIAGNOSTIC_PROBE"
    CRITICAL_MISCONCEPTION_DETECTED = "CRITICAL_MISCONCEPTION_DETECTED"
    WEAK_PREREQUISITE = "WEAK_PREREQUISITE"
    CURRENT_ANSWER_INCORRECT = "CURRENT_ANSWER_INCORRECT"
    PARTIAL_UNDERSTANDING = "PARTIAL_UNDERSTANDING"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
    MASTERY_REQUIREMENTS_MET = "MASTERY_REQUIREMENTS_MET"
    RETURN_TO_TARGET = "RETURN_TO_TARGET"
    SELF_REPORTED_MASTERY_IGNORED = "SELF_REPORTED_MASTERY_IGNORED"
    SIDE_QUESTION_PRESERVED = "SIDE_QUESTION_PRESERVED"
    INVALID_ASSESSMENT = "INVALID_ASSESSMENT"
    ANSWER_AMBIGUOUS = "ANSWER_AMBIGUOUS"
    NODE_AVAILABLE = "NODE_AVAILABLE"
    NO_AVAILABLE_REMEDIATION = "NO_AVAILABLE_REMEDIATION"
    HINT_REQUESTED = "HINT_REQUESTED"
    ANSWER_REVEALED = "ANSWER_REVEALED"


class Understanding(StrEnum):
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    CORRECT = "correct"
    UNCERTAIN = "uncertain"


class RubricResultValue(StrEnum):
    MET = "met"
    UNCERTAIN = "uncertain"
    NOT_MET = "not_met"


class RecommendedAction(StrEnum):
    ASK_FOLLOWUP = "ask_followup"
    HINT = "hint"
    RETRY = "retry"
    REMEDIATE = "remediate"
    ASSESS_TRANSFER = "assess_transfer"
    ADVANCE_CANDIDATE = "advance_candidate"


class RubricResult(StrictModel):
    criterion_id: str = Field(min_length=1, max_length=120)
    result: RubricResultValue
    evidence_span: str = Field(max_length=400)


class AssessmentResult(StrictModel):
    question_id: str = Field(min_length=1, max_length=120)
    node_id: str = Field(min_length=1, max_length=120)
    understanding: Understanding
    score: float = Field(ge=0, le=1)
    rubric_results: list[RubricResult] = Field(min_length=1, max_length=64)
    misconception_ids: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        max_length=16
    )
    missing_concept_ids: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(
        max_length=32
    )
    answer_is_ambiguous: bool
    feedback_points: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(max_length=4)
    recommended_action: RecommendedAction
    recommended_target_node_id: Annotated[str, Field(min_length=1, max_length=120)] | None

    @model_validator(mode="after")
    def unique_ids(self) -> AssessmentResult:
        for name, values in (
            ("misconception_ids", self.misconception_ids),
            ("missing_concept_ids", self.missing_concept_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must contain unique IDs")
        return self


class EventType(StrEnum):
    ASSESSMENT = "assessment"
    SELF_REPORTED_MASTERY = "self_reported_mastery"
    SIDE_QUESTION = "side_question"
    REQUEST_HINT = "request_hint"
    REQUEST_ANSWER = "request_answer"
    INVALID_ASSESSMENT = "invalid_assessment"


class TutorEvent(StrictModel):
    type: EventType
    assessment: AssessmentResult | None = None

    @model_validator(mode="after")
    def assessment_matches_event(self) -> TutorEvent:
        if (self.type == EventType.ASSESSMENT) != (self.assessment is not None):
            raise ValueError("assessment event and assessment payload must be provided together")
        return self


class SessionMode(StrEnum):
    LEARN = "learn"


class EntryMode(StrEnum):
    NORMAL = "normal"
    DIAGNOSTIC = "diagnostic"
    REVIEW = "review"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class TeacherDirective(StrictModel):
    learning_goal: str = Field(min_length=1, max_length=600)
    interaction_type: str = Field(min_length=1, max_length=80)
    must_ask_one_question: bool
    must_not_reveal_full_answer: bool
    preferred_method: str | None = Field(default=None, max_length=600)
    question_id: str | None = Field(default=None, max_length=120)
    max_length_chars: int = Field(default=500, ge=1, le=2000)


class NodeStateSnapshot(StrictModel):
    node_id: str
    learner_status: LearnerStatus
    progress_status: ProgressStatus
    access_status: AccessStatus
    mastery_score: float = Field(ge=0, le=1)
    confidence_score: float = Field(ge=0, le=1)
    evidence_weight: float = Field(ge=0)
    attempts: int = Field(ge=0)


class NodeStateChange(StrictModel):
    before: NodeStateSnapshot
    after: NodeStateSnapshot


class StateDelta(StrictModel):
    node_changes: dict[str, NodeStateChange] = Field(default_factory=dict)
    evidence_id: str | None = None
    activated_misconception_ids: list[str] = Field(default_factory=list)
    resolved_misconception_ids: list[str] = Field(default_factory=list)
    diagnostic_probe_consumed: bool = False
    session_changes: dict[str, Any] = Field(default_factory=dict)


class CandidateAction(StrictModel):
    action: Action
    target_node_id: str
    reason_codes: list[ReasonCode]
    rank: list[int] = Field(default_factory=list)


class Decision(StrictModel):
    action: Action
    target_node_id: str
    reason_codes: list[ReasonCode]
    teacher_directive: TeacherDirective
    state_delta: StateDelta
    next_expected_question_id: str | None
    return_stack: list[str]


class LearningSessionView(StrictModel):
    session_id: str
    learner_id: str
    mode: SessionMode
    entry_mode: EntryMode
    version: int = Field(ge=1)
    target_node_id: str
    current_node_id: str
    expected_question_id: str | None
    return_stack: list[str]
    status: SessionStatus
    last_action: Action | None
    current_assistance_level: Literal["none", "light_hint", "strong_hint", "answer_revealed"]
    used_target_diagnostic_probes: list[str]
    current_question_is_diagnostic_probe: bool
    created_at: datetime
    updated_at: datetime


class TutorTurnResult(StrictModel):
    session: LearningSessionView
    decision: Decision


class DecisionTrace(StrictModel):
    trace_id: str
    session_id: str
    session_input: dict[str, Any]
    assessment_summary: dict[str, Any] | None
    state_before: dict[str, NodeStateSnapshot]
    candidate_actions: list[CandidateAction]
    final_action: Action
    target_node_id: str
    reason_codes: list[ReasonCode]
    state_delta: StateDelta
    next_expected_question_id: str | None
    created_at: datetime
