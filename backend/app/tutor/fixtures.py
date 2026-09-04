from backend.app.curriculum.loader import CurriculumCatalog
from backend.app.tutor.domain import (
    AssessmentResult,
    EventType,
    RecommendedAction,
    RubricResult,
    TutorEvent,
    Understanding,
)


def correct_assessment(catalog: CurriculumCatalog, question_id: str) -> AssessmentResult:
    assessment = next(item for item in catalog.assessment_set.assessments if item.id == question_id)
    return AssessmentResult(
        question_id=assessment.id,
        node_id=assessment.node_id,
        understanding=Understanding.CORRECT,
        score=1.0,
        rubric_results=[
            RubricResult(
                criterion_id=item.id,
                result="met",
                evidence_span=f"fixture:{item.id}",
            )
            for item in assessment.rubric.criteria
        ],
        misconception_ids=[],
        missing_concept_ids=[],
        answer_is_ambiguous=False,
        feedback_points=["固定 fixture：全部 rubric 已满足"],
        recommended_action=RecommendedAction.ADVANCE_CANDIDATE,
        recommended_target_node_id=None,
    )


def mr_copies_memory_to_hca(catalog: CurriculumCatalog) -> AssessmentResult:
    assessment = next(
        item for item in catalog.assessment_set.assessments if item.id == "mr_q1_copy_check"
    )
    return AssessmentResult(
        question_id=assessment.id,
        node_id=assessment.node_id,
        understanding=Understanding.INCORRECT,
        score=0.0,
        rubric_results=[
            RubricResult(
                criterion_id=item.id,
                result="not_met",
                evidence_span="fixture:错误地认为 buffer 被复制到 HCA",
            )
            for item in assessment.rubric.criteria
        ],
        misconception_ids=["mr_copies_memory_to_hca"],
        missing_concept_ids=["device_dma", "pinned_memory"],
        answer_is_ambiguous=False,
        feedback_points=["混淆了注册元数据与 payload 搬运"],
        recommended_action=RecommendedAction.REMEDIATE,
        recommended_target_node_id="device_dma",
    )


def dma_is_cpu_memcpy(catalog: CurriculumCatalog) -> AssessmentResult:
    assessment = next(
        item for item in catalog.assessment_set.assessments if item.id == "dma_q3_explain"
    )
    return AssessmentResult(
        question_id=assessment.id,
        node_id=assessment.node_id,
        understanding=Understanding.INCORRECT,
        score=0.0,
        rubric_results=[
            RubricResult(
                criterion_id=item.id,
                result="not_met",
                evidence_span="fixture:错误地把 DMA 说成 CPU memcpy",
            )
            for item in assessment.rubric.criteria
        ],
        misconception_ids=["dma_is_cpu_memcpy"],
        missing_concept_ids=["device_dma"],
        answer_is_ambiguous=False,
        feedback_points=["没有区分提交者与 payload 搬运者"],
        recommended_action=RecommendedAction.HINT,
        recommended_target_node_id="device_dma",
    )


def ambiguous_assessment(catalog: CurriculumCatalog, question_id: str) -> AssessmentResult:
    assessment = next(item for item in catalog.assessment_set.assessments if item.id == question_id)
    return AssessmentResult(
        question_id=assessment.id,
        node_id=assessment.node_id,
        understanding=Understanding.UNCERTAIN,
        score=0.5,
        rubric_results=[
            RubricResult(
                criterion_id=item.id,
                result="uncertain",
                evidence_span="",
            )
            for item in assessment.rubric.criteria
        ],
        misconception_ids=[],
        missing_concept_ids=[],
        answer_is_ambiguous=True,
        feedback_points=["固定 fixture：回答信息不足"],
        recommended_action=RecommendedAction.ASK_FOLLOWUP,
        recommended_target_node_id=None,
    )


def self_reported_mastery_event() -> TutorEvent:
    return TutorEvent(type=EventType.SELF_REPORTED_MASTERY)


def side_question_event() -> TutorEvent:
    return TutorEvent(type=EventType.SIDE_QUESTION)


def assessment_event(result: AssessmentResult) -> TutorEvent:
    return TutorEvent(type=EventType.ASSESSMENT, assessment=result)
