from pathlib import Path

from backend.app.core.config import PROJECT_ROOT
from backend.app.curriculum.loader import load_curriculum
from backend.app.db.session import (
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from backend.app.learner.service import LearnerStateService
from backend.app.tutor.engine import TutorEngine
from backend.app.tutor.fixtures import (
    assessment_event,
    correct_assessment,
    mr_copies_memory_to_hca,
)


def _line(number: int, label: str, value: object) -> None:
    print(f"{number:02d}. {label}: {value}")


def main(curriculum_dir: Path = PROJECT_ROOT / "curriculum") -> int:
    catalog = load_curriculum(curriculum_dir)
    database = create_database_engine("sqlite://")
    initialize_database(database)
    session_factory = create_session_factory(database)
    learner = LearnerStateService(catalog, session_factory)
    learner.ensure_default_learner()
    learner.reset("golden_path")
    tutor = TutorEngine(catalog, session_factory, learner)

    started = tutor.start_session("memory_registration")
    _line(1, "target", started.session.target_node_id)
    _line(2, "target diagnostic probe", started.session.expected_question_id)

    remediated = tutor.handle_event(
        started.session.session_id,
        assessment_event(mr_copies_memory_to_hca(catalog)),
    )
    _line(3, "detected", "mr_copies_memory_to_hca")
    _line(4, "remediation", f"{remediated.decision.action} {remediated.session.current_node_id}")
    _line(5, "return_stack", remediated.session.return_stack)

    tutor.handle_event(
        started.session.session_id,
        assessment_event(correct_assessment(catalog, "dma_q3_explain")),
    )
    dma_transfer = tutor.handle_event(
        started.session.session_id,
        assessment_event(correct_assessment(catalog, "dma_q2_scenario")),
    )
    _line(
        6,
        "DMA",
        f"{learner.get_learner().node_states['device_dma'].progress_status}; "
        f"next={dma_transfer.session.current_node_id}",
    )
    _line(7, "next remediation", dma_transfer.session.current_node_id)

    tutor.handle_event(
        started.session.session_id,
        assessment_event(correct_assessment(catalog, "pin_q1_page_stability")),
    )
    returned = tutor.handle_event(
        started.session.session_id,
        assessment_event(correct_assessment(catalog, "pin_q2_copy_check")),
    )
    _line(8, "Pinned Memory", learner.get_learner().node_states["pinned_memory"].progress_status)
    _line(9, "returned current_node", returned.session.current_node_id)

    mr_explain = tutor.handle_event(
        started.session.session_id,
        assessment_event(correct_assessment(catalog, "mr_q2_explain")),
    )
    _line(
        10,
        "MR explanation",
        f"action={mr_explain.decision.action}; progress="
        f"{learner.get_learner().node_states['memory_registration'].progress_status}",
    )
    _line(11, "next assessment", mr_explain.session.expected_question_id)

    tutor.handle_event(
        started.session.session_id,
        assessment_event(correct_assessment(catalog, "mr_q3_transfer")),
    )
    final_state = learner.get_learner().node_states
    _line(12, "MR", final_state["memory_registration"].progress_status)
    _line(13, "lkey_rkey_concept", final_state["lkey_rkey_concept"].status)

    traces = tutor.list_decision_traces(started.session.session_id)
    _line(14, "Decision Trace count", len(traces))
    for index, trace in enumerate(traces, start=1):
        changed = ",".join(trace.state_delta.node_changes) or "none"
        reasons = ",".join(item.value for item in trace.reason_codes)
        print(
            f"    trace[{index}] action={trace.final_action.value} "
            f"target={trace.target_node_id} reasons={reasons} "
            f"next={trace.next_expected_question_id} changed={changed}"
        )

    database.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
