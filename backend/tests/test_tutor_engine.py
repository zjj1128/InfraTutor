from collections.abc import Iterator

import pytest

from backend.app.curriculum.loader import CurriculumCatalog
from backend.app.learner.repository import EvidenceRepository
from backend.app.learner.service import LearnerStateService
from backend.app.tutor.domain import (
    Action,
    EventType,
    ReasonCode,
    TutorEvent,
    TutorTurnResult,
)
from backend.app.tutor.engine import (
    DIAGNOSTIC_PROBE_WEIGHT_MULTIPLIER,
    TutorEngine,
    TutorEngineError,
)
from backend.app.tutor.fixtures import (
    ambiguous_assessment,
    assessment_event,
    correct_assessment,
    dma_is_cpu_memcpy,
    mr_copies_memory_to_hca,
    self_reported_mastery_event,
    side_question_event,
)


@pytest.fixture
def tutor_engine(
    learner_service: LearnerStateService, curriculum_catalog: CurriculumCatalog
) -> Iterator[TutorEngine]:
    learner_service.reset("golden_path")
    yield TutorEngine(
        curriculum_catalog,
        learner_service.session_factory,
        learner_service,
    )


def _start_and_remediate(
    tutor: TutorEngine, catalog: CurriculumCatalog
) -> tuple[str, TutorTurnResult]:
    started = tutor.start_session("memory_registration")
    remediated = tutor.handle_event(
        started.session.session_id,
        assessment_event(mr_copies_memory_to_hca(catalog)),
    )
    return started.session.session_id, remediated


def _complete_dma_and_pinned(
    tutor: TutorEngine, catalog: CurriculumCatalog
) -> tuple[str, TutorTurnResult]:
    session_id, _ = _start_and_remediate(tutor, catalog)
    tutor.handle_event(session_id, assessment_event(correct_assessment(catalog, "dma_q3_explain")))
    tutor.handle_event(session_id, assessment_event(correct_assessment(catalog, "dma_q2_scenario")))
    tutor.handle_event(
        session_id, assessment_event(correct_assessment(catalog, "pin_q1_page_stability"))
    )
    returned = tutor.handle_event(
        session_id, assessment_event(correct_assessment(catalog, "pin_q2_copy_check"))
    )
    return session_id, returned


def test_at_te_001_critical_misconception_prevents_advance(
    tutor_engine: TutorEngine, curriculum_catalog: CurriculumCatalog
) -> None:
    started = tutor_engine.start_session("memory_registration")
    result = tutor_engine.handle_event(
        started.session.session_id,
        assessment_event(mr_copies_memory_to_hca(curriculum_catalog)),
    )

    assert result.decision.action == Action.REMEDIATE
    assert result.decision.action != Action.ADVANCE
    assert ReasonCode.CRITICAL_MISCONCEPTION_DETECTED in result.decision.reason_codes


def test_at_te_002_golden_seed_selects_device_dma(
    tutor_engine: TutorEngine, curriculum_catalog: CurriculumCatalog
) -> None:
    _, result = _start_and_remediate(tutor_engine, curriculum_catalog)

    assert result.decision.target_node_id == "device_dma"
    assert result.session.current_node_id == "device_dma"


def test_at_te_003_return_stack_keeps_target_without_duplicates(
    tutor_engine: TutorEngine, curriculum_catalog: CurriculumCatalog
) -> None:
    session_id, result = _start_and_remediate(tutor_engine, curriculum_catalog)
    assert result.session.target_node_id == "memory_registration"
    assert result.session.return_stack == ["memory_registration"]

    repeated_weakness = tutor_engine.handle_event(
        session_id,
        assessment_event(dma_is_cpu_memcpy(curriculum_catalog)),
    )
    assert repeated_weakness.decision.action == Action.HINT
    assert repeated_weakness.session.return_stack == ["memory_registration"]


