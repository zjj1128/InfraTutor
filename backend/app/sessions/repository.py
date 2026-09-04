from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.sessions.models import SessionMessage, TutorTurnRecord


class TutorTurnRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, record: TutorTurnRecord) -> None:
        self.session.add(record)

    def get_by_client_id(self, session_id: str, client_turn_id: str) -> TutorTurnRecord | None:
        return self.session.scalar(
            select(TutorTurnRecord).where(
                TutorTurnRecord.session_id == session_id,
                TutorTurnRecord.client_turn_id == client_turn_id,
            )
        )

    def list_for_session(self, session_id: str) -> list[TutorTurnRecord]:
        return list(
            self.session.scalars(
                select(TutorTurnRecord)
                .where(TutorTurnRecord.session_id == session_id)
                .order_by(TutorTurnRecord.created_at, TutorTurnRecord.id)
            )
        )

    def latest_for_session(self, session_id: str) -> TutorTurnRecord | None:
        return self.session.scalar(
            select(TutorTurnRecord)
            .where(TutorTurnRecord.session_id == session_id)
            .order_by(TutorTurnRecord.created_at.desc(), TutorTurnRecord.id.desc())
        )


class SessionMessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, message: SessionMessage) -> None:
        self.session.add(message)

    def list_for_session(self, session_id: str) -> list[SessionMessage]:
        return list(
            self.session.scalars(
                select(SessionMessage)
                .where(SessionMessage.session_id == session_id)
                .order_by(SessionMessage.sequence_number, SessionMessage.id)
            )
        )

    def next_sequence(self, session_id: str) -> int:
        current = self.session.scalar(
            select(func.max(SessionMessage.sequence_number)).where(
                SessionMessage.session_id == session_id
            )
        )
        return int(current or 0) + 1
