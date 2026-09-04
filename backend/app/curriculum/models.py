from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


NodeType = Literal["concept", "skill", "procedure", "lab", "checkpoint"]
ImplementationStatus = Literal["planned", "supporting", "pilot"]
LearnerStatus = Literal["locked", "ready", "learning", "partial", "mastered", "review_needed"]
ProgressStatus = Literal["no_evidence", "learning", "partial", "mastered", "review_needed"]
AccessStatus = Literal["locked", "available"]
EvidenceType = Literal[
    "recognition",
    "short_answer",
    "free_explanation",
    "scenario_transfer",
    "delayed_review",
    "lab",
]


class AuthoringPolicy(StrictModel):
    knowledge_source: str
    llm_role: str
    v0_1_hard_edge_type: Literal["prerequisite"]


class RoadmapStage(StrictModel):
    id: str = Field(min_length=1)
    order: int = Field(gt=0)
    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    exit_capabilities: list[str]


class RoadmapNode(StrictModel):
    id: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    type: NodeType
    prerequisites: list[str] = Field(default_factory=list)
    recommended_next: list[str] = Field(default_factory=list)
    reinforces: list[str] = Field(default_factory=list)
    implementation_status: ImplementationStatus


class Roadmap(StrictModel):
    schema_version: str
    course_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    target_learner: str = Field(min_length=1)
    authoring_policy: AuthoringPolicy
    stages: list[RoadmapStage]
    nodes: list[RoadmapNode]


class EntryPolicy(StrictModel):
    normal_start_node_id: str
    allow_target_diagnostic_probe: bool
    probe_does_not_bypass_prerequisites: bool
    target_probe_questions: dict[str, str]
    description: str


class SupportingAssumption(StrictModel):
    node_id: str
    policy: str
    reason: str


class ContentPolicy(StrictModel):
    facts_are_human_curated: bool
    llm_may_adapt_explanation: bool
    llm_may_create_new_nodes: bool
    advanced_topics_out_of_scope: list[str]


class MasteryRequirements(StrictModel):
    minimum_mastery_score: float = Field(ge=0, le=1)
    minimum_confidence_score: float = Field(ge=0, le=1)
    minimum_independent_evidence: int = Field(ge=1)
    require_unassisted_free_explanation: bool
    require_unassisted_scenario_transfer: bool
    block_on_active_critical_misconception: bool


class PilotNode(StrictModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    type: NodeType
    prerequisites: list[str]
    learning_objectives: list[str]
    canonical_facts: list[str]
    content_boundaries: list[str]
    common_misconceptions: list[str]
    assessment_ids: list[str]
    teaching_moves: list[str]
    recommended_next: list[str]
    mastery_requirements: MasteryRequirements
    implementation_status: Literal["pilot"]


class MisconceptionDefinition(StrictModel):
    id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    critical: bool
    remediation_nodes: list[str]


class SeedNodeState(StrictModel):
    status: LearnerStatus
    mastery_score: float = Field(ge=0, le=1)
    confidence_score: float = Field(ge=0, le=1)


class SeedDefinition(StrictModel):
    description: str
    target_node_id: str | None = None
    initial_question_id: str | None = None
    node_states: dict[str, SeedNodeState]


class Seeds(StrictModel):
    clean: SeedDefinition
    golden_path: SeedDefinition


class PilotModule(StrictModel):
    schema_version: str
    module_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    stage_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    implementation_status: Literal["pilot"]
    entry_policy: EntryPolicy
    supporting_assumptions: list[SupportingAssumption]
    content_policy: ContentPolicy
    default_mastery_requirements: MasteryRequirements
    nodes: list[PilotNode]
    misconceptions: list[MisconceptionDefinition]
    seeds: Seeds


class ScoringPolicy(StrictModel):
    met_value: float = Field(ge=0, le=1)
    uncertain_value: float = Field(ge=0, le=1)
    not_met_value: float = Field(ge=0, le=1)
    backend_recalculates_score: bool
    model_score_is_advisory: bool


class RubricCriterion(StrictModel):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    weight: float = Field(gt=0)
    required_for_mastery: bool


class Rubric(StrictModel):
    criteria: list[RubricCriterion] = Field(min_length=1)
    critical_misconception_ids: list[str]


class MockFixture(StrictModel):
    contains_any: list[str] | None = None
    contains_all: list[str] | None = None
    assessment: str

    @model_validator(mode="after")
    def has_matching_rule(self) -> "MockFixture":
        if not self.contains_any and not self.contains_all:
            raise ValueError("mock fixture must define contains_any or contains_all")
        return self


class ChoiceOption(StrictModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Assessment(StrictModel):
    id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    question_type: Literal["single_choice", "multiple_choice", "free_text"]
    evidence_type: EvidenceType
    prompt: str = Field(min_length=1)
    rubric: Rubric
    hints: list[str]
    mock_fixtures: list[MockFixture]
    options: list[ChoiceOption] = Field(default_factory=list)
    correct_option_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_choice_shape(self) -> "Assessment":
        if self.question_type in {"single_choice", "multiple_choice"}:
            if len(self.options) < 2:
                raise ValueError("choice assessment must define at least two options")
            if not self.correct_option_ids:
                raise ValueError("choice assessment must define correct_option_ids")
        return self


class AssessmentSet(StrictModel):
    schema_version: str
    assessment_set_id: str = Field(min_length=1)
    language: str
    scoring_policy: ScoringPolicy
    assessments: list[Assessment]