def test_at_te_004_dma_and_pinned_completion_returns_to_mr(
    tutor_engine: TutorEngine,
    learner_service: LearnerStateService,
    curriculum_catalog: CurriculumCatalog,
) -> None:
    _, returned = _complete_dma_and_pinned(tutor_engine, curriculum_catalog)

    assert returned.decision.action == Action.ASSESS
    assert ReasonCode.RETURN_TO_TARGET in returned.decision.reason_codes
    assert returned.session.current_node_id == "memory_registration"
    assert returned.session.return_stack == []
    assert returned.session.expected_question_id == "mr_q2_explain"
    assert (
        learner_service.get_learner().node_states["memory_registration"].progress_status
        != "mastered"
    )


def test_at_te_005_correct_but_insufficient_evidence_continues_assessment(
    tutor_engine: TutorEngine, curriculum_catalog: CurriculumCatalog
) -> None:
    session_id, _ = _complete_dma_and_pinned(tutor_engine, curriculum_catalog)
    result = tutor_engine.handle_event(
        session_id,
        assessment_event(correct_assessment(curriculum_catalog, "mr_q2_explain")),
    )

    assert result.decision.action == Action.ASSESS
    assert result.session.expected_question_id == "mr_q3_transfer"
    assert ReasonCode.EVIDENCE_INSUFFICIENT in result.decision.reason_codes


def test_at_te_006_self_reported_mastery_does_not_change_state(
    tutor_engine: TutorEngine, learner_service: LearnerStateService
) -> None:
    started = tutor_engine.start_session("memory_registration")
    before = learner_service.get_learner().node_states["memory_registration"]
    result = tutor_engine.handle_event(started.session.session_id, self_reported_mastery_event())
    after = learner_service.get_learner().node_states["memory_registration"]

    assert result.decision.action == Action.ASSESS
    assert ReasonCode.SELF_REPORTED_MASTERY_IGNORED in result.decision.reason_codes
    assert after == before


def test_at_te_007_side_question_preserves_expected_question_and_mainline(
    tutor_engine: TutorEngine, curriculum_catalog: CurriculumCatalog
) -> None:
    started = tutor_engine.start_session("memory_registration")
    side = tutor_engine.handle_event(started.session.session_id, side_question_event())

    assert side.decision.action == Action.ANSWER_SIDE_QUESTION
    assert side.session.expected_question_id == "mr_q1_copy_check"
    resumed = tutor_engine.handle_event(
        started.session.session_id,
        assessment_event(mr_copies_memory_to_hca(curriculum_catalog)),
    )
    assert resumed.session.current_node_id == "device_dma"


def test_golden_path_data_path_does_not_block_return_or_unlock(
    tutor_engine: TutorEngine,
    learner_service: LearnerStateService,
    curriculum_catalog: CurriculumCatalog,
) -> None:
    initial = learner_service.get_learner().node_states["rdma_data_path"]
    assert initial.progress_status == "mastered"

    _, returned = _complete_dma_and_pinned(tutor_engine, curriculum_catalog)
    assert returned.session.current_node_id == "memory_registration"


def test_target_diagnostic_probe_is_used_once_and_has_reduced_weight(
    tutor_engine: TutorEngine,
    learner_service: LearnerStateService,
    curriculum_catalog: CurriculumCatalog,
) -> None:
    session_id, _ = _complete_dma_and_pinned(tutor_engine, curriculum_catalog)
    session = tutor_engine.get_session(session_id)
    traces = tutor_engine.list_decision_traces(session_id)
    evidence_id = traces[1].state_delta.evidence_id
    assert evidence_id is not None
    with learner_service.session_factory() as db:
        evidence = EvidenceRepository(db).get(evidence_id)
        assert evidence is not None
        assert evidence.weight == pytest.approx(0.75 * DIAGNOSTIC_PROBE_WEIGHT_MULTIPLIER)

    assert session.used_target_diagnostic_probes == ["memory_registration"]
    assert session.expected_question_id == "mr_q2_explain"
    assert sum(ReasonCode.TARGET_DIAGNOSTIC_PROBE in trace.reason_codes for trace in traces) == 1


