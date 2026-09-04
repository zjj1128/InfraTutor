from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from backend.app.curriculum.graph import CourseGraph
from backend.app.curriculum.loader import CurriculumCatalog
from backend.app.curriculum.models import (
    AccessStatus,
    Assessment,
    LearnerStatus,
    MisconceptionDefinition,
    ProgressStatus,
)
from backend.app.learner.mastery import (
    calculate_confidence,
    derive_progress_status,
    effective_evidence_weight,
    evaluate_mastery_gate,
    update_mastery,
)
from backend.app.learner.models import Evidence, Learner, LearnerMisconception, LearnerNodeState
from backend.app.learner.repository import (
    EvidenceRepository,
    LearnerRepository,
    MisconceptionRepository,
)
from backend.app.learner.schemas import (
    EvidenceInput,
    LearnerMisconceptionView,
    LearnerNodeStateView,
    LearnerProfileView,
    LearnerView,
    MisconceptionStatus,
    SeedName,
)

DEFAULT_LEARNER_ID = "default_learner"


class LearnerStateError(ValueError):
    pass


class LearnerStateService:
    def __init__(
        self,
        catalog: CurriculumCatalog,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.catalog = catalog
        self.graph = CourseGraph(catalog)
        self.session_factory = session_factory
        self.assessments: dict[str, Assessment] = {
            item.id: item for item in catalog.assessment_set.assessments
        }
        self.misconceptions: dict[str, MisconceptionDefinition] = {
            item.id: item for item in catalog.pilot.misconceptions
        }
        self.pilot_nodes = {item.id: item for item in catalog.pilot.nodes}

    def ensure_default_learner(self) -> None:
        with self.session_factory.begin() as session:
            repository = LearnerRepository(session)
            if repository.get(DEFAULT_LEARNER_ID) is None:
                self._create_seeded_learner(session, "clean")
            else:
                # Phase 2 stored UI-ready as progress. Normalize existing local databases in place.
                for state in repository.list_node_states(DEFAULT_LEARNER_ID):
                    if state.progress_status == "ready":
                        state.progress_status = "no_evidence"
                learner = repository.get(DEFAULT_LEARNER_ID)
                data_path = repository.get_node_state(DEFAULT_LEARNER_ID, "rdma_data_path")
                if (
                    learner is not None
                    and learner.active_seed == "golden_path"
                    and data_path is not None
                    and data_path.attempts == 0
                    and data_path.progress_status == "partial"
                    and data_path.mastery_score == 0.64
                    and data_path.confidence_score == 0.52
                ):
                    data_path.progress_status = "mastered"
                    data_path.mastery_score = 0.86
                    data_path.confidence_score = 0.74
                    data_path.evidence_weight = 2.22
                    data_path.ever_mastered = True
                self._refresh_effective_statuses(session)

    def reset(self, seed: SeedName) -> LearnerView:
        with self.session_factory.begin() as session:
            repository = LearnerRepository(session)
            repository.clear_for_reset(DEFAULT_LEARNER_ID)
            self._create_seeded_learner(session, seed)
        return self.get_learner()

    def get_learner(self) -> LearnerView:
        with self.session_factory.begin() as session:
            learner_repository = LearnerRepository(session)
            evidence_repository = EvidenceRepository(session)
            misconception_repository = MisconceptionRepository(session)
            learner = learner_repository.get(DEFAULT_LEARNER_ID)
            if learner is None:
                raise LearnerStateError("default learner 尚未初始化")

            self._refresh_effective_statuses(session)
            states = learner_repository.list_node_states(DEFAULT_LEARNER_ID)
            evidence = evidence_repository.list_for_learner(DEFAULT_LEARNER_ID)
            evidence_ids_by_node: dict[str, list[str]] = {}
            for item in evidence:
                evidence_ids_by_node.setdefault(item.node_id, []).append(item.id)

            return LearnerView(
                learner_id=learner.id,
                profile=LearnerProfileView(
                    display_name=learner.display_name,
                    target_role=learner.target_role,
                    teaching_preferences=list(learner.teaching_preferences_json),
                ),
                node_states={
                    state.node_id: LearnerNodeStateView(
                        status=cast(LearnerStatus, state.status),
                        progress_status=cast(ProgressStatus, state.progress_status),
                        access_status=cast(
                            AccessStatus, "locked" if state.status == "locked" else "available"
                        ),
                        mastery_score=state.mastery_score,
                        confidence_score=state.confidence_score,
                        evidence_weight=state.evidence_weight,
                        attempts=state.attempts,
                        evidence_ids=evidence_ids_by_node.get(state.node_id, []),
                        last_seen_at=self._as_utc(state.last_seen_at),
                        last_tested_at=self._as_utc(state.last_tested_at),
                        review_due_at=self._as_utc(state.review_due_at),
                    )
                    for state in states
                },
                misconceptions=[
                    LearnerMisconceptionView(
                        misconception_id=item.misconception_id,
                        node_id=item.node_id,
                        status=cast(MisconceptionStatus, item.status),
                        evidence_ids=list(item.evidence_ids_json),
                        first_seen_at=self._as_utc(item.first_seen_at),
                        last_seen_at=self._as_utc(item.last_seen_at),
                        resolved_at=self._as_utc(item.resolved_at),
                    )
                    for item in misconception_repository.list_for_learner(DEFAULT_LEARNER_ID)
                ],
            )

    def status_map(self) -> dict[str, LearnerStatus]:
        return {node_id: state.status for node_id, state in self.get_learner().node_states.items()}

    def roadmap_state_map(self) -> dict[str, LearnerNodeStateView]:
        return self.get_learner().node_states

    def record_evidence(
        self, evidence_input: EvidenceInput, *, weight_multiplier: float = 1.0
    ) -> Evidence:
        self._validate_evidence_input(evidence_input)
        with self.session_factory.begin() as session:
            return self.record_evidence_in_session(
                session, evidence_input, weight_multiplier=weight_multiplier
            )

    def record_evidence_in_session(
        self,
        session: Session,
        evidence_input: EvidenceInput,
        *,
        weight_multiplier: float = 1.0,
    ) -> Evidence:
        self._validate_evidence_input(evidence_input)
        if not 0 < weight_multiplier <= 1:
            raise LearnerStateError("Evidence weight multiplier 必须在 (0, 1] 内")

        learner_repository = LearnerRepository(session)
        evidence_repository = EvidenceRepository(session)
        state = learner_repository.get_node_state(DEFAULT_LEARNER_ID, evidence_input.node_id)
        if state is None:
            raise LearnerStateError(f"学习者缺少节点状态: {evidence_input.node_id}")

        weight = round(
            effective_evidence_weight(evidence_input.evidence_type, evidence_input.assistance_level)
            * weight_multiplier,
            6,
        )
        state.mastery_score = update_mastery(
            state.mastery_score,
            state.evidence_weight,
            evidence_input.score,
            weight,
        )
        state.evidence_weight = round(state.evidence_weight + weight, 6)
        state.attempts += 1
        state.last_seen_at = datetime.now(UTC)
        state.last_tested_at = state.last_seen_at

        evidence = Evidence(
            id=f"evidence_{uuid4().hex}",
            learner_id=DEFAULT_LEARNER_ID,
            session_id=evidence_input.session_id,
            node_id=evidence_input.node_id,
            question_id=evidence_input.question_id,
            evidence_type=evidence_input.evidence_type,
            score=evidence_input.score,
            weight=weight,
            assistance_level=evidence_input.assistance_level,
            rubric_results_json=[item.model_dump() for item in evidence_input.rubric_results],
            misconception_ids_json=list(evidence_input.misconception_ids),
        )
        evidence_repository.add(evidence)
        session.flush()

        affected_node_ids = {state.node_id}
        for misconception_id in evidence_input.misconception_ids:
            self._mark_misconception(session, misconception_id, evidence.id, explicit=True)
            affected_node_ids.add(self._misconception_definition(misconception_id).node_id)

        for affected_node_id in affected_node_ids:
            affected_state = learner_repository.get_node_state(DEFAULT_LEARNER_ID, affected_node_id)
            if affected_state is not None:
                self._recalculate_node_progress(
                    session,
                    affected_state,
                    latest_evidence=evidence if affected_node_id == state.node_id else None,
                )
        self._refresh_effective_statuses(session)
        session.flush()
        return evidence

    def mark_misconception(self, misconception_id: str, evidence_id: str, *, explicit: bool) -> str:
        with self.session_factory.begin() as session:
            status = self._mark_misconception(
                session, misconception_id, evidence_id, explicit=explicit
            )
            definition = self._misconception_definition(misconception_id)
            state = LearnerRepository(session).get_node_state(
                DEFAULT_LEARNER_ID, definition.node_id
            )
            if state is not None:
                self._recalculate_node_progress(session, state)
                self._refresh_effective_statuses(session)
            return status

    def try_resolve_misconception(self, misconception_id: str, evidence_id: str) -> bool:
        with self.session_factory.begin() as session:
            return self.try_resolve_misconception_in_session(session, misconception_id, evidence_id)

    def try_resolve_misconception_in_session(
        self, session: Session, misconception_id: str, evidence_id: str
    ) -> bool:
        definition = self._misconception_definition(misconception_id)
        misconception_repository = MisconceptionRepository(session)
        evidence = EvidenceRepository(session).get(evidence_id)
        misconception = misconception_repository.get(DEFAULT_LEARNER_ID, misconception_id)
        if evidence is None or evidence.learner_id != DEFAULT_LEARNER_ID:
            raise LearnerStateError(f"未知 Evidence: {evidence_id}")
        if misconception is None:
            return False

        assessment = self.assessments[evidence.question_id]
        required_ids = {item.id for item in assessment.rubric.criteria if item.required_for_mastery}
        result_by_id = {
            item["criterion_id"]: item["result"] for item in evidence.rubric_results_json
        }
        proves_replacement = (
            evidence.assistance_level == "none"
            and assessment.question_type == "free_text"
            and evidence.score >= 0.8
            and misconception_id not in evidence.misconception_ids_json
            and bool(required_ids)
            and all(result_by_id.get(item) == "met" for item in required_ids)
        )
        if not proves_replacement:
            return False

        now = datetime.now(UTC)
        misconception.status = "resolved"
        misconception.last_seen_at = now
        misconception.resolved_at = now
        misconception.evidence_ids_json = [*misconception.evidence_ids_json, evidence.id]

        state = LearnerRepository(session).get_node_state(DEFAULT_LEARNER_ID, definition.node_id)
        if state is not None:
            self._recalculate_node_progress(session, state)
            self._refresh_effective_statuses(session)
        return True

    def _create_seeded_learner(self, session: Session, seed_name: SeedName) -> None:
        repository = LearnerRepository(session)
        learner = Learner(
            id=DEFAULT_LEARNER_ID,
            display_name="本地学习者",
            target_role="高速互联软件工程师",
            background_assumptions_json=["计算机专业基础"],
            teaching_preferences_json=["中文优先", "prefer_system_data_flow"],
            active_seed=seed_name,
        )
        repository.add(learner)
        session.flush()

        seed = getattr(self.catalog.pilot.seeds, seed_name)
        assumed_node_ids: set[str] = set()
        for assumption in self.catalog.pilot.supporting_assumptions:
            assumed_node_ids.add(assumption.node_id)
            assumed_node_ids.update(
                item.id for item in self.graph.prerequisite_closure(assumption.node_id)
            )

        for roadmap_node in self.catalog.roadmap.nodes:
            explicit = seed.node_states.get(roadmap_node.id)
            if roadmap_node.id in assumed_node_ids:
                progress_status = "mastered"
                mastery_score = 0.9
                confidence_score = 0.8
                evidence_weight = 2.4
                is_assumption = True
            elif explicit is not None:
                progress_status = (
                    "no_evidence" if explicit.status in {"locked", "ready"} else explicit.status
                )
                mastery_score = explicit.mastery_score
                confidence_score = explicit.confidence_score
                evidence_weight = round(explicit.confidence_score * 3.0, 6)
                is_assumption = False
            else:
                progress_status = "no_evidence"
                mastery_score = 0.0
                confidence_score = 0.0
                evidence_weight = 0.0
                is_assumption = False

            repository.add_node_state(
                LearnerNodeState(
                    learner_id=DEFAULT_LEARNER_ID,
                    node_id=roadmap_node.id,
                    status=progress_status,
                    progress_status=progress_status,
                    mastery_score=mastery_score,
                    confidence_score=confidence_score,
                    evidence_weight=evidence_weight,
                    attempts=0,
                    ever_mastered=progress_status == "mastered",
                    is_seeded_assumption=is_assumption,
                )
            )
        session.flush()
        self._refresh_effective_statuses(session)

    def _validate_evidence_input(self, item: EvidenceInput) -> Assessment:
        assessment = self.assessments.get(item.question_id)
        if assessment is None:
            raise LearnerStateError(f"未知 assessment: {item.question_id}")
        if assessment.node_id != item.node_id:
            raise LearnerStateError(
                f"assessment {item.question_id} 属于 {assessment.node_id}，不属于 {item.node_id}"
            )
        if assessment.evidence_type != item.evidence_type:
            raise LearnerStateError(f"Evidence type mismatch: 课程要求 {assessment.evidence_type}")

        allowed_criteria = {criterion.id for criterion in assessment.rubric.criteria}
        criterion_ids = [result.criterion_id for result in item.rubric_results]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise LearnerStateError("rubric_results 包含重复 criterion_id")
        unknown_criteria = set(criterion_ids) - allowed_criteria
        if unknown_criteria:
            raise LearnerStateError(
                f"rubric_results 包含未知 criterion: {sorted(unknown_criteria)}"
            )

        allowed_misconceptions = set(assessment.rubric.critical_misconception_ids)
        unknown_misconceptions = set(item.misconception_ids) - allowed_misconceptions
        if unknown_misconceptions:
            raise LearnerStateError(
                f"Evidence 包含本题不允许的 misconception: {sorted(unknown_misconceptions)}"
            )
        return assessment

    def _mark_misconception(
        self,
        session: Session,
        misconception_id: str,
        evidence_id: str,
        *,
        explicit: bool,
    ) -> str:
        definition = self._misconception_definition(misconception_id)
        evidence = EvidenceRepository(session).get(evidence_id)
        if evidence is None or evidence.learner_id != DEFAULT_LEARNER_ID:
            raise LearnerStateError(f"未知 Evidence: {evidence_id}")

        repository = MisconceptionRepository(session)
        item = repository.get(DEFAULT_LEARNER_ID, misconception_id)
        now = datetime.now(UTC)
        if item is None:
            item = LearnerMisconception(
                learner_id=DEFAULT_LEARNER_ID,
                misconception_id=misconception_id,
                node_id=definition.node_id,
                status="active" if explicit else "suspected",
                evidence_ids_json=[evidence_id],
                first_seen_at=now,
                last_seen_at=now,
            )
            repository.add(item)
        else:
            prior_ids = set(item.evidence_ids_json)
            item.evidence_ids_json = list(dict.fromkeys([*item.evidence_ids_json, evidence_id]))
            item.last_seen_at = now
            item.resolved_at = None
            if explicit or evidence_id not in prior_ids:
                item.status = "active"
        return item.status

    def _recalculate_node_progress(
        self,
        session: Session,
        state: LearnerNodeState,
        latest_evidence: Evidence | None = None,
    ) -> None:
        evidence = EvidenceRepository(session).list_for_node(DEFAULT_LEARNER_ID, state.node_id)
        relevant_misconceptions = MisconceptionRepository(session).list_for_node(
            DEFAULT_LEARNER_ID, state.node_id
        )
        critical_ids = {item.id for item in self.catalog.pilot.misconceptions if item.critical}
        has_active_critical = any(
            item.status == "active" and item.misconception_id in critical_ids
            for item in relevant_misconceptions
        )
        state.confidence_score = calculate_confidence(state.evidence_weight, has_active_critical)
        if state.node_id in self.pilot_nodes:
            requirements = self.pilot_nodes[state.node_id].mastery_requirements
        else:
            requirements = self.catalog.pilot.default_mastery_requirements
        gate = evaluate_mastery_gate(
            mastery_score=state.mastery_score,
            confidence_score=state.confidence_score,
            evidence=evidence,
            assessments=self.assessments,
            requirements=requirements,
            has_active_critical=has_active_critical,
        )
        state.progress_status = derive_progress_status(
            mastery_score=state.mastery_score,
            evidence_weight=state.evidence_weight,
            ever_mastered=state.ever_mastered,
            current_progress_status=state.progress_status,
            latest_evidence=latest_evidence or (evidence[-1] if evidence else None),
            gate=gate,
            has_active_critical=has_active_critical,
        )
        if state.progress_status == "mastered":
            state.ever_mastered = True

    def _refresh_effective_statuses(self, session: Session) -> None:
        states = LearnerRepository(session).list_node_states(DEFAULT_LEARNER_ID)
        mastered_ids = {state.node_id for state in states if state.progress_status == "mastered"}
        now = datetime.now(UTC)
        for state in states:
            if (
                state.ever_mastered
                and state.review_due_at is not None
                and self._as_utc(state.review_due_at) <= now
            ):
                state.progress_status = "review_needed"

            if not state.is_seeded_assumption and self.graph.unmet_prerequisites(
                state.node_id, mastered_ids
            ):
                state.status = "locked"
            else:
                state.status = (
                    "ready" if state.progress_status == "no_evidence" else state.progress_status
                )

    def _misconception_definition(self, misconception_id: str) -> MisconceptionDefinition:
        try:
            return self.misconceptions[misconception_id]
        except KeyError as exc:
            raise LearnerStateError(f"未知 misconception: {misconception_id}") from exc

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
