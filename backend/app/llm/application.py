from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from backend.app.learner.service import LearnerStateService
from backend.app.llm.builders import TeacherRequestBuilder
from backend.app.llm.contracts import (
    LearnerTurn,
    LearnerTurnKind,
    LLMCallMetadata,
    TutorTurnResult,
)
from backend.app.llm.repository import LLMCallRepository
from backend.app.llm.services import AssessorService, TeacherService
from backend.app.tutor.domain import EventType, TutorEvent
from backend.app.tutor.engine import TutorEngine


class TutorTurnService:
    def __init__(
        self,
        *,
        tutor_engine: TutorEngine,
        learner_state: LearnerStateService,
        assessor: AssessorService,
        teacher: TeacherService,
        teacher_builder: TeacherRequestBuilder,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.tutor_engine = tutor_engine
        self.learner_state = learner_state
        self.assessor = assessor
        self.teacher = teacher
        self.teacher_builder = teacher_builder
        self.session_factory = session_factory

    async def handle_turn(self, session_id: str, turn: LearnerTurn) -> TutorTurnResult:
        session = self.tutor_engine.get_session(session_id)
        raw_assessment = None
        assessment = None
        assessment_warnings: list[str] = []
        metadata: list[LLMCallMetadata] = []
        recoverable_error = None

        if turn.kind == LearnerTurnKind.ANSWER:
            assessor_result = await self.assessor.assess(session, turn.text)
            metadata.extend(assessor_result.metadata)
            raw_assessment = assessor_result.raw
            assessment = assessor_result.canonical
            assessment_warnings = assessor_result.warnings
            recoverable_error = assessor_result.error
            if assessment is None:
                engine_result = self.tutor_engine.handle_event(
                    session_id, TutorEvent(type=EventType.INVALID_ASSESSMENT)
                )
            else:
                engine_result = self.tutor_engine.handle_event(
                    session_id,
                    TutorEvent(type=EventType.ASSESSMENT, assessment=assessment),
                )
        else:
            event_type = {
                LearnerTurnKind.SIDE_QUESTION: EventType.SIDE_QUESTION,
                LearnerTurnKind.REQUEST_HINT: EventType.REQUEST_HINT,
                LearnerTurnKind.REQUEST_ANSWER: EventType.REQUEST_ANSWER,
                LearnerTurnKind.SELF_REPORTED_MASTERY: EventType.SELF_REPORTED_MASTERY,
            }[turn.kind]
            engine_result = self.tutor_engine.handle_event(session_id, TutorEvent(type=event_type))

        learner = self.learner_state.get_learner()
        teacher_request = self.teacher_builder.build(
            session=engine_result.session,
            decision=engine_result.decision,
            learner=learner,
            assessment=assessment,
        )
        if assessment is None and turn.kind == LearnerTurnKind.ANSWER:
            tutor_message = self.teacher.fallback_message(teacher_request)
        else:
            teacher_result = await self.teacher.compose(teacher_request)
            metadata.extend(teacher_result.metadata)
            tutor_message = teacher_result.message
            if teacher_result.error is not None:
                recoverable_error = teacher_result.error

        self._persist_metadata(metadata, session_id=session_id, client_turn_id=turn.client_turn_id)
        traces = self.tutor_engine.list_decision_traces(session_id)
        return TutorTurnResult(
            learner_turn=turn,
            raw_assessment=raw_assessment,
            validated_assessment=assessment,
            assessment_warnings=assessment_warnings,
            decision=engine_result.decision,
            tutor_message=tutor_message,
            learner_state_summary=learner.model_dump(mode="json"),
            recoverable_error=recoverable_error,
            llm_metadata=metadata,
            decision_trace_id=traces[-1].trace_id,
        )

    def _persist_metadata(
        self,
        items: list[LLMCallMetadata],
        *,
        session_id: str,
        client_turn_id: str,
    ) -> None:
        if not items:
            return
        with self.session_factory.begin() as db:
            repository = LLMCallRepository(db)
            for item in items:
                repository.add(
                    item,
                    session_id=session_id,
                    client_turn_id=client_turn_id,
                )
