from __future__ import annotations

from backend.app.curriculum.graph import CourseGraph
from backend.app.curriculum.loader import CurriculumCatalog
from backend.app.curriculum.models import Assessment
from backend.app.learner.schemas import LearnerView
from backend.app.llm.contracts import (
    AssessmentQuestionRequest,
    AssessmentQuestionToAsk,
    AssessmentRequest,
    CurrentNodeContext,
    NodeReference,
    QuestionType,
    RubricCriterionRequest,
    TeacherLearnerContext,
    TutorMessageRequest,
)
from backend.app.tutor.domain import AssessmentResult, Decision, LearningSessionView


class RequestBuildError(ValueError):
    pass


class AssessmentRequestBuilder:
    def __init__(self, catalog: CurriculumCatalog) -> None:
        self.catalog = catalog
        self.graph = CourseGraph(catalog)
        self.assessments = {item.id: item for item in catalog.assessment_set.assessments}
        self.misconceptions = {item.id: item for item in catalog.pilot.misconceptions}

    def build(
        self,
        session: LearningSessionView,
        learner_answer: str,
        *,
        language: str | None = None,
    ) -> AssessmentRequest:
        if session.expected_question_id is None:
            raise RequestBuildError("Session 当前没有 expected question")
        assessment = self.assessments.get(session.expected_question_id)
        if assessment is None:
            raise RequestBuildError(f"未知 expected question: {session.expected_question_id}")
        if assessment.node_id != session.current_node_id:
            raise RequestBuildError("expected question 不属于 Session current node")

        allowed_misconceptions = list(assessment.rubric.critical_misconception_ids)
        related_ids = {
            session.current_node_id,
            session.target_node_id,
            *(item.id for item in self.graph.prerequisite_closure(session.current_node_id)),
            *(item.id for item in self.graph.prerequisite_closure(session.target_node_id)),
        }
        for misconception_id in allowed_misconceptions:
            definition = self.misconceptions.get(misconception_id)
            if definition is not None:
                related_ids.update(definition.remediation_nodes)
        related_ids &= set(self.graph.node_ids)

        return AssessmentRequest(
            question=AssessmentQuestionRequest(
                question_id=assessment.id,
                node_id=assessment.node_id,
                prompt=assessment.prompt,
                question_type=QuestionType(assessment.question_type),
                evidence_type=assessment.evidence_type,
                rubric_criteria=[
                    RubricCriterionRequest(
                        criterion_id=item.id,
                        description=item.description,
                        weight=item.weight,
                        required_for_mastery=item.required_for_mastery,
                    )
                    for item in assessment.rubric.criteria
                ],
                critical_misconception_ids=allowed_misconceptions,
            ),
            learner_answer=learner_answer,
            allowed_misconception_ids=allowed_misconceptions,
            allowed_missing_concept_ids=sorted(related_ids),
            assistance_level=session.current_assistance_level,
            language=language or self.catalog.assessment_set.language,
        )


class TeacherRequestBuilder:
    def __init__(self, catalog: CurriculumCatalog) -> None:
        self.catalog = catalog
        self.nodes = {item.id: item for item in catalog.pilot.nodes}
        self.assessments: dict[str, Assessment] = {
            item.id: item for item in catalog.assessment_set.assessments
        }

    def build(
        self,
        *,
        session: LearningSessionView,
        decision: Decision,
        learner: LearnerView,
        assessment: AssessmentResult | None,
        language: str | None = None,
    ) -> TutorMessageRequest:
        current = self.nodes.get(session.current_node_id)
        target = self.nodes.get(session.target_node_id)
        if current is None or target is None:
            raise RequestBuildError("Teacher request 只能使用 pilot course node")

        known: list[str] = []
        missing: list[str] = []
        if assessment is not None:
            rubric = self.assessments[assessment.question_id].rubric
            descriptions = {item.id: item.description for item in rubric.criteria}
            for result in assessment.rubric_results:
                if result.result == "met":
                    known.append(descriptions[result.criterion_id])
                else:
                    missing.append(descriptions[result.criterion_id])

        question = self._question(decision.next_expected_question_id)
        active_ids = [
            item.misconception_id
            for item in learner.misconceptions
            if item.status == "active"
            and item.node_id in {session.current_node_id, session.target_node_id}
        ]
        return TutorMessageRequest(
            action=decision.action,
            course_target_node=NodeReference(node_id=target.id, title=target.title),
            current_node=CurrentNodeContext(
                node_id=current.id,
                title=current.title,
                learning_objectives=current.learning_objectives,
                canonical_facts=current.canonical_facts,
                content_boundaries=current.content_boundaries,
            ),
            learner_context=TeacherLearnerContext(
                known_correct_points=known,
                missing_points=missing,
                active_misconception_ids=active_ids,
                teaching_preferences=learner.profile.teaching_preferences,
            ),
            directive=decision.teacher_directive,
            question_to_ask=question,
            language=language or self.catalog.assessment_set.language,
        )

    def _question(self, question_id: str | None) -> AssessmentQuestionToAsk | None:
        if question_id is None:
            return None
        assessment = self.assessments.get(question_id)
        if assessment is None:
            raise RequestBuildError(f"Decision 引用了未知 question: {question_id}")
        return AssessmentQuestionToAsk(
            question_id=assessment.id,
            prompt=assessment.prompt,
            question_type=QuestionType(assessment.question_type),
        )
