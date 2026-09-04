from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from backend.app.curriculum.graph import CourseGraph
from backend.app.curriculum.loader import CurriculumCatalog
from backend.app.curriculum.models import AccessStatus, LearnerStatus, ProgressStatus
from backend.app.learner.models import Evidence, LearnerNodeState, utc_now
from backend.app.learner.repository import (
    EvidenceRepository,
    LearnerRepository,
    MisconceptionRepository,
)
from backend.app.learner.schemas import AssistanceLevel, EvidenceInput, RubricResultInput
from backend.app.learner.service import DEFAULT_LEARNER_ID, LearnerStateService
from backend.app.tutor.domain import (
    Action,
    AssessmentResult,
    CandidateAction,
    Decision,
    DecisionTrace,
    EntryMode,
    EventType,
    LearningSessionView,
    NodeStateChange,
    NodeStateSnapshot,
    ReasonCode,
    SessionMode,
    SessionStatus,
    StateDelta,
    TeacherDirective,
    TutorEvent,
    TutorTurnResult,
    Understanding,
)
from backend.app.tutor.models import DecisionTraceRecord, LearningSession
from backend.app.tutor.planner import AssessmentPlanner
from backend.app.tutor.policy import PolicyContext, PolicyOutcome, TutorPolicy
from backend.app.tutor.remediation import RemediationSelector
from backend.app.tutor.repository import DecisionTraceRepository, LearningSessionRepository

DIAGNOSTIC_PROBE_WEIGHT_MULTIPLIER = 0.05


class TutorEngineError(ValueError):
    pass


