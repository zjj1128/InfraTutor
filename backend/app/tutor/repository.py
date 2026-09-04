from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.tutor.models import DecisionTraceRecord, LearningSession


class LearningSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, learning_session: LearningSession) -> None:
        self.session.add(learning_session)

    def get(self, session_id: str) -> LearningSession | None:
        return self.session.get(LearningSession, session_id)

    def list_for_learner(self, learner_id: str) -> list[LearningSession]:
        statement = (
            select(LearningSession)
            .where(LearningSession.learner_id == learner_id)
            .order_by(LearningSession.created_at, LearningSession.id)
        )
        return list(self.session.scalars(statement))


class DecisionTraceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, trace: DecisionTraceRecord) -> None:
        self.session.add(trace)

    def get(self, trace_id: str) -> DecisionTraceRecord | None:
        return self.session.get(DecisionTraceRecord, trace_id)

    def list_for_session(self, session_id: str) -> list[DecisionTraceRecord]:
        statement = (
            select(DecisionTraceRecord)
            .where(DecisionTraceRecord.session_id == session_id)
            .order_by(DecisionTraceRecord.created_at, DecisionTraceRecord.id)
        )
        return list(self.session.scalars(statement))
