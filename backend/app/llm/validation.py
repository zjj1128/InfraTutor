from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from backend.app.curriculum.graph import CourseGraph
from backend.app.curriculum.loader import CurriculumCatalog
from backend.app.llm.contracts import (
    AssessmentRequest,
    AssessmentResult,
    ExpectedResponseType,
    TutorInteractionType,
    TutorMessageRequest,
    TutorMessageResult,
)
from backend.app.llm.errors import SemanticValidationError
from backend.app.tutor.domain import Action, Understanding

SCORE_WARNING_THRESHOLD = 0.15


@dataclass(frozen=True)
class CanonicalAssessment:
    raw: AssessmentResult
    result: AssessmentResult
    warnings: list[str]


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


class AssessmentSemanticValidator:
    def __init__(self, catalog: CurriculumCatalog) -> None:
        self.catalog = catalog
        self.graph = CourseGraph(catalog)
        self.assessments = {item.id: item for item in catalog.assessment_set.assessments}
        self.misconceptions = {item.id: item for item in catalog.pilot.misconceptions}

    def validate_and_canonicalize(
        self, request: AssessmentRequest, result: AssessmentResult
    ) -> CanonicalAssessment:
        errors: list[str] = []
        course_assessment = self.assessments.get(request.question.question_id)
        if course_assessment is None:
            errors.append(f"unknown curriculum question: {request.question.question_id}")
        elif course_assessment.node_id != request.question.node_id:
            errors.append("request question node does not match curriculum ownership")
        if result.question_id != request.question.question_id:
            errors.append(
                f"question_id mismatch: expected {request.question.question_id}, "
                f"received {result.question_id}"
            )
        if result.node_id != request.question.node_id:
            errors.append(
                f"node_id mismatch: expected {request.question.node_id}, received {result.node_id}"
            )

        expected = [item.criterion_id for item in request.question.rubric_criteria]
        if course_assessment is not None:
            course_criteria = [item.id for item in course_assessment.rubric.criteria]
            if expected != course_criteria:
                errors.append("request rubric does not match curriculum rubric")
        received = [item.criterion_id for item in result.rubric_results]
        duplicates = sorted({item for item in received if received.count(item) > 1})
        missing = sorted(set(expected) - set(received))
        extra = sorted(set(received) - set(expected))
        if duplicates:
            errors.append(f"duplicate criterion IDs: {duplicates}")
        if missing:
            errors.append(f"missing criterion IDs: {missing}")
        if extra:
            errors.append(f"unknown criterion IDs: {extra}")
        if len(received) != len(expected) and not (duplicates or missing or extra):
            errors.append("rubric_results 必须恰好覆盖全部 criterion")

        invalid_misconceptions = sorted(
            set(result.misconception_ids) - set(request.allowed_misconception_ids)
        )
        unknown_misconceptions = sorted(set(result.misconception_ids) - set(self.misconceptions))
        if unknown_misconceptions:
            errors.append(f"unknown curriculum misconception IDs: {unknown_misconceptions}")
        if invalid_misconceptions:
            errors.append(f"unknown or disallowed misconception IDs: {invalid_misconceptions}")
        invalid_missing = sorted(
            set(result.missing_concept_ids) - set(request.allowed_missing_concept_ids)
        )
        if invalid_missing:
            errors.append(f"missing concept IDs outside related graph: {invalid_missing}")
        unknown_missing = sorted(set(result.missing_concept_ids) - set(self.graph.node_ids))
        if unknown_missing:
            errors.append(f"unknown curriculum missing concept IDs: {unknown_missing}")
        if result.recommended_target_node_id is not None and (
            result.recommended_target_node_id not in request.allowed_missing_concept_ids
        ):
            errors.append("recommended_target_node_id outside allowed related graph")

        normalized_answer = _normalized_text(request.learner_answer)
        for rubric_result in result.rubric_results:
            if rubric_result.evidence_span and (
                _normalized_text(rubric_result.evidence_span) not in normalized_answer
            ):
                errors.append(
                    f"evidence_span for {rubric_result.criterion_id} is not from learner answer"
                )
        if errors:
            raise SemanticValidationError(errors)

        score = self._score(request, result)
        warnings: list[str] = []
        if abs(result.score - score) > SCORE_WARNING_THRESHOLD:
            warnings.append(f"model score {result.score:.3f} replaced by backend score {score:.3f}")
        critical = any(
            self.misconceptions[item].critical
            for item in result.misconception_ids
            if item in self.misconceptions
        )
        if result.answer_is_ambiguous:
            understanding = Understanding.UNCERTAIN
        elif score >= 0.8 and not critical:
            understanding = Understanding.CORRECT
        elif score >= 0.5:
            understanding = Understanding.PARTIAL
        else:
            understanding = Understanding.INCORRECT
        canonical = result.model_copy(
            update={"score": score, "understanding": understanding}, deep=True
        )
        return CanonicalAssessment(raw=result, result=canonical, warnings=warnings)

    def _score(self, request: AssessmentRequest, result: AssessmentResult) -> float:
        values = {"met": 1.0, "uncertain": 0.5, "not_met": 0.0}
        result_by_id = {item.criterion_id: item.result for item in result.rubric_results}
        total = sum(item.weight for item in request.question.rubric_criteria)
        score = sum(
            item.weight * values[result_by_id[item.criterion_id]]
            for item in request.question.rubric_criteria
        )
        return round(score / total, 6)


