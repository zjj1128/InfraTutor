from collections.abc import Iterable

import pytest

from backend.app.learner.mastery import (
    calculate_confidence,
    effective_evidence_weight,
    update_mastery,
)
from backend.app.learner.models import ImmutableEvidenceError
from backend.app.learner.repository import EvidenceRepository, LearnerRepository
from backend.app.learner.schemas import EvidenceInput, RubricResultInput
from backend.app.learner.service import DEFAULT_LEARNER_ID, LearnerStateService


def _evidence(
    service: LearnerStateService,
    question_id: str,
    *,
    score: float = 1.0,
    assistance: str = "none",
    result: str = "met",
    misconception_ids: Iterable[str] = (),
    met_only: Iterable[str] | None = None,
) -> EvidenceInput:
    assessment = service.assessments[question_id]
    met_ids = set(met_only) if met_only is not None else None
    rubric_results = [
        RubricResultInput(
            criterion_id=criterion.id,
            result=result if met_ids is None else ("met" if criterion.id in met_ids else "not_met"),
        )
        for criterion in assessment.rubric.criteria
    ]
    return EvidenceInput(
        node_id=assessment.node_id,
        question_id=question_id,
        evidence_type=assessment.evidence_type,
        score=score,
        assistance_level=assistance,  # type: ignore[arg-type]
        rubric_results=rubric_results,
        misconception_ids=list(misconception_ids),
    )


def _set_progress(service: LearnerStateService, node_ids: Iterable[str], status: str) -> None:
    with service.session_factory.begin() as session:
        repository = LearnerRepository(session)
        for node_id in node_ids:
            state = repository.get_node_state(DEFAULT_LEARNER_ID, node_id)
            assert state is not None
            state.progress_status = status
            state.status = status
            state.ever_mastered = status == "mastered"


def test_at_ls_001_reading_without_evidence_does_not_change_mastery(
    learner_service: LearnerStateService,
) -> None:
    before = learner_service.get_learner().node_states["virtual_vs_physical_memory"]

    # Phase 2 has no Tutor Engine; a content read/recalculation is the TEACH-equivalent no-op.
    after = learner_service.get_learner().node_states["virtual_vs_physical_memory"]

    assert after.mastery_score == before.mastery_score == 0
    assert after.confidence_score == before.confidence_score == 0
    assert after.evidence_ids == before.evidence_ids == []


def test_at_ls_002_one_correct_recognition_is_not_mastered(
    learner_service: LearnerStateService,
) -> None:
    evidence = learner_service.record_evidence(_evidence(learner_service, "vm_q1_pointer_kind"))
    state = learner_service.get_learner().node_states["virtual_vs_physical_memory"]

    assert evidence.weight == pytest.approx(0.4)
    assert state.mastery_score == pytest.approx(1.0)
    assert state.confidence_score == calculate_confidence(0.4, False)
    assert state.status == "partial"


def test_at_ls_003_strong_hint_has_lower_contribution() -> None:
    no_hint_weight = effective_evidence_weight("recognition", "none")
    strong_hint_weight = effective_evidence_weight("recognition", "strong_hint")

    no_hint_mastery = update_mastery(0.2, 1.0, 1.0, no_hint_weight)
    strong_hint_mastery = update_mastery(0.2, 1.0, 1.0, strong_hint_weight)

    assert strong_hint_weight == pytest.approx(no_hint_weight * 0.45)
    assert strong_hint_mastery < no_hint_mastery
    assert calculate_confidence(1 + strong_hint_weight, False) < calculate_confidence(
        1 + no_hint_weight, False
    )


