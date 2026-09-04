from __future__ import annotations

import asyncio
from typing import Any, Literal, cast
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import Settings
from backend.app.curriculum.loader import CurriculumCatalog
from backend.app.curriculum.models import Assessment
from backend.app.learner.models import utc_now
from backend.app.learner.schemas import LearnerView
from backend.app.learner.service import DEFAULT_LEARNER_ID, LearnerStateService
from backend.app.llm.builders import TeacherRequestBuilder
from backend.app.llm.contracts import (
    LearnerTurnKind,
    LLMCallMetadata,
    LLMError,
    LLMErrorCode,
    LLMMode,
)
from backend.app.llm.demo_fixtures import demo_inputs
from backend.app.llm.models import LLMCallRecord
from backend.app.llm.repository import LLMCallRepository
from backend.app.llm.services import AssessorService, TeacherService, TeacherServiceResult
from backend.app.sessions.errors import SessionErrorCode, TutorSessionError
from backend.app.sessions.models import SessionMessage, TutorTurnRecord
from backend.app.sessions.repository import SessionMessageRepository, TutorTurnRepository
from backend.app.sessions.schemas import (
    AbandonSessionRequest,
    ActiveSessionSummary,
    AvailableActions,
    ChoiceOptionView,
    LearnerStateNodeSummary,
    MessageRole,
    QuestionView,
    RecoverableErrorView,
    RoadmapDeltaItem,
    SessionDebugView,
    SessionMessageView,
    SessionNodeView,
    StartSessionRequest,
    SubmitTurnRequest,
    TutorSessionSnapshot,
)
from backend.app.tutor.domain import (
    Action,
    AssessmentResult,
    EntryMode,
    EventType,
    SessionStatus,
    TutorEvent,
)
from backend.app.tutor.engine import TutorEngine, TutorEngineError
from backend.app.tutor.models import LearningSession
from backend.app.tutor.repository import DecisionTraceRepository, LearningSessionRepository

TURN_DISPLAY_TEXT = {
    LearnerTurnKind.REQUEST_HINT: "给我提示",
    LearnerTurnKind.REQUEST_ANSWER: "直接讲解",
    LearnerTurnKind.SELF_REPORTED_MASTERY: "我觉得我已经会了",
}


