from collections.abc import Mapping
from typing import Literal, Protocol

from pydantic import BaseModel

from backend.app.curriculum.graph import CourseGraph, CourseNode
from backend.app.curriculum.loader import CurriculumCatalog
from backend.app.curriculum.models import AccessStatus, LearnerStatus, ProgressStatus
from backend.app.sessions.schemas import ActiveSessionSummary


class LearnerNodeStateLike(Protocol):
    status: LearnerStatus
    progress_status: ProgressStatus
    access_status: AccessStatus


class NodeReference(BaseModel):
    id: str
    title: str


class RoadmapNodeView(BaseModel):
    id: str
    title: str
    summary: str
    type: str
    implementation_status: str
    availability: Literal["available", "supporting", "coming_later"]
    is_selectable: bool
    learner_status: LearnerStatus | None = None
    progress_status: ProgressStatus | None = None
    access_status: AccessStatus | None = None
    can_start_diagnostic_probe: bool = False
    active_session_id: str | None = None
    prerequisites: list[NodeReference]
    missing_prerequisites: list[NodeReference]
    recommended_next: list[NodeReference]
    learning_objectives: list[str]


class RoadmapStageView(BaseModel):
    id: str
    order: int
    title: str
    goal: str
    exit_capabilities: list[str]
    availability: Literal["in_progress", "coming_later"]
    nodes: list[RoadmapNodeView]


class RoadmapView(BaseModel):
    course_id: str
    title: str
    target_learner: str
    current_stage_id: str
    stage_count: int
    pilot_node_count: int
    learner_state_available: bool
    active_session: ActiveSessionSummary | None = None
    stages: list[RoadmapStageView]


def _availability(node: CourseNode) -> Literal["available", "supporting", "coming_later"]:
    if node.implementation_status == "pilot":
        return "available"
    if node.implementation_status == "supporting":
        return "supporting"
    return "coming_later"


class CurriculumService:
    def __init__(self, catalog: CurriculumCatalog) -> None:
        self.catalog = catalog
        self.graph = CourseGraph(catalog)

    def roadmap_view(
        self,
        learner_states: Mapping[str, LearnerNodeStateLike] | None = None,
        *,
        active_session: ActiveSessionSummary | None = None,
    ) -> RoadmapView:
        nodes_by_stage: dict[str, list[RoadmapNodeView]] = {
            stage.id: [] for stage in self.catalog.roadmap.stages
        }
        mastered_ids = {
            node_id
            for node_id, state in (learner_states or {}).items()
            if state.progress_status == "mastered"
        }

        for roadmap_node in self.catalog.roadmap.nodes:
            node = self.graph.get_node(roadmap_node.id)
            availability = _availability(node)
            learner_state = (learner_states or {}).get(node.id)
            can_probe = bool(
                learner_state
                and learner_state.access_status == "locked"
                and self.catalog.pilot.entry_policy.allow_target_diagnostic_probe
                and node.id in self.catalog.pilot.entry_policy.target_probe_questions
            )
            nodes_by_stage[node.stage_id].append(
                RoadmapNodeView(
                    id=node.id,
                    title=node.title,
                    summary=node.summary,
                    type=node.type,
                    implementation_status=node.implementation_status,
                    availability=availability,
                    is_selectable=availability == "available",
                    learner_status=learner_state.status if learner_state else None,
                    progress_status=learner_state.progress_status if learner_state else None,
                    access_status=learner_state.access_status if learner_state else None,
                    can_start_diagnostic_probe=can_probe,
                    active_session_id=(
                        active_session.session_id
                        if active_session and active_session.target_node_id == node.id
                        else None
                    ),
                    prerequisites=[
                        NodeReference(id=item.id, title=item.title)
                        for item in self.graph.direct_prerequisites(node.id)
                    ],
                    missing_prerequisites=[
                        NodeReference(id=item.id, title=item.title)
                        for item in self.graph.unmet_prerequisites(node.id, mastered_ids)
                    ]
                    if learner_states is not None
                    else [],
                    recommended_next=[
                        NodeReference(id=item.id, title=item.title)
                        for item in self.graph.recommended_next(node.id)
                    ],
                    learning_objectives=list(node.learning_objectives),
                )
            )

        stages = [
            RoadmapStageView(
                id=stage.id,
                order=stage.order,
                title=stage.title,
                goal=stage.goal,
                exit_capabilities=stage.exit_capabilities,
                availability=(
                    "in_progress"
                    if any(node.availability == "available" for node in nodes_by_stage[stage.id])
                    else "coming_later"
                ),
                nodes=nodes_by_stage[stage.id],
            )
            for stage in sorted(self.catalog.roadmap.stages, key=lambda item: item.order)
        ]

        return RoadmapView(
            course_id=self.catalog.roadmap.course_id,
            title=self.catalog.roadmap.title,
            target_learner=self.catalog.roadmap.target_learner,
            current_stage_id=self.catalog.pilot.stage_id,
            stage_count=len(stages),
            pilot_node_count=len(self.catalog.pilot.nodes),
            learner_state_available=learner_states is not None,
            active_session=active_session,
            stages=stages,
        )