def test_correct_target_probe_does_not_unlock_or_master_locked_target(
    tutor_engine: TutorEngine,
    learner_service: LearnerStateService,
    curriculum_catalog: CurriculumCatalog,
) -> None:
    started = tutor_engine.start_session("memory_registration")
    result = tutor_engine.handle_event(
        started.session.session_id,
        assessment_event(correct_assessment(curriculum_catalog, "mr_q1_copy_check")),
    )
    state = learner_service.get_learner().node_states["memory_registration"]

    assert result.decision.action == Action.REMEDIATE
    assert state.access_status == "locked"
    assert state.status == "locked"
    assert state.progress_status != "mastered"


def test_invalid_or_ambiguous_assessment_does_not_write_evidence(
    tutor_engine: TutorEngine,
    learner_service: LearnerStateService,
    curriculum_catalog: CurriculumCatalog,
) -> None:
    started = tutor_engine.start_session("memory_registration")
    before = learner_service.get_learner().node_states["memory_registration"]

    wrong_question = correct_assessment(curriculum_catalog, "mr_q2_explain")
    invalid = tutor_engine.handle_event(
        started.session.session_id, assessment_event(wrong_question)
    )
    assert invalid.decision.reason_codes == [ReasonCode.INVALID_ASSESSMENT]

    ambiguous = tutor_engine.handle_event(
        started.session.session_id,
        assessment_event(ambiguous_assessment(curriculum_catalog, "mr_q1_copy_check")),
    )
    after = learner_service.get_learner().node_states["memory_registration"]
    assert ambiguous.decision.reason_codes == [ReasonCode.ANSWER_AMBIGUOUS]
    assert after == before


def test_session_and_decision_trace_survive_repository_reload(
    tutor_engine: TutorEngine,
    learner_service: LearnerStateService,
    curriculum_catalog: CurriculumCatalog,
) -> None:
    session_id, result = _start_and_remediate(tutor_engine, curriculum_catalog)
    reloaded_engine = TutorEngine(
        curriculum_catalog,
        learner_service.session_factory,
        learner_service,
    )

    reloaded = reloaded_engine.get_session(session_id)
    traces = reloaded_engine.list_decision_traces(session_id)
    assert reloaded.current_node_id == result.session.current_node_id
    assert reloaded.return_stack == ["memory_registration"]
    assert reloaded.expected_question_id == "dma_q3_explain"
    assert [item.final_action for item in traces] == [Action.ASSESS, Action.REMEDIATE]


def test_learner_reset_cascades_sessions_and_traces(
    tutor_engine: TutorEngine,
    learner_service: LearnerStateService,
) -> None:
    started = tutor_engine.start_session("memory_registration")
    learner_service.reset("clean")

    with pytest.raises(TutorEngineError, match="未知 LearningSession"):
        tutor_engine.get_session(started.session.session_id)


def test_full_golden_path_mastery_unlocks_lkey_rkey(
    tutor_engine: TutorEngine,
    learner_service: LearnerStateService,
    curriculum_catalog: CurriculumCatalog,
) -> None:
    session_id, _ = _complete_dma_and_pinned(tutor_engine, curriculum_catalog)
    tutor_engine.handle_event(
        session_id,
        assessment_event(correct_assessment(curriculum_catalog, "mr_q2_explain")),
    )
    final = tutor_engine.handle_event(
        session_id,
        assessment_event(correct_assessment(curriculum_catalog, "mr_q3_transfer")),
    )
    states = learner_service.get_learner().node_states

    assert final.decision.action == Action.ADVANCE
    assert states["memory_registration"].progress_status == "mastered"
    assert states["lkey_rkey_concept"].status == "ready"


def test_event_contract_rejects_assessment_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="provided together"):
        TutorEvent(type=EventType.ASSESSMENT)
