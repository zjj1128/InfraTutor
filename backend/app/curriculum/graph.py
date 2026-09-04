from dataclasses import dataclass

from backend.app.curriculum.loader import CurriculumCatalog
from backend.app.curriculum.models import ImplementationStatus, NodeType


@dataclass(frozen=True)
class CourseNode:
    id: str
    stage_id: str
    title: str
    summary: str
    type: NodeType
    prerequisites: tuple[str, ...]
    recommended_next: tuple[str, ...]
    reinforces: tuple[str, ...]
    implementation_status: ImplementationStatus
    learning_objectives: tuple[str, ...] = ()


class CourseNodeNotFoundError(KeyError):
    pass


class CourseGraph:
    def __init__(self, catalog: CurriculumCatalog) -> None:
        pilot_nodes = {node.id: node for node in catalog.pilot.nodes}
        self._nodes: dict[str, CourseNode] = {}

        for roadmap_node in catalog.roadmap.nodes:
            pilot_node = pilot_nodes.get(roadmap_node.id)
            self._nodes[roadmap_node.id] = CourseNode(
                id=roadmap_node.id,
                stage_id=roadmap_node.stage_id,
                title=pilot_node.title if pilot_node else roadmap_node.title,
                summary=roadmap_node.summary,
                type=roadmap_node.type,
                prerequisites=tuple(
                    pilot_node.prerequisites if pilot_node else roadmap_node.prerequisites
                ),
                recommended_next=tuple(
                    pilot_node.recommended_next if pilot_node else roadmap_node.recommended_next
                ),
                reinforces=tuple(roadmap_node.reinforces),
                implementation_status=roadmap_node.implementation_status,
                learning_objectives=tuple(pilot_node.learning_objectives if pilot_node else ()),
            )

    @property
    def node_ids(self) -> frozenset[str]:
        return frozenset(self._nodes)

    def get_node(self, node_id: str) -> CourseNode:
        try:
            return self._nodes[node_id]
        except KeyError as exc:
            raise CourseNodeNotFoundError(f"未知课程节点: {node_id}") from exc

    def direct_prerequisites(self, node_id: str) -> tuple[CourseNode, ...]:
        node = self.get_node(node_id)
        return tuple(self.get_node(item) for item in node.prerequisites)

    def prerequisite_closure(self, node_id: str) -> tuple[CourseNode, ...]:
        self.get_node(node_id)
        queue = list(self._nodes[node_id].prerequisites)
        visited: set[str] = set()
        result: list[CourseNode] = []

        while queue:
            prerequisite_id = queue.pop(0)
            if prerequisite_id in visited:
                continue
            visited.add(prerequisite_id)
            prerequisite = self.get_node(prerequisite_id)
            result.append(prerequisite)
            queue.extend(prerequisite.prerequisites)
        return tuple(result)

    def unmet_prerequisites(
        self, node_id: str, mastered_node_ids: set[str] | frozenset[str]
    ) -> tuple[CourseNode, ...]:
        return tuple(
            node for node in self.prerequisite_closure(node_id) if node.id not in mastered_node_ids
        )

    def is_unlocked(self, node_id: str, mastered_node_ids: set[str] | frozenset[str]) -> bool:
        return not self.unmet_prerequisites(node_id, mastered_node_ids)

    def recommended_next(self, node_id: str) -> tuple[CourseNode, ...]:
        node = self.get_node(node_id)
        return tuple(self.get_node(item) for item in node.recommended_next)
