from pathlib import Path

import pytest

from backend.app.curriculum.graph import CourseGraph, CourseNodeNotFoundError
from backend.app.curriculum.loader import load_curriculum


@pytest.fixture
def graph(curriculum_copy: Path) -> CourseGraph:
    return CourseGraph(load_curriculum(curriculum_copy))


@pytest.mark.parametrize("missing_node_id", ["device_dma", "pinned_memory"])
def test_memory_registration_requires_full_prerequisite_closure(
    graph: CourseGraph, missing_node_id: str
) -> None:
    mastered = set(graph.node_ids)
    mastered.remove(missing_node_id)

    assert not graph.is_unlocked("memory_registration", mastered)
    assert missing_node_id in {
        node.id for node in graph.unmet_prerequisites("memory_registration", mastered)
    }


def test_lkey_rkey_unlocks_only_after_memory_registration(graph: CourseGraph) -> None:
    mastered = {node.id for node in graph.prerequisite_closure("lkey_rkey_concept")}
    mastered.remove("memory_registration")

    assert not graph.is_unlocked("lkey_rkey_concept", mastered)
    assert graph.is_unlocked("lkey_rkey_concept", {*mastered, "memory_registration"})


def test_pilot_recommended_next_overrides_empty_roadmap_hint(graph: CourseGraph) -> None:
    assert [node.id for node in graph.recommended_next("memory_registration")] == [
        "lkey_rkey_concept"
    ]


def test_unknown_node_has_actionable_error(graph: CourseGraph) -> None:
    with pytest.raises(CourseNodeNotFoundError, match="未知课程节点: not_in_course"):
        graph.get_node("not_in_course")