class TutorSessionService:
    def __init__(
        self,
        *,
        settings: Settings,
        catalog: CurriculumCatalog,
        session_factory: sessionmaker[Session],
        learner_state: LearnerStateService,
        tutor_engine: TutorEngine,
        assessor: AssessorService,
        teacher: TeacherService,
        teacher_builder: TeacherRequestBuilder,
    ) -> None:
        self.settings = settings
        self.catalog = catalog
        self.session_factory = session_factory
        self.learner_state = learner_state
        self.tutor_engine = tutor_engine
        self.assessor = assessor
        self.teacher = teacher
        self.teacher_builder = teacher_builder
        self.nodes = {item.id: item for item in catalog.roadmap.nodes}
        self.pilot_nodes = {item.id: item for item in catalog.pilot.nodes}
        self.assessments: dict[str, Assessment] = {
            item.id: item for item in catalog.assessment_set.assessments
        }
        self._learner_lock = asyncio.Lock()
        self._turn_locks: dict[str, asyncio.Lock] = {}

    async def start_or_resume(self, request: StartSessionRequest) -> TutorSessionSnapshot:
        async with self._learner_lock:
            active = self._active_record()
            if active is not None:
                if active.target_node_id == request.target_node_id:
                    return self.get_snapshot(active.id)
                raise TutorSessionError(
                    SessionErrorCode.ACTIVE_SESSION_EXISTS,
                    "已有进行中的学习会话",
                    status_code=409,
                    details={
                        "active_session_id": active.id,
                        "active_target_node_id": active.target_node_id,
                    },
                )

            self._validate_start(request.target_node_id, request.entry_mode)
            started = self.tutor_engine.start_session(
                request.target_node_id,
                entry_mode=request.entry_mode,
            )
            learner = self.learner_state.get_learner()
            teacher_request = self.teacher_builder.build(
                session=started.session,
                decision=started.decision,
                learner=learner,
                assessment=None,
            )
            teacher_result = await self.teacher.compose(teacher_request)
            error = (
                self._error_payload(teacher_result.error, source="teacher")
                if teacher_result.error
                else None
            )
            with self.session_factory.begin() as db:
                record = self._require_record(db, started.session.session_id)
                record.recoverable_error_json = error
                message = self._add_message(
                    db,
                    record.id,
                    role=MessageRole.TUTOR,
                    message_kind="initial",
                    text=teacher_result.message.student_message,
                    question_id=teacher_result.message.question_id,
                    interaction_type=teacher_result.message.interaction_type.value,
                    client_turn_id=None,
                )
                del message
                self._persist_metadata(
                    db,
                    teacher_result.metadata,
                    session_id=record.id,
                    client_turn_id=request.client_request_id,
                )
            return self.get_snapshot(started.session.session_id)

    def get_active(self) -> TutorSessionSnapshot | None:
        active = self._active_record()
        return self.get_snapshot(active.id) if active is not None else None

    def active_summary(self) -> ActiveSessionSummary | None:
        active = self._active_record()
        if active is None:
            return None
        return ActiveSessionSummary(
            session_id=active.id,
            target_node_id=active.target_node_id,
            current_node_id=active.current_node_id,
            version=active.version,
            mode=EntryMode(active.entry_mode),
        )

    def get_snapshot(self, session_id: str) -> TutorSessionSnapshot:
        learner = self.learner_state.get_learner()
        with self.session_factory() as db:
            record = self._require_record(db, session_id)
            return self._snapshot(db, record, learner)

    async def submit_turn(
        self, session_id: str, request: SubmitTurnRequest
    ) -> TutorSessionSnapshot:
        lock = self._turn_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            replay = self._replayed_turn(session_id, request.client_turn_id)
            if replay is not None:
                return replay

            try:
                answer_text, display_text = self._reserve_turn(session_id, request)
            except IntegrityError as exc:
                # The database uniqueness constraint is the cross-worker backstop;
                # the in-process lock only avoids duplicate work in this process.
                try:
                    replay = self._replayed_turn(session_id, request.client_turn_id)
                except TutorSessionError as pending_error:
                    raise pending_error from exc
                if replay is not None:
                    return replay
                raise TutorSessionError(
                    SessionErrorCode.TURN_IN_PROGRESS,
                    "相同 client_turn_id 的请求仍在处理中",
                    status_code=409,
                ) from exc
            metadata: list[LLMCallMetadata] = []
            assessment: AssessmentResult | None = None

            if request.kind == LearnerTurnKind.ANSWER:
                session_view = self.tutor_engine.get_session(session_id)
                try:
                    assessor_result = await self.assessor.assess(session_view, answer_text)
                except Exception:
                    return self._finish_assessor_failure(
                        session_id,
                        request.client_turn_id,
                        LLMError(
                            code=LLMErrorCode.PROVIDER_UNAVAILABLE,
                            message="Assessor 服务暂时不可用",
                        ),
                        metadata,
                    )
                metadata.extend(assessor_result.metadata)
                assessment = assessor_result.canonical
                if assessment is None:
                    return self._finish_assessor_failure(
                        session_id,
                        request.client_turn_id,
                        assessor_result.error,
                        metadata,
                    )

            self._recheck_reserved_context(session_id, request)
            event = self._event_for_turn(request.kind, assessment)
            try:
                engine_result = self.tutor_engine.handle_event(
                    session_id,
                    event,
                    expected_version=request.expected_session_version,
                )
            except TutorEngineError as exc:
                self._mark_reservation_failed(session_id, request.client_turn_id)
                if "SESSION_VERSION_CONFLICT" in str(exc):
                    raise TutorSessionError(
                        SessionErrorCode.SESSION_VERSION_CONFLICT,
                        "会话已在其他页面更新",
                        status_code=409,
                    ) from exc
                raise

            trace = self.tutor_engine.list_decision_traces(session_id)[-1]
            with self.session_factory.begin() as db:
                record = self._require_turn(db, session_id, request.client_turn_id)
                record.status = "engine_applied"
                record.assessment_result_json = (
                    assessment.model_dump(mode="json") if assessment else None
                )
                record.decision_json = engine_result.decision.model_dump(mode="json")
                record.decision_trace_id = trace.trace_id
                record.updated_at = utc_now()
                self._persist_metadata(
                    db,
                    metadata,
                    session_id=session_id,
                    client_turn_id=request.client_turn_id,
                )

            learner = self.learner_state.get_learner()
            teacher_request = self.teacher_builder.build(
                session=engine_result.session,
                decision=engine_result.decision,
                learner=learner,
                assessment=assessment,
            )
            try:
                teacher_result = await self.teacher.compose(teacher_request)
            except Exception:
                teacher_result = TeacherServiceResult(
                    request=teacher_request,
                    message=self.teacher.fallback_message(teacher_request),
                    error=LLMError(
                        code=LLMErrorCode.PROVIDER_UNAVAILABLE,
                        message="Teacher 服务暂时不可用",
                    ),
                    metadata=[],
                )
            error = (
                self._error_payload(teacher_result.error, source="teacher")
                if teacher_result.error
                else None
            )

            with self.session_factory.begin() as db:
                session_record = self._require_record(db, session_id)
                turn_record = self._require_turn(db, session_id, request.client_turn_id)
                session_record.recoverable_error_json = error
                self._add_message(
                    db,
                    session_id,
                    role=MessageRole.LEARNER,
                    message_kind=request.kind.value.lower(),
                    text=display_text,
                    question_id=request.expected_question_id,
                    interaction_type=None,
                    client_turn_id=request.client_turn_id,
                )
                tutor_message = self._add_message(
                    db,
                    session_id,
                    role=MessageRole.TUTOR,
                    message_kind=(
                        "recoverable_error" if teacher_result.error else "tutor_response"
                    ),
                    text=teacher_result.message.student_message,
                    question_id=teacher_result.message.question_id,
                    interaction_type=teacher_result.message.interaction_type.value,
                    client_turn_id=request.client_turn_id,
                )
                self._persist_metadata(
                    db,
                    teacher_result.metadata,
                    session_id=session_id,
                    client_turn_id=request.client_turn_id,
                )
                turn_record.status = "recoverable_error" if error else "completed"
                turn_record.tutor_message_id = tutor_message.id
                turn_record.recoverable_error_code = error["code"] if error else None
                turn_record.recoverable_error_json = error
                turn_record.updated_at = utc_now()
                snapshot = self._snapshot(db, session_record, learner)
                turn_record.response_json = snapshot.model_dump(mode="json")
            return snapshot

    def abandon(self, session_id: str, request: AbandonSessionRequest) -> TutorSessionSnapshot:
        learner = self.learner_state.get_learner()
        with self.session_factory.begin() as db:
            record = self._require_record(db, session_id)
            if record.status != SessionStatus.ACTIVE.value:
                raise TutorSessionError(
                    SessionErrorCode.SESSION_NOT_ACTIVE,
                    "会话已经结束",
                    status_code=409,
                )
            if record.version != request.expected_session_version:
                raise TutorSessionError(
                    SessionErrorCode.SESSION_VERSION_CONFLICT,
                    "会话已在其他页面更新",
                    status_code=409,
                )
            record.status = SessionStatus.ABANDONED.value
            record.version += 1
            record.updated_at = utc_now()
            record.recoverable_error_json = None
            self._add_message(
                db,
                session_id,
                role=MessageRole.SYSTEM,
                message_kind="session_abandoned",
                text="会话已结束，已有学习证据和状态保持不变。",
                question_id=None,
                interaction_type=None,
                client_turn_id=None,
            )
            return self._snapshot(db, record, learner)

    def _validate_start(self, node_id: str, mode: EntryMode) -> None:
        node = self.nodes.get(node_id)
        if node is None or node.implementation_status != "pilot":
            raise TutorSessionError(
                SessionErrorCode.COMING_LATER,
                "该节点尚未开放学习会话",
                status_code=400,
            )
        learner = self.learner_state.get_learner()
        state = learner.node_states[node_id]
        if mode == EntryMode.NORMAL:
            if state.access_status == "locked":
                raise TutorSessionError(
                    SessionErrorCode.NODE_LOCKED,
                    "该节点的前置知识尚未满足",
                    status_code=409,
                )
            if state.progress_status in {"mastered", "review_needed"}:
                raise TutorSessionError(
                    SessionErrorCode.INVALID_ENTRY_MODE,
                    "已掌握节点请使用 review 模式",
                )
        elif mode == EntryMode.DIAGNOSTIC:
            policy = self.catalog.pilot.entry_policy
            allowed = (
                state.access_status == "locked"
                and policy.allow_target_diagnostic_probe
                and node_id in policy.target_probe_questions
            )
            if not allowed:
                raise TutorSessionError(
                    SessionErrorCode.DIAGNOSTIC_PROBE_NOT_ALLOWED,
                    "该节点当前不允许目标诊断",
                    status_code=409,
                )
        elif mode == EntryMode.REVIEW and state.progress_status not in {
            "mastered",
            "review_needed",
        }:
            raise TutorSessionError(
                SessionErrorCode.INVALID_ENTRY_MODE,
                "只有已掌握或待复习节点可以进入 review",
            )

    def _reserve_turn(self, session_id: str, request: SubmitTurnRequest) -> tuple[str, str]:
        with self.session_factory.begin() as db:
            session_record = self._require_record(db, session_id)
            if session_record.status != SessionStatus.ACTIVE.value:
                raise TutorSessionError(
                    SessionErrorCode.SESSION_NOT_ACTIVE,
                    "会话已经结束",
                    status_code=409,
                )
            if session_record.version != request.expected_session_version:
                raise TutorSessionError(
                    SessionErrorCode.SESSION_VERSION_CONFLICT,
                    "会话已在其他页面更新",
                    status_code=409,
                )
            if session_record.expected_question_id != request.expected_question_id:
                raise TutorSessionError(
                    SessionErrorCode.EXPECTED_QUESTION_MISMATCH,
                    "提交的问题与当前会话问题不一致",
                    status_code=409,
                )

            answer_text, display_text = self._authoritative_turn_text(session_record, request)
            TutorTurnRepository(db).add(
                TutorTurnRecord(
                    id=f"turn_{uuid4().hex}",
                    session_id=session_id,
                    client_turn_id=request.client_turn_id,
                    learner_turn_kind=request.kind.value,
                    learner_text=(
                        request.text.strip()
                        if request.selected_option_id is None and request.text.strip()
                        else None
                    ),
                    option_id=request.selected_option_id,
                    expected_question_id=request.expected_question_id,
                    session_version_before=request.expected_session_version,
                    status="processing",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
            return answer_text, display_text

    def _authoritative_turn_text(
        self, session: LearningSession, request: SubmitTurnRequest
    ) -> tuple[str, str]:
        if request.kind == LearnerTurnKind.ANSWER:
            if session.expected_question_id is None:
                raise TutorSessionError(
                    SessionErrorCode.INVALID_TURN,
                    "当前没有可回答的问题",
                )
            assessment = self.assessments[session.expected_question_id]
            if assessment.question_type == "single_choice":
                options = {item.id: item.text for item in assessment.options}
                if request.selected_option_id not in options:
                    raise TutorSessionError(
                        SessionErrorCode.INVALID_OPTION_ID,
                        "选项不属于当前问题",
                    )
                authoritative = options[cast(str, request.selected_option_id)]
                return authoritative, authoritative
            if request.selected_option_id is not None or not request.text.strip():
                raise TutorSessionError(
                    SessionErrorCode.INVALID_TURN,
                    "自由文本回答不能为空，且不能提交 option_id",
                )
            return request.text.strip(), request.text.strip()
        if request.kind == LearnerTurnKind.SIDE_QUESTION:
            return request.text.strip(), request.text.strip()
        text = TURN_DISPLAY_TEXT[request.kind]
        return text, text

    def _recheck_reserved_context(self, session_id: str, request: SubmitTurnRequest) -> None:
        conflict: SessionErrorCode | None = None
        with self.session_factory() as db:
            record = self._require_record(db, session_id)
            if record.version != request.expected_session_version:
                conflict = SessionErrorCode.SESSION_VERSION_CONFLICT
            elif record.expected_question_id != request.expected_question_id:
                conflict = SessionErrorCode.EXPECTED_QUESTION_MISMATCH
        if conflict is not None:
            self._mark_reservation_failed(session_id, request.client_turn_id)
            message = (
                "会话已在其他页面更新"
                if conflict == SessionErrorCode.SESSION_VERSION_CONFLICT
                else "当前问题已经变化"
            )
            raise TutorSessionError(conflict, message, status_code=409)

    @staticmethod
    def _event_for_turn(kind: LearnerTurnKind, assessment: AssessmentResult | None) -> TutorEvent:
        if kind == LearnerTurnKind.ANSWER:
            return TutorEvent(type=EventType.ASSESSMENT, assessment=assessment)
        return TutorEvent(
            type={
                LearnerTurnKind.SIDE_QUESTION: EventType.SIDE_QUESTION,
                LearnerTurnKind.REQUEST_HINT: EventType.REQUEST_HINT,
                LearnerTurnKind.REQUEST_ANSWER: EventType.REQUEST_ANSWER,
                LearnerTurnKind.SELF_REPORTED_MASTERY: EventType.SELF_REPORTED_MASTERY,
            }[kind]
        )

    def _finish_assessor_failure(
        self,
        session_id: str,
        client_turn_id: str,
        error: LLMError | None,
        metadata: list[LLMCallMetadata],
    ) -> TutorSessionSnapshot:
        learner = self.learner_state.get_learner()
        payload = self._error_payload(error, source="assessor")
        with self.session_factory.begin() as db:
            session_record = self._require_record(db, session_id)
            turn = self._require_turn(db, session_id, client_turn_id)
            session_record.recoverable_error_json = payload
            turn.status = "recoverable_error"
            turn.recoverable_error_code = payload["code"]
            turn.recoverable_error_json = payload
            turn.updated_at = utc_now()
            self._persist_metadata(
                db, metadata, session_id=session_id, client_turn_id=client_turn_id
            )
            snapshot = self._snapshot(db, session_record, learner)
            turn.response_json = snapshot.model_dump(mode="json")
            return snapshot

    def _replayed_turn(self, session_id: str, client_turn_id: str) -> TutorSessionSnapshot | None:
        with self.session_factory() as db:
            self._require_record(db, session_id)
            record = TutorTurnRepository(db).get_by_client_id(session_id, client_turn_id)
            if record is None:
                return None
            if record.response_json is None:
                raise TutorSessionError(
                    SessionErrorCode.TURN_IN_PROGRESS,
                    "相同 client_turn_id 的请求仍在处理中",
                    status_code=409,
                )
            return TutorSessionSnapshot.model_validate(record.response_json)

    def _mark_reservation_failed(self, session_id: str, client_turn_id: str) -> None:
        with self.session_factory.begin() as db:
            record = TutorTurnRepository(db).get_by_client_id(session_id, client_turn_id)
            if record is not None:
                record.status = "conflict"
                record.updated_at = utc_now()

    def _snapshot(
        self, db: Session, record: LearningSession, learner: LearnerView
    ) -> TutorSessionSnapshot:
        messages = SessionMessageRepository(db).list_for_session(record.id)
        learner_nodes = [
            LearnerStateNodeSummary(
                node_id=node_id,
                learner_status=state.status,
                progress_status=state.progress_status,
            )
            for node_id, state in sorted(learner.node_states.items())
            if node_id in self.pilot_nodes
        ]
        next_ready = self._next_ready_node(db, record, learner)
        is_active = record.status == SessionStatus.ACTIVE.value
        has_question = record.expected_question_id is not None
        debug = self._debug_view(db, record, learner) if self._debug_enabled else None
        return TutorSessionSnapshot(
            session_id=record.id,
            version=record.version,
            status=SessionStatus(record.status),
            mode=EntryMode(record.entry_mode),
            target_node=self._node_view(record.target_node_id, learner),
            current_node=self._node_view(record.current_node_id, learner),
            return_stack=[self._node_view(item, learner) for item in record.return_stack_json],
            expected_question=self._question_view(record.expected_question_id),
            messages=[self._message_view(item) for item in messages],
            available_actions=AvailableActions(
                can_submit_answer=is_active and has_question,
                can_ask_side_question=is_active and has_question,
                can_request_hint=is_active and has_question,
                can_request_answer=is_active and has_question,
                can_report_mastery=is_active and has_question,
                can_abandon=is_active,
            ),
            learner_state_summary=learner_nodes,
            roadmap_delta=[
                RoadmapDeltaItem(node_id=item.node_id, learner_status=item.learner_status)
                for item in learner_nodes
            ],
            next_ready_node=next_ready,
            llm_mode=LLMMode(self.settings.llm_mode),
            recoverable_error=(
                RecoverableErrorView.model_validate(record.recoverable_error_json)
                if record.recoverable_error_json
                else None
            ),
            debug=debug,
        )

    def _debug_view(
        self, db: Session, record: LearningSession, learner: LearnerView
    ) -> SessionDebugView:
        turn = TutorTurnRepository(db).latest_for_session(record.id)
        traces = DecisionTraceRepository(db).list_for_session(record.id)
        trace = traces[-1] if traces else None
        metadata = (
            LLMCallRepository(db).list_for_turn(record.id, turn.client_turn_id)
            if turn is not None
            else []
        )
        active_ids = [
            item.misconception_id for item in learner.misconceptions if item.status == "active"
        ]
        resolved_ids = [
            item.misconception_id for item in learner.misconceptions if item.status == "resolved"
        ]
        final_action = Action(trace.final_action) if trace else None
        return SessionDebugView(
            session_id=record.id,
            session_version=record.version,
            client_turn_id=turn.client_turn_id if turn else None,
            target_node_id=record.target_node_id,
            current_node_id=record.current_node_id,
            expected_question_id=record.expected_question_id,
            current_assistance_level=record.current_assistance_level,
            canonical_assessment_summary=(turn.assessment_result_json if turn else None),
            final_action=final_action,
            reason_codes=list(trace.reason_codes_json) if trace else [],
            remediation_target=(
                trace.target_node_id if trace and final_action == Action.REMEDIATE else None
            ),
            return_stack=list(record.return_stack_json),
            state_delta=trace.state_delta_json if trace else None,
            state_before=trace.state_before_json if trace else None,
            active_misconception_ids=active_ids,
            resolved_misconception_ids=resolved_ids,
            decision_trace_id=trace.id if trace else None,
            llm_metadata=[self._safe_metadata(item) for item in metadata],
            llm_mode=LLMMode(self.settings.llm_mode),
            recoverable_error_code=turn.recoverable_error_code if turn else None,
            demo_inputs=(
                demo_inputs(record.expected_question_id) if self.settings.llm_mode == "mock" else []
            ),
        )

    def _next_ready_node(
        self, db: Session, record: LearningSession, learner: LearnerView
    ) -> SessionNodeView | None:
        if record.status != SessionStatus.COMPLETED.value:
            return None
        turn = TutorTurnRepository(db).latest_for_session(record.id)
        target = turn.decision_json.get("target_node_id") if turn and turn.decision_json else None
        if target and target != record.target_node_id:
            state = learner.node_states.get(target)
            if state is not None and state.status == "ready":
                return self._node_view(target, learner)
        return None

    def _node_view(self, node_id: str, learner: LearnerView) -> SessionNodeView:
        node = self.nodes[node_id]
        state = learner.node_states[node_id]
        return SessionNodeView(
            node_id=node.id,
            title=node.title,
            learner_status=state.status,
            progress_status=state.progress_status,
        )

    def _question_view(self, question_id: str | None) -> QuestionView | None:
        if question_id is None:
            return None
        assessment = self.assessments[question_id]
        if assessment.question_type not in {"single_choice", "free_text"}:
            raise TutorSessionError(
                SessionErrorCode.INVALID_TURN,
                f"V0.1 Question Renderer 不支持题型: {assessment.question_type}",
            )
        return QuestionView(
            question_id=assessment.id,
            node_id=assessment.node_id,
            prompt=assessment.prompt,
            response_type=(
                "single_choice" if assessment.question_type == "single_choice" else "free_text"
            ),
            options=[
                ChoiceOptionView(option_id=item.id, label=item.text) for item in assessment.options
            ],
        )

    @staticmethod
    def _message_view(record: SessionMessage) -> SessionMessageView:
        return SessionMessageView(
            message_id=record.id,
            sequence_number=record.sequence_number,
            role=MessageRole(record.role),
            message_kind=record.message_kind,
            text=record.text,
            question_id=record.question_id,
            interaction_type=record.interaction_type,
            client_turn_id=record.client_turn_id,
            created_at=record.created_at,
        )

    @staticmethod
    def _safe_metadata(record: LLMCallRecord) -> dict[str, Any]:
        return {
            "operation": record.operation,
            "mode": record.mode,
            "provider": record.provider,
            "model": record.model,
            "attempt_count": record.attempt_count,
            "latency_ms": record.latency_ms,
            "provider_request_id": record.provider_request_id,
            "success": record.success,
            "error_code": record.error_code,
            "token_usage": {
                "input": record.input_tokens,
                "output": record.output_tokens,
                "total": record.total_tokens,
            },
        }

    @property
    def _debug_enabled(self) -> bool:
        return (
            self.settings.app_env.casefold() == "development" and self.settings.enable_debug_panel
        )

    def _active_record(self) -> LearningSession | None:
        with self.session_factory() as db:
            return LearningSessionRepository(db).get_active_for_learner(DEFAULT_LEARNER_ID)

    @staticmethod
    def _require_record(db: Session, session_id: str) -> LearningSession:
        record = LearningSessionRepository(db).get(session_id)
        if record is None:
            raise TutorSessionError(
                SessionErrorCode.SESSION_NOT_FOUND,
                "学习会话不存在",
                status_code=404,
            )
        return record

    @staticmethod
    def _require_turn(db: Session, session_id: str, client_turn_id: str) -> TutorTurnRecord:
        record = TutorTurnRepository(db).get_by_client_id(session_id, client_turn_id)
        if record is None:
            raise TutorSessionError(
                SessionErrorCode.INVALID_TURN,
                "Turn 记录不存在",
            )
        return record

    @staticmethod
    def _add_message(
        db: Session,
        session_id: str,
        *,
        role: MessageRole,
        message_kind: str,
        text: str,
        question_id: str | None,
        interaction_type: str | None,
        client_turn_id: str | None,
    ) -> SessionMessage:
        repository = SessionMessageRepository(db)
        message = SessionMessage(
            id=f"message_{uuid4().hex}",
            session_id=session_id,
            sequence_number=repository.next_sequence(session_id),
            role=role.value,
            message_kind=message_kind,
            text=text,
            question_id=question_id,
            interaction_type=interaction_type,
            client_turn_id=client_turn_id,
            created_at=utc_now(),
        )
        repository.add(message)
        db.flush()
        return message

    @staticmethod
    def _persist_metadata(
        db: Session,
        metadata: list[LLMCallMetadata],
        *,
        session_id: str,
        client_turn_id: str,
    ) -> None:
        repository = LLMCallRepository(db)
        for item in metadata:
            repository.add(item, session_id=session_id, client_turn_id=client_turn_id)

    @staticmethod
    def _error_payload(
        error: LLMError | None,
        *,
        source: Literal["assessor", "teacher", "session"],
    ) -> dict[str, str]:
        if error is None:
            return {
                "code": "LLM_PROVIDER_UNAVAILABLE",
                "message": "模型服务暂时不可用",
                "source": source,
            }
        return {
            "code": error.code.value,
            "message": error.message,
            "source": source,
        }
