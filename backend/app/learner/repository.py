from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.learner.models import (
    Evidence,
    Learner,
    LearnerMisconception,
    LearnerNodeState,
)


class LearnerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, learner_id: str) -> Learner | None:
        return self.session.get(Learner, learner_id)

    def add(self, learner: Learner) -> None:
        self.session.add(learner)

    def get_node_state(self, learner_id: str, node_id: str) -> LearnerNodeState | None:
        return self.session.get(LearnerNodeState, (learner_id, node_id))

    def list_node_states(self, learner_id: str) -> list[LearnerNodeState]:
        statement = (
            select(LearnerNodeState)
            .where(LearnerNodeState.learner_id == learner_id)
            .order_by(LearnerNodeState.node_id)
        )
        return list(self.session.scalars(statement))

    def add_node_state(self, state: LearnerNodeState) -> None:
        self.session.add(state)

    def clear_for_reset(self, learner_id: str) -> None:
        # Bulk deletes intentionally bypass Evidence's normal immutability hooks.
        self.session.execute(delete(Evidence).where(Evidence.learner_id == learner_id))
        self.session.execute(
            delete(LearnerMisconception).where(LearnerMisconception.learner_id == learner_id)
        )
        self.session.execute(
            delete(LearnerNodeState).where(LearnerNodeState.learner_id == learner_id)
        )
        self.session.execute(delete(Learner).where(Learner.id == learner_id))


class EvidenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, evidence: Evidence) -> None:
        self.session.add(evidence)

    def get(self, evidence_id: str) -> Evidence | None:
        return self.session.get(Evidence, evidence_id)

    def list_for_node(self, learner_id: str, node_id: str) -> list[Evidence]:
        statement = (
            select(Evidence)
            .where(Evidence.learner_id == learner_id, Evidence.node_id == node_id)
            .order_by(Evidence.created_at, Evidence.id)
        )
        return list(self.session.scalars(statement))

    def list_for_learner(self, learner_id: str) -> list[Evidence]:
        statement = (
            select(Evidence)
            .where(Evidence.learner_id == learner_id)
            .order_by(Evidence.created_at, Evidence.id)
        )
        return list(self.session.scalars(statement))


class MisconceptionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, learner_id: str, misconception_id: str) -> LearnerMisconception | None:
        return self.session.get(LearnerMisconception, (learner_id, misconception_id))

    def add(self, misconception: LearnerMisconception) -> None:
        self.session.add(misconception)

    def list_for_learner(self, learner_id: str) -> list[LearnerMisconception]:
        statement = (
            select(LearnerMisconception)
            .where(LearnerMisconception.learner_id == learner_id)
            .order_by(LearnerMisconception.first_seen_at, LearnerMisconception.misconception_id)
        )
        return list(self.session.scalars(statement))

    def list_for_node(self, learner_id: str, node_id: str) -> list[LearnerMisconception]:
        statement = select(LearnerMisconception).where(
            LearnerMisconception.learner_id == learner_id,
            LearnerMisconception.node_id == node_id,
        )
        return list(self.session.scalars(statement))
