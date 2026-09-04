from dataclasses import dataclass, field

from backend.app.tutor.domain import (
    Action,
    CandidateAction,
    EventType,
    ReasonCode,
    Understanding,
)


@dataclass(frozen=True)
class PolicyContext:
    event_type: EventType
    current_node_id: str
    assessment_valid: bool = True
    ambiguous: bool = False
    understanding: Understanding | None = None
    score: float | None = None
    critical_misconception_detected: bool = False
    remediation_target_node_id: str | None = None
    current_mastered: bool = False
    next_question_id: str | None = None
    completion_action: Action | None = None
    completion_target_node_id: str | None = None
    completion_reason_codes: list[ReasonCode] = field(default_factory=list)


@dataclass(frozen=True)
class PolicyOutcome:
    action: Action
    target_node_id: str
    reason_codes: list[ReasonCode]
    candidates: list[CandidateAction]


class TutorPolicy:
    """Pure P0-P7 policy. It has no repository, network, model, or ID generation access."""

    def decide(self, context: PolicyContext) -> PolicyOutcome:
        candidates: list[CandidateAction] = []

        def choose(
            action: Action, target: str, reasons: list[ReasonCode], priority: int
        ) -> PolicyOutcome:
            candidate = CandidateAction(
                action=action,
                target_node_id=target,
                reason_codes=reasons,
                rank=[priority],
            )
            candidates.append(candidate)
            return PolicyOutcome(action, target, reasons, candidates)

        # P0: malformed or context-mismatched assessment never mutates learner state.
        if not context.assessment_valid:
            return choose(
                Action.RETRY,
                context.current_node_id,
                [ReasonCode.INVALID_ASSESSMENT],
                0,
            )
        if context.event_type == EventType.SELF_REPORTED_MASTERY:
            return choose(
                Action.ASSESS,
                context.current_node_id,
                [ReasonCode.SELF_REPORTED_MASTERY_IGNORED, ReasonCode.EVIDENCE_INSUFFICIENT],
                0,
            )
        if context.event_type == EventType.SIDE_QUESTION:
            return choose(
                Action.ANSWER_SIDE_QUESTION,
                context.current_node_id,
                [ReasonCode.SIDE_QUESTION_PRESERVED],
                0,
            )
        if context.event_type == EventType.REQUEST_HINT:
            return choose(
                Action.HINT,
                context.current_node_id,
                [ReasonCode.HINT_REQUESTED],
                0,
            )
        if context.event_type == EventType.REQUEST_ANSWER:
            return choose(
                Action.TEACH,
                context.current_node_id,
                [ReasonCode.ANSWER_REVEALED, ReasonCode.EVIDENCE_INSUFFICIENT],
                0,
            )

        # P1: ambiguous output gets clarification, not a confident state transition.
        if context.ambiguous:
            return choose(
                Action.RETRY,
                context.current_node_id,
                [ReasonCode.ANSWER_AMBIGUOUS],
                1,
            )

        # P2: a critical misconception outranks advancement and ordinary weakness.
        if context.critical_misconception_detected:
            target = context.remediation_target_node_id or context.current_node_id
            action = Action.REMEDIATE if target != context.current_node_id else Action.HINT
            reasons = [ReasonCode.CRITICAL_MISCONCEPTION_DETECTED]
            if target != context.current_node_id:
                reasons.append(ReasonCode.WEAK_PREREQUISITE)
            return choose(action, target, reasons, 2)

        # P3: prerequisite remediation is selected before continuing the current node.
        if context.remediation_target_node_id is not None:
            return choose(
                Action.REMEDIATE,
                context.remediation_target_node_id,
                [ReasonCode.WEAK_PREREQUISITE],
                3,
            )

        # P4-P5: incorrect and partial answers stay on the current learning goal.
        if context.score is not None and context.score < 0.5:
            return choose(
                Action.HINT,
                context.current_node_id,
                [ReasonCode.CURRENT_ANSWER_INCORRECT],
                4,
            )
        if context.understanding in {Understanding.PARTIAL, Understanding.UNCERTAIN}:
            return choose(
                Action.HINT,
                context.current_node_id,
                [ReasonCode.PARTIAL_UNDERSTANDING],
                5,
            )

        # P6: a correct answer is still insufficient until the deterministic gate passes.
        if not context.current_mastered:
            action = Action.ASSESS if context.next_question_id else Action.TEACH
            return choose(
                action,
                context.current_node_id,
                [ReasonCode.EVIDENCE_INSUFFICIENT],
                6,
            )

        # P7: completion details are precomputed from graph state and the return stack.
        return choose(
            context.completion_action or Action.ADVANCE,
            context.completion_target_node_id or context.current_node_id,
            context.completion_reason_codes or [ReasonCode.MASTERY_REQUIREMENTS_MET],
            7,
        )
