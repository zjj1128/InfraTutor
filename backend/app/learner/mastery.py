from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.app.curriculum.models import Assessment, EvidenceType, MasteryRequirements
from backend.app.learner.models import Evidence
from backend.app.learner.schemas import AssistanceLevel

EVIDENCE_TYPE_WEIGHTS: dict[EvidenceType, float] = {
    "recognition": 0.40,
    "short_answer": 0.75,
    "free_explanation": 1.00,
    "scenario_transfer": 1.25,
    "delayed_review": 1.25,
    "lab": 1.50,
}

ASSISTANCE_MULTIPLIERS: dict[AssistanceLevel, float] = {
    "none": 1.00,
    "light_hint": 0.75,
    "strong_hint": 0.45,
    "answer_revealed": 0.15,
}


def effective_evidence_weight(
    evidence_type: EvidenceType, assistance_level: AssistanceLevel
) -> float:
    return round(EVIDENCE_TYPE_WEIGHTS[evidence_type] * ASSISTANCE_MULTIPLIERS[assistance_level], 6)


def update_mastery(
    old_mastery: float,
    old_weight: float,
    evidence_score: float,
    new_weight: float,
) -> float:
    if old_weight <= 0:
        return round(evidence_score, 6)
    bounded_old_weight = min(old_weight, 3.0)
    return round(
        (old_mastery * bounded_old_weight + evidence_score * new_weight)
        / (bounded_old_weight + new_weight),
        6,
    )


def calculate_confidence(total_effective_weight: float, has_active_critical: bool) -> float:
    confidence = min(1.0, total_effective_weight / 3.0)
    if has_active_critical:
        confidence = max(0.0, confidence - 0.15)
    return round(confidence, 6)


@dataclass(frozen=True)
class MasteryGateResult:
    passed: bool
    independent_evidence_count: int
    has_unassisted_open_answer: bool
    has_unassisted_scenario: bool
    required_rubrics_met: bool


def evaluate_mastery_gate(
    *,
    mastery_score: float,
    confidence_score: float,
    evidence: Sequence[Evidence],
    assessments: Mapping[str, Assessment],
    requirements: MasteryRequirements,
    has_active_critical: bool,
) -> MasteryGateResult:
    independent_count = len({item.question_id for item in evidence})
    unassisted = [item for item in evidence if item.assistance_level == "none"]

    open_answers = [item for item in unassisted if item.evidence_type == "free_explanation"]
    scenarios = [item for item in unassisted if item.evidence_type == "scenario_transfer"]

    qualifying = {item.id: item for item in [*open_answers, *scenarios]}
    required_criteria: set[str] = set()
    met_criteria: set[str] = set()
    for item in qualifying.values():
        assessment = assessments[item.question_id]
        required_criteria.update(
            criterion.id
            for criterion in assessment.rubric.criteria
            if criterion.required_for_mastery
        )
        met_criteria.update(
            result["criterion_id"]
            for result in item.rubric_results_json
            if result["result"] == "met"
        )
    required_rubrics_met = bool(required_criteria) and required_criteria <= met_criteria
    has_open = bool(open_answers)
    has_scenario = bool(scenarios)

    passed = (
        mastery_score >= requirements.minimum_mastery_score
        and confidence_score >= requirements.minimum_confidence_score
        and independent_count >= requirements.minimum_independent_evidence
        and (not requirements.require_unassisted_free_explanation or has_open)
        and (not requirements.require_unassisted_scenario_transfer or has_scenario)
        and (not requirements.block_on_active_critical_misconception or not has_active_critical)
        and required_rubrics_met
    )
    return MasteryGateResult(
        passed=passed,
        independent_evidence_count=independent_count,
        has_unassisted_open_answer=has_open,
        has_unassisted_scenario=has_scenario,
        required_rubrics_met=required_rubrics_met,
    )


def derive_progress_status(
    *,
    mastery_score: float,
    evidence_weight: float,
    ever_mastered: bool,
    current_progress_status: str,
    latest_evidence: Evidence | None,
    gate: MasteryGateResult,
    has_active_critical: bool,
) -> str:
    if (
        ever_mastered
        and latest_evidence is not None
        and latest_evidence.assistance_level == "none"
        and latest_evidence.score < 0.5
    ):
        return "review_needed"
    if has_active_critical:
        return "learning" if mastery_score < 0.55 else "partial"
    if gate.passed:
        return "mastered"
    if current_progress_status == "mastered":
        # Seeded demo mastery is a trusted initialization snapshot, not fabricated Evidence.
        return "mastered"
    if evidence_weight <= 0:
        return "no_evidence"
    if mastery_score < 0.55:
        return "learning"
    return "partial"
