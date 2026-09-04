from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.app.curriculum.graph import CourseGraph
from backend.app.curriculum.loader import CurriculumCatalog
from backend.app.curriculum.models import MisconceptionDefinition
from backend.app.learner.models import LearnerNodeState
from backend.app.tutor.domain import Action, CandidateAction, ReasonCode


@dataclass(frozen=True)
class RemediationSelection:
    selected_node_id: str | None
    candidates: list[CandidateAction]


class RemediationSelector:
    def __init__(self, catalog: CurriculumCatalog) -> None:
        self.graph = CourseGraph(catalog)
        self.misconceptions: dict[str, MisconceptionDefinition] = {
            item.id: item for item in catalog.pilot.misconceptions
        }

    def select(
        self,
        *,
        target_node_id: str,
        current_node_id: str,
        states: Mapping[str, LearnerNodeState],
        critical_misconception_ids: Sequence[str] = (),
        missing_concept_ids: Sequence[str] = (),
        restrict_to: set[str] | None = None,
        include_prerequisite_closure: bool = True,
    ) -> RemediationSelection:
        ranked: dict[str, tuple[tuple[int, int, int, int, int], list[ReasonCode]]] = {}

        for misconception_order, misconception_id in enumerate(critical_misconception_ids):
            definition = self.misconceptions.get(misconception_id)
            if definition is None:
                continue
            for remediation_order, node_id in enumerate(definition.remediation_nodes):
                self._consider(
                    ranked,
                    node_id,
                    states,
                    rank=(
                        0,
                        misconception_order * 100 + remediation_order,
                        self._distance(target_node_id, node_id),
                        self._state_rank(states.get(node_id)),
                        self._confidence_rank(states.get(node_id)),
                    ),
                    reasons=[
                        ReasonCode.CRITICAL_MISCONCEPTION_DETECTED,
                        ReasonCode.WEAK_PREREQUISITE,
                    ],
                    restrict_to=restrict_to,
                )

        for order, node_id in enumerate(missing_concept_ids):
            self._consider(
                ranked,
                node_id,
                states,
                rank=(
                    1,
                    order,
                    self._distance(target_node_id, node_id),
                    self._state_rank(states.get(node_id)),
                    self._confidence_rank(states.get(node_id)),
                ),
                reasons=[ReasonCode.WEAK_PREREQUISITE],
                restrict_to=restrict_to,
            )

        if include_prerequisite_closure:
            closure_ids = list(
                dict.fromkeys(
                    [
                        *(item.id for item in self.graph.prerequisite_closure(target_node_id)),
                        *(item.id for item in self.graph.prerequisite_closure(current_node_id)),
                    ]
                )
            )
            for order, node_id in enumerate(closure_ids):
                self._consider(
                    ranked,
                    node_id,
                    states,
                    rank=(
                        2,
                        order,
                        min(
                            self._distance(target_node_id, node_id),
                            self._distance(current_node_id, node_id),
                        ),
                        self._state_rank(states.get(node_id)),
                        self._confidence_rank(states.get(node_id)),
                    ),
                    reasons=[ReasonCode.WEAK_PREREQUISITE],
                    restrict_to=restrict_to,
                )

        candidates = [
            CandidateAction(
                action=Action.REMEDIATE,
                target_node_id=node_id,
                reason_codes=reasons,
                rank=list(rank),
            )
            for node_id, (rank, reasons) in sorted(
                ranked.items(), key=lambda item: (item[1][0], item[0])
            )
        ]
        return RemediationSelection(
            selected_node_id=candidates[0].target_node_id if candidates else None,
            candidates=candidates,
        )

    def _consider(
        self,
        ranked: dict[str, tuple[tuple[int, int, int, int, int], list[ReasonCode]]],
        node_id: str,
        states: Mapping[str, LearnerNodeState],
        *,
        rank: tuple[int, int, int, int, int],
        reasons: list[ReasonCode],
        restrict_to: set[str] | None,
    ) -> None:
        state = states.get(node_id)
        if (
            state is None
            or state.progress_status == "mastered"
            or (restrict_to is not None and node_id not in restrict_to)
        ):
            return
        previous = ranked.get(node_id)
        if previous is None or rank < previous[0]:
            ranked[node_id] = (rank, reasons)

    def _distance(self, source_node_id: str, target_node_id: str) -> int:
        if source_node_id == target_node_id:
            return 0
        queue: deque[tuple[str, int]] = deque([(source_node_id, 0)])
        visited = {source_node_id}
        while queue:
            node_id, distance = queue.popleft()
            for prerequisite in self.graph.direct_prerequisites(node_id):
                if prerequisite.id == target_node_id:
                    return distance + 1
                if prerequisite.id not in visited:
                    visited.add(prerequisite.id)
                    queue.append((prerequisite.id, distance + 1))
        return 999

    @staticmethod
    def _state_rank(state: LearnerNodeState | None) -> int:
        if state is None:
            return 99
        return {
            "review_needed": 0,
            "learning": 1,
            "no_evidence": 2,
            "partial": 3,
            "mastered": 9,
        }.get(state.progress_status, 8)

    @staticmethod
    def _confidence_rank(state: LearnerNodeState | None) -> int:
        return 1000 if state is None else round(state.confidence_score * 1000)
