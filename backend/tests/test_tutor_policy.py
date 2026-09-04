import pytest

from backend.app.tutor.domain import Action, EventType, ReasonCode, Understanding
from backend.app.tutor.policy import PolicyContext, TutorPolicy


@pytest.mark.parametrize(
    ("context", "expected_action", "expected_reason"),
    [
        (
            PolicyContext(
                event_type=EventType.ASSESSMENT,
                current_node_id="device_dma",
                score=0.2,
            ),
            Action.HINT,
            ReasonCode.CURRENT_ANSWER_INCORRECT,
        ),
        (
            PolicyContext(
                event_type=EventType.ASSESSMENT,
                current_node_id="device_dma",
                score=0.7,
                understanding=Understanding.PARTIAL,
            ),
            Action.HINT,
            ReasonCode.PARTIAL_UNDERSTANDING,
        ),
        (
            PolicyContext(
                event_type=EventType.ASSESSMENT,
                current_node_id="device_dma",
                score=1.0,
                understanding=Understanding.CORRECT,
                next_question_id="dma_q2_scenario",
            ),
            Action.ASSESS,
            ReasonCode.EVIDENCE_INSUFFICIENT,
        ),
    ],
)
def test_policy_p4_to_p6_are_deterministic(
    context: PolicyContext,
    expected_action: Action,
    expected_reason: ReasonCode,
) -> None:
    result = TutorPolicy().decide(context)

    assert result.action == expected_action
    assert expected_reason in result.reason_codes


def test_policy_p0_invalid_assessment_outranks_critical_misconception() -> None:
    result = TutorPolicy().decide(
        PolicyContext(
            event_type=EventType.ASSESSMENT,
            current_node_id="memory_registration",
            assessment_valid=False,
            critical_misconception_detected=True,
            remediation_target_node_id="device_dma",
        )
    )

    assert result.action == Action.RETRY
    assert result.reason_codes == [ReasonCode.INVALID_ASSESSMENT]