class TeacherSemanticValidator:
    _INTERACTIONS_BY_ACTION = {
        Action.ORIENT: {TutorInteractionType.ORIENTATION},
        Action.TEACH: {TutorInteractionType.EXPLANATION, TutorInteractionType.FEEDBACK},
        Action.ASK: {TutorInteractionType.GUIDED_QUESTION},
        Action.ASSESS: {TutorInteractionType.FORMAL_ASSESSMENT},
        Action.HINT: {TutorInteractionType.HINT, TutorInteractionType.GUIDED_QUESTION},
        Action.RETRY: {TutorInteractionType.GUIDED_QUESTION, TutorInteractionType.FEEDBACK},
        Action.REMEDIATE: {TutorInteractionType.REMEDIATION, TutorInteractionType.GUIDED_QUESTION},
        Action.REVIEW: {TutorInteractionType.REVIEW},
        Action.ADVANCE: {TutorInteractionType.TRANSITION},
        Action.ANSWER_SIDE_QUESTION: {TutorInteractionType.SIDE_ANSWER},
    }

    def validate(self, request: TutorMessageRequest, result: TutorMessageResult) -> None:
        errors: list[str] = []
        expected_question_id = (
            request.question_to_ask.question_id if request.question_to_ask is not None else None
        )
        if result.question_id != expected_question_id:
            errors.append(
                f"question_id mismatch: expected {expected_question_id}, "
                f"received {result.question_id}"
            )
        if request.question_to_ask is None:
            expected_response = ExpectedResponseType.NONE
        else:
            expected_response = ExpectedResponseType(request.question_to_ask.question_type.value)
        if request.directive.question_id != expected_question_id:
            errors.append("TeacherDirective question_id 与 Decision next question 不一致")
        if result.expected_response_type != expected_response:
            errors.append(
                f"expected_response_type mismatch: expected {expected_response.value}, "
                f"received {result.expected_response_type.value}"
            )
        if result.interaction_type not in self._INTERACTIONS_BY_ACTION[request.action]:
            errors.append(
                f"interaction_type {result.interaction_type.value} "
                f"is invalid for {request.action.value}"
            )
        if len(result.student_message) > request.directive.max_length_chars:
            errors.append("student_message exceeds TeacherDirective.max_length_chars")
        if request.directive.must_ask_one_question and result.question_id is None:
            errors.append("TeacherDirective requires exactly one curriculum question")
        if request.directive.must_not_reveal_full_answer and (
            result.interaction_type == TutorInteractionType.EXPLANATION
        ):
            errors.append("must_not_reveal_full_answer forbids the answer-revealed path")
        if errors:
            raise SemanticValidationError(errors)
