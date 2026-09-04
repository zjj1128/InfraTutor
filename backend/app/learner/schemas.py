from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.curriculum.models import AccessStatus, EvidenceType, LearnerStatus, ProgressStatus

AssistanceLevel = Literal["none", "light_hint", "strong_hint", "answer_revealed"]
RubricResultValue = Literal["met", "uncertain", "not_met"]
MisconceptionStatus = Literal["suspected", "active", "resolved"]
SeedName = Literal["clean", "golden_path"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RubricResultInput(StrictModel):
    criterion_id: str = Field(min_length=1)
    result: RubricResultValue


class EvidenceInput(StrictModel):
    node_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    evidence_type: EvidenceType
    score: float = Field(ge=0, le=1)
    assistance_level: AssistanceLevel = "none"
    rubric_results: list[RubricResultInput]
    misconception_ids: list[str] = Field(default_factory=list)
    session_id: str | None = None


class LearnerProfileView(StrictModel):
    display_name: str
    target_role: str
    teaching_preferences: list[str]


class LearnerNodeStateView(StrictModel):
    status: LearnerStatus
    progress_status: ProgressStatus
    access_status: AccessStatus
    mastery_score: float = Field(ge=0, le=1)
    confidence_score: float = Field(ge=0, le=1)
    evidence_weight: float = Field(ge=0)
    attempts: int = Field(ge=0)
    evidence_ids: list[str]
    last_seen_at: datetime | None
    last_tested_at: datetime | None
    review_due_at: datetime | None


class LearnerMisconceptionView(StrictModel):
    misconception_id: str
    node_id: str
    status: MisconceptionStatus
    evidence_ids: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None


class LearnerView(StrictModel):
    learner_id: str
    profile: LearnerProfileView
    node_states: dict[str, LearnerNodeStateView]
    misconceptions: list[LearnerMisconceptionView]


class ResetLearnerRequest(StrictModel):
    seed: SeedName