class TutorEngine:
    def __init__(
        self,
        catalog: CurriculumCatalog,
        session_factory: sessionmaker[Session],
        learner_state_service: LearnerStateService | None = None,
    ) -> None:
        self.catalog = catalog
        self.graph = CourseGraph(catalog)
        self.session_factory = session_factory
        self.learner_state = learner_state_service or LearnerStateService(catalog, session_factory)
        self.assessments = {item.id: item for item in catalog.assessment_set.assessments}
        self.pilot_nodes = {item.id: item for item in catalog.pilot.nodes}
        self.misconceptions = {item.id: item for item in catalog.pilot.misconceptions}
        self.planner = AssessmentPlanner(catalog)
        self.remediation = RemediationSelector(catalog)
        self.policy = TutorPolicy()

    def start_session(
        self,
        target_node_id: str,
        mode: SessionMode = SessionMode.LEARN,
        *,
        entry_mode: EntryMode = EntryMode.NORMAL,
    ) -> TutorTurnResult:
        if target_node_id not in self.pilot_nodes:
            raise TutorEngineError(f"目标不是可教学的 pilot node: {target_node_id}")

        with self.session_factory.begin() as db:
            if LearnerRepository(db).get(DEFAULT_LEARNER_ID) is None:
                raise TutorEngineError("default learner 尚未初始化")
            now = utc_now()
            record = LearningSession(
                id=f"session_{uuid4().hex}",
                learner_id=DEFAULT_LEARNER_ID,
                mode=mode.value,
                entry_mode=entry_mode.value,
                version=1,
                target_node_id=target_node_id,
                current_node_id=target_node_id,
                expected_question_id=None,
                return_stack_json=[],
                status=SessionStatus.ACTIVE.value,
                last_action=None,
                current_assistance_level="none",
                used_target_diagnostic_probes_json=[],
                current_question_is_diagnostic_probe=False,
                recoverable_error_json=None,
                created_at=now,
                updated_at=now,
            )
            LearningSessionRepository(db).add(record)
            db.flush()

            session_input = {
                "event": "start_session",
                "requested_target_node_id": target_node_id,
                "session": self._session_view(record).model_dump(mode="json"),
            }
            states = self._states(db)
            state_before = self._snapshots(states)
            target_state = self._require_state(states, target_node_id)
            candidates: list[CandidateAction] = []
            diagnostic_consumed = False

            probe_id = self._available_probe(record, target_state)
            if entry_mode == EntryMode.REVIEW:
                action = Action.REVIEW
                action_target = target_node_id
                reasons = [ReasonCode.NODE_AVAILABLE]
                record.expected_question_id = self._planned_question(
                    db, record, target_node_id, target_state
                )
                candidates.append(
                    CandidateAction(
                        action=action,
                        target_node_id=action_target,
                        reason_codes=reasons,
                        rank=[7],
                    )
                )
            elif target_state.status == "locked" and probe_id is not None:
                record.expected_question_id = probe_id
                record.current_question_is_diagnostic_probe = True
                record.used_target_diagnostic_probes_json = [target_node_id]
                action = Action.ASSESS
                action_target = target_node_id
                reasons = [ReasonCode.TARGET_LOCKED, ReasonCode.TARGET_DIAGNOSTIC_PROBE]
                diagnostic_consumed = True
                candidates.append(
                    CandidateAction(
                        action=action,
                        target_node_id=action_target,
                        reason_codes=reasons,
                        rank=[0],
                    )
                )
            elif target_state.status == "locked":
                selection = self.remediation.select(
                    target_node_id=target_node_id,
                    current_node_id=target_node_id,
                    states=states,
                )
                candidates.extend(selection.candidates)
                if selection.selected_node_id is None:
                    action = Action.TEACH
                    action_target = target_node_id
                    reasons = [ReasonCode.TARGET_LOCKED, ReasonCode.NO_AVAILABLE_REMEDIATION]
                else:
                    action = Action.REMEDIATE
                    action_target = selection.selected_node_id
                    reasons = [ReasonCode.TARGET_LOCKED, ReasonCode.WEAK_PREREQUISITE]
                    self._push_return_target(record, target_node_id)
                    record.current_node_id = action_target
                    record.expected_question_id = self._planned_question(
                        db, record, action_target, states[action_target]
                    )
            else:
                action = Action.ORIENT
                action_target = target_node_id
                reasons = [ReasonCode.NODE_AVAILABLE]
                record.expected_question_id = self._planned_question(
                    db, record, target_node_id, target_state
                )
                candidates.append(
                    CandidateAction(
                        action=action,
                        target_node_id=action_target,
                        reason_codes=reasons,
                        rank=[7],
                    )
                )

            record.last_action = action.value
            record.updated_at = utc_now()
            state_delta = StateDelta(
                diagnostic_probe_consumed=diagnostic_consumed,
                session_changes=self._session_changes(session_input["session"], record),
            )
            decision = self._decision(
                action=action,
                target_node_id=action_target,
                reasons=reasons,
                state_delta=state_delta,
                record=record,
            )
            self._persist_trace(
                db,
                record=record,
                session_input=session_input,
                assessment_summary=None,
                state_before=state_before,
                candidates=candidates,
                decision=decision,
            )
            db.flush()
            return TutorTurnResult(session=self._session_view(record), decision=decision)

    def handle_event(
        self,
        session_id: str,
        event: TutorEvent,
        *,
        expected_version: int | None = None,
    ) -> TutorTurnResult:
        with self.session_factory.begin() as db:
            record = self._require_session(db, session_id)
            if record.status != SessionStatus.ACTIVE.value:
                raise TutorEngineError(f"Session 已结束: {session_id}")
            if expected_version is not None and record.version != expected_version:
                raise TutorEngineError(
                    "SESSION_VERSION_CONFLICT: "
                    f"expected {expected_version}, current {record.version}"
                )

            before_session = self._session_view(record).model_dump(mode="json")
            session_input = {
                "event": event.model_dump(mode="json"),
                "session": before_session,
            }
            states_before = self._states(db)
            state_before = self._snapshots(states_before)
            assessment_summary = (
                event.assessment.model_dump(mode="json") if event.assessment else None
            )

            if event.type != EventType.ASSESSMENT:
                if event.type == EventType.REQUEST_HINT:
                    record.current_assistance_level = self._next_assistance(
                        record.current_assistance_level
                    )
                elif event.type == EventType.REQUEST_ANSWER:
                    previous_question_id = record.expected_question_id
                    record.current_assistance_level = "answer_revealed"
                    record.current_question_is_diagnostic_probe = False
                    record.expected_question_id = self._planned_question(
                        db,
                        record,
                        record.current_node_id,
                        states_before[record.current_node_id],
                        extra_excluded_question_ids=(
                            {previous_question_id} if previous_question_id else set()
                        ),
                    )
                outcome = self.policy.decide(
                    PolicyContext(
                        event_type=event.type,
                        current_node_id=record.current_node_id,
                        assessment_valid=event.type != EventType.INVALID_ASSESSMENT,
                        next_question_id=record.expected_question_id,
                    )
                )
                if outcome.action == Action.ASSESS and record.expected_question_id is None:
                    record.expected_question_id = self._planned_question(
                        db,
                        record,
                        record.current_node_id,
                        states_before[record.current_node_id],
                    )
                return self._finish_turn(
                    db,
                    record=record,
                    outcome=outcome,
                    session_input=session_input,
                    assessment_summary=assessment_summary,
                    state_before=state_before,
                    before_session=before_session,
                    extra_candidates=[],
                    state_delta=StateDelta(),
                )

            assessment = cast(AssessmentResult, event.assessment)
            validation_error = self._assessment_validation_error(record, assessment)
            if validation_error is not None:
                session_input["validation_error"] = validation_error
                outcome = self.policy.decide(
                    PolicyContext(
                        event_type=event.type,
                        current_node_id=record.current_node_id,
                        assessment_valid=False,
                    )
                )
                return self._finish_turn(
                    db,
                    record=record,
                    outcome=outcome,
                    session_input=session_input,
                    assessment_summary=assessment_summary,
                    state_before=state_before,
                    before_session=before_session,
                    extra_candidates=[],
                    state_delta=StateDelta(),
                )

            if assessment.answer_is_ambiguous:
                outcome = self.policy.decide(
                    PolicyContext(
                        event_type=event.type,
                        current_node_id=record.current_node_id,
                        ambiguous=True,
                        understanding=assessment.understanding,
                        score=assessment.score,
                    )
                )
                return self._finish_turn(
                    db,
                    record=record,
                    outcome=outcome,
                    session_input=session_input,
                    assessment_summary=assessment_summary,
                    state_before=state_before,
                    before_session=before_session,
                    extra_candidates=[],
                    state_delta=StateDelta(),
                )

            score = self._recalculate_score(assessment)
            assessment_summary = {
                **cast(dict[str, Any], assessment_summary),
                "backend_recalculated_score": score,
            }
            evidence = self.learner_state.record_evidence_in_session(
                db,
                EvidenceInput(
                    node_id=assessment.node_id,
                    question_id=assessment.question_id,
                    evidence_type=self.assessments[assessment.question_id].evidence_type,
                    score=score,
                    assistance_level=cast(AssistanceLevel, record.current_assistance_level),
                    rubric_results=[
                        RubricResultInput(
                            criterion_id=item.criterion_id,
                            result=item.result,
                        )
                        for item in assessment.rubric_results
                    ],
                    misconception_ids=assessment.misconception_ids,
                    session_id=record.id,
                ),
                weight_multiplier=(
                    DIAGNOSTIC_PROBE_WEIGHT_MULTIPLIER
                    if record.current_question_is_diagnostic_probe
                    else 1.0
                ),
            )
            resolved_ids = self._resolve_corrected_misconceptions(db, assessment, evidence)
            states_after = self._states(db)
            current_state = states_after[record.current_node_id]
            active_critical_ids = self._active_critical_ids(db, record.current_node_id)
            selection = self.remediation.select(
                target_node_id=record.target_node_id,
                current_node_id=record.current_node_id,
                states=states_after,
                critical_misconception_ids=active_critical_ids,
                missing_concept_ids=assessment.missing_concept_ids,
                include_prerequisite_closure=current_state.status == "locked",
            )
            remediation_target = selection.selected_node_id
            if remediation_target == record.current_node_id and not active_critical_ids:
                remediation_target = None

            next_question = self._planned_question(
                db, record, record.current_node_id, current_state
            )
            completion_action: Action | None = None
            completion_target: str | None = None
            completion_reasons: list[ReasonCode] = []
            completion_question: str | None = None
            completion_return_target: str | None = None
            completion_candidates: list[CandidateAction] = []
            if current_state.progress_status == "mastered":
                (
                    completion_action,
                    completion_target,
                    completion_reasons,
                    completion_question,
                    completion_return_target,
                    completion_candidates,
                ) = self._completion_plan(db, record, states_after)

            outcome = self.policy.decide(
                PolicyContext(
                    event_type=event.type,
                    current_node_id=record.current_node_id,
                    understanding=assessment.understanding,
                    score=score,
                    critical_misconception_detected=bool(active_critical_ids),
                    remediation_target_node_id=remediation_target,
                    current_mastered=current_state.progress_status == "mastered",
                    next_question_id=next_question,
                    completion_action=completion_action,
                    completion_target_node_id=completion_target,
                    completion_reason_codes=completion_reasons,
                )
            )

            self._apply_outcome(
                db,
                record,
                outcome,
                states_after,
                next_question=next_question,
                completion_question=completion_question,
                completion_return_target=completion_return_target,
            )
            state_delta = self._state_delta(
                state_before,
                self._snapshots(states_after),
                evidence=evidence,
                activated_ids=assessment.misconception_ids,
                resolved_ids=resolved_ids,
                diagnostic_probe_consumed=bool(
                    before_session["current_question_is_diagnostic_probe"]
                ),
            )
            return self._finish_turn(
                db,
                record=record,
                outcome=outcome,
                session_input=session_input,
                assessment_summary=assessment_summary,
                state_before=state_before,
                before_session=before_session,
                extra_candidates=[*selection.candidates, *completion_candidates],
                state_delta=state_delta,
                outcome_already_applied=True,
            )

    def get_session(self, session_id: str) -> LearningSessionView:
        with self.session_factory() as db:
            return self._session_view(self._require_session(db, session_id))

    def list_decision_traces(self, session_id: str) -> list[DecisionTrace]:
        with self.session_factory() as db:
            self._require_session(db, session_id)
            return [
                self._trace_view(item)
                for item in DecisionTraceRepository(db).list_for_session(session_id)
            ]

    def _finish_turn(
        self,
        db: Session,
        *,
        record: LearningSession,
        outcome: PolicyOutcome,
        session_input: dict[str, Any],
        assessment_summary: dict[str, Any] | None,
        state_before: dict[str, NodeStateSnapshot],
        before_session: dict[str, Any],
        extra_candidates: list[CandidateAction],
        state_delta: StateDelta,
        outcome_already_applied: bool = False,
    ) -> TutorTurnResult:
        if not outcome_already_applied:
            record.last_action = outcome.action.value
            record.updated_at = utc_now()
        record.version += 1
        record.recoverable_error_json = None
        state_delta.session_changes = self._session_changes(before_session, record)
        decision = self._decision(
            action=outcome.action,
            target_node_id=outcome.target_node_id,
            reasons=outcome.reason_codes,
            state_delta=state_delta,
            record=record,
        )
        candidates = self._deduplicate_candidates([*extra_candidates, *outcome.candidates])
        self._persist_trace(
            db,
            record=record,
            session_input=session_input,
            assessment_summary=assessment_summary,
            state_before=state_before,
            candidates=candidates,
            decision=decision,
        )
        db.flush()
        return TutorTurnResult(session=self._session_view(record), decision=decision)

    def _apply_outcome(
        self,
        db: Session,
        record: LearningSession,
        outcome: PolicyOutcome,
        states: Mapping[str, LearnerNodeState],
        *,
        next_question: str | None,
        completion_question: str | None,
        completion_return_target: str | None,
    ) -> None:
        previous_node_id = record.current_node_id
        if outcome.action == Action.REMEDIATE and outcome.target_node_id != previous_node_id:
            if states[previous_node_id].progress_status != "mastered":
                self._push_return_target(record, previous_node_id)
            elif completion_return_target is not None:
                self._push_return_target(record, completion_return_target)
            record.current_node_id = outcome.target_node_id
            record.expected_question_id = self._planned_question(
                db, record, outcome.target_node_id, states[outcome.target_node_id]
            )
            record.current_assistance_level = "none"
        elif outcome.action == Action.ASSESS:
            if outcome.target_node_id != previous_node_id:
                self._pop_return_target(record, outcome.target_node_id)
                record.current_node_id = outcome.target_node_id
                record.expected_question_id = completion_question
            else:
                record.expected_question_id = next_question
            record.current_assistance_level = "none"
        elif outcome.action == Action.ADVANCE:
            if previous_node_id == record.target_node_id:
                # A target session ends at target mastery. The recommended next node is
                # returned by the Decision, but starting it remains an explicit user action.
                record.current_node_id = previous_node_id
                record.expected_question_id = None
                record.status = SessionStatus.COMPLETED.value
            else:
                record.current_node_id = outcome.target_node_id
                record.expected_question_id = completion_question
            record.current_assistance_level = "none"
            if outcome.target_node_id == previous_node_id and completion_question is None:
                record.status = SessionStatus.COMPLETED.value
        elif outcome.action == Action.HINT:
            record.current_assistance_level = self._next_assistance(record.current_assistance_level)
        elif outcome.action == Action.TEACH:
            record.expected_question_id = next_question

        if outcome.action not in {Action.HINT, Action.RETRY}:
            record.current_question_is_diagnostic_probe = False
        record.last_action = outcome.action.value
        record.updated_at = utc_now()

    def _completion_plan(
        self,
        db: Session,
        record: LearningSession,
        states: Mapping[str, LearnerNodeState],
    ) -> tuple[
        Action,
        str,
        list[ReasonCode],
        str | None,
        str | None,
        list[CandidateAction],
    ]:
        if record.return_stack_json:
            return_target = record.return_stack_json[-1]
            mastered_ids = {
                item.node_id for item in states.values() if item.progress_status == "mastered"
            }
            missing_ids = {
                item.id for item in self.graph.unmet_prerequisites(return_target, mastered_ids)
            }
            if missing_ids:
                selection = self.remediation.select(
                    target_node_id=return_target,
                    current_node_id=record.current_node_id,
                    states=states,
                    missing_concept_ids=[
                        item.id
                        for item in self.graph.prerequisite_closure(return_target)
                        if item.id in missing_ids
                    ],
                    restrict_to=missing_ids,
                    include_prerequisite_closure=False,
                )
                if selection.selected_node_id is not None:
                    question = self._planned_question(
                        db,
                        record,
                        selection.selected_node_id,
                        states[selection.selected_node_id],
                    )
                    return (
                        Action.REMEDIATE,
                        selection.selected_node_id,
                        [ReasonCode.MASTERY_REQUIREMENTS_MET, ReasonCode.WEAK_PREREQUISITE],
                        question,
                        None,
                        selection.candidates,
                    )

            question = self._planned_question(db, record, return_target, states[return_target])
            return (
                Action.ASSESS,
                return_target,
                [ReasonCode.MASTERY_REQUIREMENTS_MET, ReasonCode.RETURN_TO_TARGET],
                question,
                None,
                [],
            )

        next_nodes = [
            item
            for item in self.graph.recommended_next(record.current_node_id)
            if item.id in self.pilot_nodes
        ]
        if next_nodes:
            next_node = next_nodes[0]
            mastered_ids = {
                item.node_id for item in states.values() if item.progress_status == "mastered"
            }
            missing_ids = {
                item.id for item in self.graph.unmet_prerequisites(next_node.id, mastered_ids)
            }
            if missing_ids:
                selection = self.remediation.select(
                    target_node_id=next_node.id,
                    current_node_id=record.current_node_id,
                    states=states,
                    missing_concept_ids=[
                        item.id
                        for item in self.graph.prerequisite_closure(next_node.id)
                        if item.id in missing_ids
                    ],
                    restrict_to=missing_ids,
                    include_prerequisite_closure=False,
                )
                if selection.selected_node_id is not None:
                    question = self._planned_question(
                        db,
                        record,
                        selection.selected_node_id,
                        states[selection.selected_node_id],
                    )
                    return (
                        Action.REMEDIATE,
                        selection.selected_node_id,
                        [ReasonCode.MASTERY_REQUIREMENTS_MET, ReasonCode.WEAK_PREREQUISITE],
                        question,
                        next_node.id,
                        selection.candidates,
                    )
            question = self._planned_question(db, record, next_node.id, states[next_node.id])
            return (
                Action.ADVANCE,
                next_node.id,
                [ReasonCode.MASTERY_REQUIREMENTS_MET],
                question,
                None,
                [],
            )
        return (
            Action.ADVANCE,
            record.current_node_id,
            [ReasonCode.MASTERY_REQUIREMENTS_MET],
            None,
            None,
            [],
        )

    def _assessment_validation_error(
        self, record: LearningSession, result: AssessmentResult
    ) -> str | None:
        if record.expected_question_id is None:
            return "session 没有 expected_question_id"
        if result.question_id != record.expected_question_id:
            return (
                f"question mismatch: expected {record.expected_question_id}, "
                f"received {result.question_id}"
            )
        assessment = self.assessments.get(result.question_id)
        if assessment is None:
            return f"未知 assessment: {result.question_id}"
        if result.node_id != assessment.node_id or result.node_id != record.current_node_id:
            return "assessment node 与课程或 current_node 不匹配"

        expected_criteria = {item.id for item in assessment.rubric.criteria}
        received_criteria = {item.criterion_id for item in result.rubric_results}
        if received_criteria != expected_criteria:
            return "rubric_results 必须精确覆盖课程 rubric criteria"
        if not set(result.misconception_ids) <= set(assessment.rubric.critical_misconception_ids):
            return "assessment 包含本题未声明的 misconception ID"

        related_ids = {
            record.current_node_id,
            record.target_node_id,
            *(item.id for item in self.graph.prerequisite_closure(record.current_node_id)),
            *(item.id for item in self.graph.prerequisite_closure(record.target_node_id)),
        }
        if not set(result.missing_concept_ids) <= related_ids:
            return "assessment 包含与 current/target graph 无关的 missing concept ID"
        if (
            result.recommended_target_node_id is not None
            and result.recommended_target_node_id not in related_ids
        ):
            return "recommended target node 未知或与当前图上下文无关"
        return None

    def _recalculate_score(self, result: AssessmentResult) -> float:
        assessment = self.assessments[result.question_id]
        values = self.catalog.assessment_set.scoring_policy
        score_by_result = {
            "met": values.met_value,
            "uncertain": values.uncertain_value,
            "not_met": values.not_met_value,
        }
        result_by_id = {item.criterion_id: item.result for item in result.rubric_results}
        total_weight = sum(item.weight for item in assessment.rubric.criteria)
        weighted = sum(
            item.weight * score_by_result[result_by_id[item.id]]
            for item in assessment.rubric.criteria
        )
        return round(weighted / total_weight, 6)

    def _resolve_corrected_misconceptions(
        self, db: Session, result: AssessmentResult, evidence: Evidence
    ) -> list[str]:
        if result.understanding != Understanding.CORRECT or evidence.score < 0.8:
            return []
        allowed = set(self.assessments[result.question_id].rubric.critical_misconception_ids)
        resolved: list[str] = []
        for item in MisconceptionRepository(db).list_for_node(DEFAULT_LEARNER_ID, result.node_id):
            if (
                item.status == "active"
                and item.misconception_id in allowed
                and item.misconception_id not in result.misconception_ids
                and self.learner_state.try_resolve_misconception_in_session(
                    db, item.misconception_id, evidence.id
                )
            ):
                resolved.append(item.misconception_id)
        return resolved

    def _active_critical_ids(self, db: Session, node_id: str) -> list[str]:
        return [
            item.misconception_id
            for item in MisconceptionRepository(db).list_for_node(DEFAULT_LEARNER_ID, node_id)
            if item.status == "active" and self.misconceptions[item.misconception_id].critical
        ]

    def _planned_question(
        self,
        db: Session,
        record: LearningSession,
        node_id: str,
        state: LearnerNodeState,
        *,
        extra_excluded_question_ids: set[str] | frozenset[str] = frozenset(),
    ) -> str | None:
        excluded: set[str] = set(extra_excluded_question_ids)
        if node_id in record.used_target_diagnostic_probes_json:
            probe = self.catalog.pilot.entry_policy.target_probe_questions.get(node_id)
            if probe:
                excluded.add(probe)
        evidence = EvidenceRepository(db).list_for_node(DEFAULT_LEARNER_ID, node_id)
        return self.planner.next_question(node_id, state, evidence, excluded_question_ids=excluded)

    def _available_probe(
        self, record: LearningSession, target_state: LearnerNodeState
    ) -> str | None:
        policy = self.catalog.pilot.entry_policy
        if (
            target_state.status != "locked"
            or not policy.allow_target_diagnostic_probe
            or record.target_node_id in record.used_target_diagnostic_probes_json
        ):
            return None
        return policy.target_probe_questions.get(record.target_node_id)

    def _states(self, db: Session) -> dict[str, LearnerNodeState]:
        return {
            item.node_id: item
            for item in LearnerRepository(db).list_node_states(DEFAULT_LEARNER_ID)
        }

    def _snapshots(self, states: Mapping[str, LearnerNodeState]) -> dict[str, NodeStateSnapshot]:
        return {
            node_id: self._snapshot(states[node_id])
            for node_id in self.pilot_nodes
            if node_id in states
        }

    @staticmethod
    def _snapshot(state: LearnerNodeState) -> NodeStateSnapshot:
        return NodeStateSnapshot(
            node_id=state.node_id,
            learner_status=cast(LearnerStatus, state.status),
            progress_status=cast(ProgressStatus, state.progress_status),
            access_status=cast(AccessStatus, "locked" if state.status == "locked" else "available"),
            mastery_score=state.mastery_score,
            confidence_score=state.confidence_score,
            evidence_weight=state.evidence_weight,
            attempts=state.attempts,
        )

    @staticmethod
    def _state_delta(
        before: Mapping[str, NodeStateSnapshot],
        after: Mapping[str, NodeStateSnapshot],
        *,
        evidence: Evidence,
        activated_ids: list[str],
        resolved_ids: list[str],
        diagnostic_probe_consumed: bool,
    ) -> StateDelta:
        return StateDelta(
            node_changes={
                node_id: NodeStateChange(before=before[node_id], after=after[node_id])
                for node_id in sorted(before.keys() & after.keys())
                if before[node_id] != after[node_id]
            },
            evidence_id=evidence.id,
            activated_misconception_ids=list(activated_ids),
            resolved_misconception_ids=resolved_ids,
            diagnostic_probe_consumed=diagnostic_probe_consumed,
        )

    def _decision(
        self,
        *,
        action: Action,
        target_node_id: str,
        reasons: list[ReasonCode],
        state_delta: StateDelta,
        record: LearningSession,
    ) -> Decision:
        return Decision(
            action=action,
            target_node_id=target_node_id,
            reason_codes=reasons,
            teacher_directive=self._directive(action, target_node_id, record.expected_question_id),
            state_delta=state_delta,
            next_expected_question_id=record.expected_question_id,
            return_stack=list(record.return_stack_json),
        )

    def _directive(self, action: Action, node_id: str, question_id: str | None) -> TeacherDirective:
        node = self.pilot_nodes[node_id]
        question_actions = {
            Action.ASK,
            Action.ASSESS,
            Action.HINT,
            Action.RETRY,
            Action.REMEDIATE,
            Action.REVIEW,
        }
        return TeacherDirective(
            learning_goal=node.learning_objectives[0],
            interaction_type=action.value.lower(),
            must_ask_one_question=action in question_actions and question_id is not None,
            must_not_reveal_full_answer=action in question_actions,
            preferred_method=node.teaching_moves[0] if node.teaching_moves else None,
            question_id=question_id,
            max_length_chars=500,
        )

    def _persist_trace(
        self,
        db: Session,
        *,
        record: LearningSession,
        session_input: dict[str, Any],
        assessment_summary: dict[str, Any] | None,
        state_before: dict[str, NodeStateSnapshot],
        candidates: list[CandidateAction],
        decision: Decision,
    ) -> None:
        DecisionTraceRepository(db).add(
            DecisionTraceRecord(
                id=f"trace_{uuid4().hex}",
                session_id=record.id,
                session_input_json=session_input,
                assessment_summary_json=assessment_summary,
                state_before_json={
                    key: value.model_dump(mode="json") for key, value in state_before.items()
                },
                candidate_actions_json=[item.model_dump(mode="json") for item in candidates],
                final_action=decision.action.value,
                target_node_id=decision.target_node_id,
                reason_codes_json=[item.value for item in decision.reason_codes],
                state_delta_json=decision.state_delta.model_dump(mode="json"),
                next_expected_question_id=decision.next_expected_question_id,
                created_at=utc_now(),
            )
        )

    @staticmethod
    def _trace_view(record: DecisionTraceRecord) -> DecisionTrace:
        return DecisionTrace(
            trace_id=record.id,
            session_id=record.session_id,
            session_input=record.session_input_json,
            assessment_summary=record.assessment_summary_json,
            state_before={
                key: NodeStateSnapshot.model_validate(value)
                for key, value in record.state_before_json.items()
            },
            candidate_actions=[
                CandidateAction.model_validate(item) for item in record.candidate_actions_json
            ],
            final_action=Action(record.final_action),
            target_node_id=record.target_node_id,
            reason_codes=[ReasonCode(item) for item in record.reason_codes_json],
            state_delta=StateDelta.model_validate(record.state_delta_json),
            next_expected_question_id=record.next_expected_question_id,
            created_at=record.created_at,
        )

    @staticmethod
    def _session_view(record: LearningSession) -> LearningSessionView:
        return LearningSessionView(
            session_id=record.id,
            learner_id=record.learner_id,
            mode=SessionMode(record.mode),
            entry_mode=EntryMode(record.entry_mode),
            version=record.version,
            target_node_id=record.target_node_id,
            current_node_id=record.current_node_id,
            expected_question_id=record.expected_question_id,
            return_stack=list(record.return_stack_json),
            status=SessionStatus(record.status),
            last_action=Action(record.last_action) if record.last_action else None,
            current_assistance_level=cast(AssistanceLevel, record.current_assistance_level),
            used_target_diagnostic_probes=list(record.used_target_diagnostic_probes_json),
            current_question_is_diagnostic_probe=record.current_question_is_diagnostic_probe,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _session_changes(before: dict[str, Any], record: LearningSession) -> dict[str, Any]:
        after = TutorEngine._session_view(record).model_dump(mode="json")
        tracked = (
            "current_node_id",
            "version",
            "expected_question_id",
            "return_stack",
            "status",
            "last_action",
            "current_assistance_level",
            "used_target_diagnostic_probes",
            "current_question_is_diagnostic_probe",
        )
        return {
            key: {"before": before.get(key), "after": after.get(key)}
            for key in tracked
            if before.get(key) != after.get(key)
        }

    @staticmethod
    def _push_return_target(record: LearningSession, node_id: str) -> None:
        stack = list(record.return_stack_json)
        if node_id not in stack:
            stack.append(node_id)
            record.return_stack_json = stack

    @staticmethod
    def _pop_return_target(record: LearningSession, node_id: str) -> None:
        stack = list(record.return_stack_json)
        if stack and stack[-1] == node_id:
            stack.pop()
            record.return_stack_json = stack

    @staticmethod
    def _next_assistance(current: str) -> str:
        return {
            "none": "light_hint",
            "light_hint": "strong_hint",
            "strong_hint": "answer_revealed",
            "answer_revealed": "answer_revealed",
        }[current]

    @staticmethod
    def _deduplicate_candidates(items: list[CandidateAction]) -> list[CandidateAction]:
        result: list[CandidateAction] = []
        seen: set[tuple[Action, str, tuple[ReasonCode, ...]]] = set()
        for item in items:
            key = (item.action, item.target_node_id, tuple(item.reason_codes))
            if key not in seen:
                result.append(item)
                seen.add(key)
        return result

    @staticmethod
    def _require_state(states: Mapping[str, LearnerNodeState], node_id: str) -> LearnerNodeState:
        try:
            return states[node_id]
        except KeyError as exc:
            raise TutorEngineError(f"学习者缺少节点状态: {node_id}") from exc

    @staticmethod
    def _require_session(db: Session, session_id: str) -> LearningSession:
        record = LearningSessionRepository(db).get(session_id)
        if record is None:
            raise TutorEngineError(f"未知 LearningSession: {session_id}")
        return record