def test_at_ls_004_mastered_requires_multiple_unassisted_evidence_types(
    learner_service: LearnerStateService,
) -> None:
    learner_service.record_evidence(_evidence(learner_service, "hca_q1_role_path"))
    one_evidence = learner_service.get_learner().node_states["hca_role"]
    assert one_evidence.status == "partial"

    learner_service.record_evidence(_evidence(learner_service, "hca_q2_buffer_location"))
    mastered = learner_service.get_learner().node_states["hca_role"]
    assert mastered.mastery_score >= 0.8
    assert mastered.confidence_score >= 0.65
    assert len(mastered.evidence_ids) == 2
    assert mastered.status == "mastered"

    learner_service.reset("clean")
    learner_service.record_evidence(
        _evidence(
            learner_service,
            "hca_q1_role_path",
            misconception_ids=["hca_stores_registered_buffer"],
        )
    )
    learner_service.record_evidence(_evidence(learner_service, "hca_q2_buffer_location"))
    learner_service.record_evidence(_evidence(learner_service, "hca_q1_role_path"))
    blocked = learner_service.get_learner().node_states["hca_role"]
    assert blocked.mastery_score >= 0.8
    assert blocked.confidence_score >= 0.65
    assert blocked.status != "mastered"


def test_at_ls_005_unassisted_failure_after_mastery_requires_review(
    learner_service: LearnerStateService,
) -> None:
    learner_service.record_evidence(_evidence(learner_service, "hca_q1_role_path"))
    learner_service.record_evidence(_evidence(learner_service, "hca_q2_buffer_location"))
    assert learner_service.get_learner().node_states["hca_role"].status == "mastered"

    learner_service.record_evidence(
        _evidence(learner_service, "hca_q1_role_path", score=0.4, result="not_met")
    )
    assert learner_service.get_learner().node_states["hca_role"].status == "review_needed"


def test_at_ls_006_denial_without_correct_replacement_does_not_resolve(
    learner_service: LearnerStateService,
) -> None:
    detected = learner_service.record_evidence(
        _evidence(
            learner_service,
            "mr_q1_copy_check",
            score=0.1,
            result="not_met",
            misconception_ids=["mr_copies_memory_to_hca"],
        )
    )
    assert not learner_service.try_resolve_misconception("mr_copies_memory_to_hca", detected.id)

    denial_only = learner_service.record_evidence(
        _evidence(
            learner_service,
            "mr_q1_copy_check",
            score=0.4,
            met_only=["mr_q1_not_copy"],
        )
    )
    assert not learner_service.try_resolve_misconception("mr_copies_memory_to_hca", denial_only.id)

    replacement = learner_service.record_evidence(_evidence(learner_service, "mr_q2_explain"))
    assert learner_service.try_resolve_misconception("mr_copies_memory_to_hca", replacement.id)
    misconception = learner_service.get_learner().misconceptions[0]
    assert misconception.status == "resolved"


@pytest.mark.parametrize("weak_node_id", ["device_dma", "pinned_memory"])
def test_at_cg_004_memory_registration_is_locked_by_full_prerequisite_closure(
    learner_service: LearnerStateService, weak_node_id: str
) -> None:
    prerequisite_ids = {
        item.id for item in learner_service.graph.prerequisite_closure("memory_registration")
    }
    _set_progress(learner_service, prerequisite_ids, "mastered")
    _set_progress(learner_service, [weak_node_id], "partial")

    assert learner_service.status_map()["memory_registration"] == "locked"


def test_at_cg_005_lkey_rkey_ready_only_after_memory_registration_mastered(
    learner_service: LearnerStateService,
) -> None:
    prerequisite_ids = {
        item.id for item in learner_service.graph.prerequisite_closure("lkey_rkey_concept")
    }
    _set_progress(learner_service, prerequisite_ids, "mastered")
    assert learner_service.status_map()["lkey_rkey_concept"] == "ready"

    _set_progress(learner_service, ["memory_registration"], "partial")
    assert learner_service.status_map()["lkey_rkey_concept"] == "locked"


def test_evidence_repository_is_append_only(learner_service: LearnerStateService) -> None:
    evidence = learner_service.record_evidence(_evidence(learner_service, "vm_q1_pointer_kind"))

    with pytest.raises(ImmutableEvidenceError, match="不可变"):
        with learner_service.session_factory.begin() as session:
            stored = EvidenceRepository(session).get(evidence.id)
            assert stored is not None
            stored.score = 0.0
