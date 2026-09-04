from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from backend.app.curriculum.loader import load_curriculum
from backend.app.curriculum.validator import CurriculumValidationError


def _mutate_yaml(path: Path, mutate: Callable[[dict[str, object]], None]) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_repository_curriculum_is_valid(curriculum_copy: Path) -> None:
    catalog = load_curriculum(curriculum_copy)

    assert len(catalog.roadmap.stages) == 9
    assert len(catalog.pilot.nodes) == 8
    assert len(catalog.assessment_set.assessments) == 20


def test_duplicate_node_id_is_rejected(curriculum_copy: Path) -> None:
    def duplicate_first_node(data: dict[str, object]) -> None:
        nodes = data["nodes"]
        assert isinstance(nodes, list)
        nodes.append(nodes[0].copy())

    _mutate_yaml(curriculum_copy / "roadmap.yaml", duplicate_first_node)

    with pytest.raises(CurriculumValidationError, match="重复的node ID"):
        load_curriculum(curriculum_copy)


def test_unknown_prerequisite_is_rejected(curriculum_copy: Path) -> None:
    def add_unknown_prerequisite(data: dict[str, object]) -> None:
        nodes = data["nodes"]
        assert isinstance(nodes, list)
        nodes[0]["prerequisites"] = ["missing_foundation"]

    _mutate_yaml(curriculum_copy / "roadmap.yaml", add_unknown_prerequisite)

    with pytest.raises(CurriculumValidationError, match="未知 prerequisite: missing_foundation"):
        load_curriculum(curriculum_copy)


def test_prerequisite_cycle_is_rejected_with_path(curriculum_copy: Path) -> None:
    def create_cycle(data: dict[str, object]) -> None:
        nodes = data["nodes"]
        assert isinstance(nodes, list)
        nodes[0]["prerequisites"] = [nodes[1]["id"]]
        nodes[1]["prerequisites"] = [nodes[0]["id"]]

    _mutate_yaml(curriculum_copy / "roadmap.yaml", create_cycle)

    with pytest.raises(CurriculumValidationError, match=r"prerequisite 存在环: .* -> .*"):
        load_curriculum(curriculum_copy)


@pytest.mark.parametrize(
    ("filename", "mutate", "message"),
    [
        (
            "roadmap.yaml",
            lambda data: data["nodes"][0].update(stage_id="missing_stage"),
            "未知 stage: missing_stage",
        ),
        (
            "v0_1_rdma_memory_registration.yaml",
            lambda data: data["nodes"][0]["assessment_ids"].append("missing_question"),
            "未知 assessment: missing_question",
        ),
        (
            "v0_1_rdma_memory_registration.yaml",
            lambda data: data["nodes"][0]["common_misconceptions"].append("made_up_model"),
            "未知 misconception: made_up_model",
        ),
    ],
)
def test_unknown_cross_file_ids_are_rejected(
    curriculum_copy: Path,
    filename: str,
    mutate: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    _mutate_yaml(curriculum_copy / filename, mutate)

    with pytest.raises(CurriculumValidationError, match=message):
        load_curriculum(curriculum_copy)


def _node(data: dict[str, object], node_id: str) -> dict[str, object]:
    nodes = data["nodes"]
    assert isinstance(nodes, list)
    return next(item for item in nodes if item["id"] == node_id)


def test_required_free_explanation_without_assessment_is_rejected(
    curriculum_copy: Path,
) -> None:
    def remove_free_explanation(data: dict[str, object]) -> None:
        _node(data, "virtual_vs_physical_memory")["assessment_ids"].remove("vm_q3_explain")

    _mutate_yaml(
        curriculum_copy / "v0_1_rdma_memory_registration.yaml",
        remove_free_explanation,
    )
    with pytest.raises(CurriculumValidationError, match="没有 free_explanation assessment"):
        load_curriculum(curriculum_copy)


def test_required_scenario_transfer_without_assessment_is_rejected(
    curriculum_copy: Path,
) -> None:
    def remove_scenario(data: dict[str, object]) -> None:
        _node(data, "device_dma")["assessment_ids"].remove("dma_q2_scenario")

    _mutate_yaml(curriculum_copy / "v0_1_rdma_memory_registration.yaml", remove_scenario)
    with pytest.raises(CurriculumValidationError, match="没有 scenario_transfer assessment"):
        load_curriculum(curriculum_copy)


def test_assessment_count_below_minimum_independent_evidence_is_rejected(
    curriculum_copy: Path,
) -> None:
    def raise_minimum(data: dict[str, object]) -> None:
        _node(data, "device_dma")["mastery_requirements"]["minimum_independent_evidence"] = 4

    _mutate_yaml(curriculum_copy / "v0_1_rdma_memory_registration.yaml", raise_minimum)
    with pytest.raises(CurriculumValidationError, match="少于 minimum_independent_evidence"):
        load_curriculum(curriculum_copy)


def test_target_probe_question_must_belong_to_target_node(curriculum_copy: Path) -> None:
    def mismatch_probe(data: dict[str, object]) -> None:
        data["entry_policy"]["target_probe_questions"]["memory_registration"] = "vm_q1_pointer_kind"

    _mutate_yaml(curriculum_copy / "v0_1_rdma_memory_registration.yaml", mismatch_probe)
    with pytest.raises(CurriculumValidationError, match="与目标 node memory_registration 不匹配"):
        load_curriculum(curriculum_copy)


def test_theoretically_unreachable_mastery_requirement_is_rejected(
    curriculum_copy: Path,
) -> None:
    def remove_required_type(data: dict[str, object]) -> None:
        _node(data, "rdma_data_path")["assessment_ids"].remove("path_q3_explain")

    _mutate_yaml(curriculum_copy / "v0_1_rdma_memory_registration.yaml", remove_required_type)
    with pytest.raises(CurriculumValidationError, match="Mastered 条件理论上不可达到"):
        load_curriculum(curriculum_copy)
