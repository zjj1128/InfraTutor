from collections.abc import Sequence

from backend.app.curriculum.loader import CurriculumCatalog
from backend.app.curriculum.models import Assessment, PilotNode
from backend.app.learner.models import Evidence, LearnerNodeState


class AssessmentPlanner:
    def __init__(self, catalog: CurriculumCatalog) -> None:
        self.nodes: dict[str, PilotNode] = {item.id: item for item in catalog.pilot.nodes}
        self.assessments: dict[str, Assessment] = {
            item.id: item for item in catalog.assessment_set.assessments
        }

    def next_question(
        self,
        node_id: str,
        state: LearnerNodeState,
        evidence: Sequence[Evidence],
        *,
        excluded_question_ids: set[str] | frozenset[str] = frozenset(),
    ) -> str | None:
        node = self.nodes.get(node_id)
        if node is None:
            return None

        available = [
            self.assessments[item]
            for item in node.assessment_ids
            if item not in excluded_question_ids
        ]
        if not available:
            return None

        if state.progress_status == "no_evidence":
            recognition = self._first_of_type(available, "recognition")
            if recognition is not None:
                return recognition.id

        requirements = node.mastery_requirements
        if requirements.require_unassisted_free_explanation and not self._has_qualifying(
            evidence, "free_explanation"
        ):
            question = self._first_of_type(available, "free_explanation")
            if question is not None:
                return question.id

        if requirements.require_unassisted_scenario_transfer and not self._has_qualifying(
            evidence, "scenario_transfer"
        ):
            question = self._first_of_type(available, "scenario_transfer")
            if question is not None:
                return question.id

        counts = {item.id: 0 for item in available}
        for item in evidence:
            if item.question_id in counts:
                counts[item.question_id] += 1
        return min(
            available,
            key=lambda item: (counts[item.id], node.assessment_ids.index(item.id)),
        ).id

    @staticmethod
    def _first_of_type(assessments: Sequence[Assessment], evidence_type: str) -> Assessment | None:
        return next((item for item in assessments if item.evidence_type == evidence_type), None)

    @staticmethod
    def _has_qualifying(evidence: Sequence[Evidence], evidence_type: str) -> bool:
        return any(
            item.evidence_type == evidence_type
            and item.assistance_level == "none"
            and item.score >= 0.8
            for item in evidence
        )
