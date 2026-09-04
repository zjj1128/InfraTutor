from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.curriculum.models import EvidenceType
from backend.app.learner.schemas import AssistanceLevel
from backend.app.tutor.domain import (
    Action,
    AssessmentResult,
    Decision,
    RubricResult,
    TeacherDirective,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class LearnerTurnKind(StrEnum):
    ANSWER = "ANSWER"
    SIDE_QUESTION = "SIDE_QUESTION"
    REQUEST_HINT = "REQUEST_HINT"
    REQUEST_ANSWER = "REQUEST_ANSWER"
    SELF_REPORTED_MASTERY = "SELF_REPORTED_MASTERY"


class LearnerTurn(StrictModel):
    kind: LearnerTurnKind
    text: str = Field(min_length=1, max_length=8000)
    client_turn_id: str = Field(min_length=1, max_length=120)
    submitted_at: datetime


class QuestionType(StrEnum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    FREE_TEXT = "free_text"


class RubricCriterionRequest(StrictModel):
    criterion_id: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=600)
    weight: float = Field(gt=0, le=100)
    required_for_mastery: bool


class AssessmentQuestionRequest(StrictModel):
    question_id: str = Field(min_length=1, max_length=120)
    node_id: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=4000)
    question_type: QuestionType
    evidence_type: EvidenceType
    rubric_criteria: list[RubricCriterionRequest] = Field(min_length=1, max_length=64)
    critical_misconception_ids: list[str] = Field(max_length=16)


class RepairContext(StrictModel):
    previous_output: dict[str, Any] | str
    validation_errors: list[str] = Field(min_length=1, max_length=32)
    output_schema: dict[str, Any]
    allowed_ids: dict[str, list[str]]


class AssessmentRequest(StrictModel):
    question: AssessmentQuestionRequest
    learner_answer: str = Field(min_length=1, max_length=8000)
    allowed_misconception_ids: list[str] = Field(max_length=16)
    allowed_missing_concept_ids: list[str] = Field(min_length=1, max_length=128)
    assistance_level: AssistanceLevel
    language: str = Field(min_length=2, max_length=20)
    repair_context: RepairContext | None = None


class NodeReference(StrictModel):
    node_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)


class CurrentNodeContext(NodeReference):
    learning_objectives: list[str] = Field(min_length=1, max_length=16)
    canonical_facts: list[str] = Field(min_length=1, max_length=24)
    content_boundaries: list[str] = Field(max_length=24)


class TeacherLearnerContext(StrictModel):
    known_correct_points: list[str] = Field(max_length=64)
    missing_points: list[str] = Field(max_length=64)
    active_misconception_ids: list[str] = Field(max_length=16)
    teaching_preferences: list[str] = Field(max_length=16)


class AssessmentQuestionToAsk(StrictModel):
    question_id: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=4000)
    question_type: QuestionType


class TutorMessageRequest(StrictModel):
    action: Action
    course_target_node: NodeReference
    current_node: CurrentNodeContext
    learner_context: TeacherLearnerContext
    directive: TeacherDirective
    question_to_ask: AssessmentQuestionToAsk | None
    language: str = Field(min_length=2, max_length=20)
    repair_context: RepairContext | None = None


class TutorInteractionType(StrEnum):
    ORIENTATION = "orientation"
    EXPLANATION = "explanation"
    GUIDED_QUESTION = "guided_question"
    FORMAL_ASSESSMENT = "formal_assessment"
    HINT = "hint"
    FEEDBACK = "feedback"
    REMEDIATION = "remediation"
    REVIEW = "review"
    TRANSITION = "transition"
    SIDE_ANSWER = "side_answer"
    RECOVERABLE_ERROR = "recoverable_error"


class ExpectedResponseType(StrEnum):
    NONE = "none"
    FREE_TEXT = "free_text"
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"


class TutorMessageResult(StrictModel):
    student_message: str = Field(min_length=1, max_length=2000)
    interaction_type: TutorInteractionType
    expected_response_type: ExpectedResponseType
    question_id: Annotated[str, Field(min_length=1, max_length=120)] | None
    quick_replies: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(max_length=6)


class LLMOperation(StrEnum):
    ASSESSOR = "assessor"
    TEACHER = "teacher"


class LLMMode(StrEnum):
    MOCK = "mock"
    LIVE = "live"


class LLMErrorCode(StrEnum):
    NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
    TIMEOUT = "LLM_TIMEOUT"
    RATE_LIMITED = "LLM_RATE_LIMITED"
    AUTH_FAILED = "LLM_AUTH_FAILED"
    PROVIDER_UNAVAILABLE = "LLM_PROVIDER_UNAVAILABLE"
    REFUSED = "LLM_REFUSED"
    INCOMPLETE_OUTPUT = "LLM_INCOMPLETE_OUTPUT"
    SCHEMA_VALIDATION_FAILED = "LLM_SCHEMA_VALIDATION_FAILED"
    SEMANTIC_VALIDATION_FAILED = "LLM_SEMANTIC_VALIDATION_FAILED"
    INCOMPATIBLE_ENDPOINT = "LLM_INCOMPATIBLE_ENDPOINT"


class LLMError(StrictModel):
    code: LLMErrorCode
    message: str = Field(min_length=1, max_length=500)
    recoverable: bool = True
    validation_errors: list[str] = Field(default_factory=list, max_length=32)


class LLMCallMetadata(StrictModel):
    call_id: str = Field(min_length=1, max_length=80)
    operation: LLMOperation
    mode: LLMMode
    provider: str = Field(min_length=1, max_length=80)
    model: str | None = Field(default=None, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=80)
    prompt_hash: str = Field(min_length=64, max_length=64)
    attempt_count: int = Field(ge=1, le=20)
    latency_ms: int = Field(ge=0)
    provider_request_id: str | None = Field(default=None, max_length=200)
    success: bool
    error_code: LLMErrorCode | None
    input_hash: str = Field(min_length=64, max_length=64)
    output_hash: str | None = Field(default=None, min_length=64, max_length=64)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    created_at: datetime


class LLMStatus(StrictModel):
    mode: LLMMode
    provider: str
    assessor_model_configured: bool
    teacher_model_configured: bool
    api_key_configured: bool
    live_ready: bool
    last_error_code: LLMErrorCode | None = None


class TutorTurnResult(StrictModel):
    learner_turn: LearnerTurn
    raw_assessment: AssessmentResult | None
    validated_assessment: AssessmentResult | None
    assessment_warnings: list[str]
    decision: Decision
    tutor_message: TutorMessageResult
    learner_state_summary: dict[str, Any]
    recoverable_error: LLMError | None
    llm_metadata: list[LLMCallMetadata]
    decision_trace_id: str


__all__ = [
    "AssessmentRequest",
    "AssessmentResult",
    "LLMCallMetadata",
    "LLMError",
    "LearnerTurn",
    "RubricResult",
    "TutorMessageRequest",
    "TutorMessageResult",
]
