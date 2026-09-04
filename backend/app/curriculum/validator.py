from collections.abc import Callable, Iterable

from backend.app.curriculum.models import AssessmentSet, PilotModule, Roadmap


class CurriculumValidationError(ValueError):
    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("课程校验失败:\n- " + "\n- ".join(issues))


def _duplicate_ids(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _report_duplicates(
    issues: list[str],
    label: str,
    values: Iterable[str],
    formatter: Callable[[str], str] | None = None,
) -> None:
    for duplicate in sorted(_duplicate_ids(values)):
        display = formatter(duplicate) if formatter else duplicate
        issues.append(f"重复的{label} ID: {display}")


def _find_prerequisite_cycle(roadmap: Roadmap, known_node_ids: set[str]) -> list[str] | None:
    prerequisites = {
        node.id: [item for item in node.prerequisites if item in known_node_ids]
        for node in roadmap.nodes
    }
    state: dict[str, int] = {node_id: 0 for node_id in known_node_ids}
    stack: list[str] = []

    def visit(node_id: str) -> list[str] | None:
        state[node_id] = 1
        stack.append(node_id)
        for prerequisite_id in prerequisites.get(node_id, []):
            if state[prerequisite_id] == 0:
                cycle = visit(prerequisite_id)
                if cycle:
                    return cycle
            elif state[prerequisite_id] == 1:
                start = stack.index(prerequisite_id)
                return [*stack[start:], prerequisite_id]
        stack.pop()
        state[node_id] = 2
        return None

    for node_id in sorted(known_node_ids):
        if state[node_id] == 0:
            cycle = visit(node_id)
            if cycle:
                return cycle
    return None


def validate_curriculum(
    roadmap: Roadmap, pilot: PilotModule, assessment_set: AssessmentSet
) -> None:
    issues: list[str] = []

    _report_duplicates(issues, "stage", (stage.id for stage in roadmap.stages))
    _report_duplicates(issues, "stage order", (str(stage.order) for stage in roadmap.stages))
    _report_duplicates(issues, "node", (node.id for node in roadmap.nodes))
    _report_duplicates(issues, "pilot node", (node.id for node in pilot.nodes))
    _report_duplicates(issues, "assessment", (item.id for item in assessment_set.assessments))
    _report_duplicates(issues, "misconception", (item.id for item in pilot.misconceptions))

    stage_ids = {stage.id for stage in roadmap.stages}
    roadmap_nodes = {node.id: node for node in roadmap.nodes}
    node_ids = set(roadmap_nodes)
    pilot_nodes = {node.id: node for node in pilot.nodes}
    assessment_by_id = {item.id: item for item in assessment_set.assessments}
    assessment_ids = set(assessment_by_id)
    misconception_by_id = {item.id: item for item in pilot.misconceptions}
    misconception_ids = set(misconception_by_id)

    if pilot.stage_id not in stage_ids:
        issues.append(f"pilot module 引用了未知 stage: {pilot.stage_id}")

    for node in roadmap.nodes:
        if node.stage_id not in stage_ids:
            issues.append(f"node {node.id} 引用了未知 stage: {node.stage_id}")
        for prerequisite_id in node.prerequisites:
            if prerequisite_id not in node_ids:
                issues.append(f"node {node.id} 引用了未知 prerequisite: {prerequisite_id}")
        for next_id in node.recommended_next:
            if next_id == node.id:
                issues.append(f"node {node.id} 的 recommended_next 不能指向自身")
            elif next_id not in node_ids:
                issues.append(f"node {node.id} 引用了未知 recommended_next: {next_id}")
        for reinforced_id in node.reinforces:
            if reinforced_id not in node_ids:
                issues.append(f"node {node.id} 引用了未知 reinforces node: {reinforced_id}")

    cycle = _find_prerequisite_cycle(roadmap, node_ids)
    if cycle:
        issues.append(f"prerequisite 存在环: {' -> '.join(cycle)}")

    for node in pilot.nodes:
        roadmap_node = roadmap_nodes.get(node.id)
        if roadmap_node is None:
            issues.append(f"pilot node 不存在于 roadmap: {node.id}")
            continue
        if roadmap_node.stage_id != pilot.stage_id:
            issues.append(
                f"pilot node {node.id} 位于 {roadmap_node.stage_id}, 预期 {pilot.stage_id}"
            )
        if roadmap_node.type != node.type:
            issues.append(f"pilot node {node.id} 的 type 与 roadmap 不一致")
        if set(roadmap_node.prerequisites) != set(node.prerequisites):
            issues.append(f"pilot node {node.id} 的 prerequisites 与 roadmap 不一致")
        if roadmap_node.implementation_status != "pilot":
            issues.append(f"pilot node {node.id} 在 roadmap 中未标记为 pilot")
        if not node.assessment_ids:
            issues.append(f"pilot node {node.id} 至少需要一个 assessment")
        for prerequisite_id in node.prerequisites:
            if prerequisite_id not in node_ids:
                issues.append(f"pilot node {node.id} 引用了未知 prerequisite: {prerequisite_id}")
        for next_id in node.recommended_next:
            if next_id == node.id:
                issues.append(f"pilot node {node.id} 的 recommended_next 不能指向自身")
            elif next_id not in node_ids:
                issues.append(f"pilot node {node.id} 引用了未知 recommended_next: {next_id}")
        for misconception_id in node.common_misconceptions:
            if misconception_id not in misconception_ids:
                issues.append(f"pilot node {node.id} 引用了未知 misconception: {misconception_id}")
        for assessment_id in node.assessment_ids:
            assessment = assessment_by_id.get(assessment_id)
            if assessment is None:
                issues.append(f"pilot node {node.id} 引用了未知 assessment: {assessment_id}")
            elif assessment.node_id != node.id:
                issues.append(
                    f"assessment {assessment_id} 属于 {assessment.node_id}, 不能挂到 {node.id}"
                )

        valid_assessments = [
            assessment_by_id[item]
            for item in dict.fromkeys(node.assessment_ids)
            if item in assessment_by_id and assessment_by_id[item].node_id == node.id
        ]
        evidence_types = {item.evidence_type for item in valid_assessments}
        unreachable_reasons: list[str] = []
        requirements = node.mastery_requirements
        if (
            requirements.require_unassisted_free_explanation
            and "free_explanation" not in evidence_types
        ):
            issues.append(
                f"pilot node {node.id} 要求 unassisted free_explanation，"
                "但没有 free_explanation assessment"
            )
            unreachable_reasons.append("缺少 free_explanation")
        if (
            requirements.require_unassisted_scenario_transfer
            and "scenario_transfer" not in evidence_types
        ):
            issues.append(
                f"pilot node {node.id} 要求 unassisted scenario_transfer，"
                "但没有 scenario_transfer assessment"
            )
            unreachable_reasons.append("缺少 scenario_transfer")
        if len(valid_assessments) < requirements.minimum_independent_evidence:
            issues.append(
                f"pilot node {node.id} 的 assessment 数量 {len(valid_assessments)} "
                f"少于 minimum_independent_evidence "
                f"{requirements.minimum_independent_evidence}"
            )
            unreachable_reasons.append("独立 assessment 数量不足")
        if unreachable_reasons:
            issues.append(
                f"pilot node {node.id} 的 Mastered 条件理论上不可达到: "
                + "、".join(unreachable_reasons)
            )

    for roadmap_node in roadmap.nodes:
        if roadmap_node.implementation_status == "pilot" and roadmap_node.id not in pilot_nodes:
            issues.append(f"roadmap pilot node 缺少详细课程定义: {roadmap_node.id}")

    for assumption in pilot.supporting_assumptions:
        if assumption.node_id not in node_ids:
            issues.append(f"supporting assumption 引用了未知 node: {assumption.node_id}")

    entry_policy = pilot.entry_policy
    if entry_policy.normal_start_node_id not in pilot_nodes:
        issues.append(
            f"normal_start_node_id 不是已定义的 pilot node: {entry_policy.normal_start_node_id}"
        )
    for target_node_id, question_id in entry_policy.target_probe_questions.items():
        if target_node_id not in pilot_nodes:
            issues.append(f"target probe 引用了未知 pilot node: {target_node_id}")
        assessment = assessment_by_id.get(question_id)
        if assessment is None:
            issues.append(f"target probe 引用了未知 assessment: {question_id}")
        elif assessment.node_id != target_node_id:
            issues.append(
                f"target probe question {question_id} 与目标 node {target_node_id} 不匹配"
            )
        elif question_id not in pilot_nodes[target_node_id].assessment_ids:
            issues.append(f"target probe question {question_id} 未挂载到目标 node {target_node_id}")

    for misconception in pilot.misconceptions:
        if misconception.node_id not in pilot_nodes:
            issues.append(
                f"misconception {misconception.id} 引用了未知 pilot node: {misconception.node_id}"
            )
        for remediation_node_id in misconception.remediation_nodes:
            if remediation_node_id not in node_ids:
                issues.append(
                    f"misconception {misconception.id} 引用了未知 remediation node: "
                    f"{remediation_node_id}"
                )

    criterion_ids: list[str] = []
    for assessment in assessment_set.assessments:
        if assessment.node_id not in pilot_nodes:
            issues.append(f"assessment {assessment.id} 引用了未知 pilot node: {assessment.node_id}")
        criterion_ids.extend(criterion.id for criterion in assessment.rubric.criteria)
        for misconception_id in assessment.rubric.critical_misconception_ids:
            if misconception_id not in misconception_ids:
                issues.append(
                    f"assessment {assessment.id} 引用了未知 misconception: {misconception_id}"
                )
        option_ids = [option.id for option in assessment.options]
        for duplicate in sorted(_duplicate_ids(option_ids)):
            issues.append(f"assessment {assessment.id} 包含重复 option ID: {duplicate}")
        for correct_option_id in assessment.correct_option_ids:
            if correct_option_id not in option_ids:
                issues.append(
                    f"assessment {assessment.id} 引用了未知 correct option: {correct_option_id}"
                )
    _report_duplicates(issues, "criterion", criterion_ids)

    for seed_name, seed in (("clean", pilot.seeds.clean), ("golden_path", pilot.seeds.golden_path)):
        for node_id in seed.node_states:
            if node_id not in pilot_nodes:
                issues.append(f"{seed_name} seed 引用了未知 pilot node: {node_id}")
        if seed.target_node_id and seed.target_node_id not in pilot_nodes:
            issues.append(f"{seed_name} seed 引用了未知 target node: {seed.target_node_id}")
        if seed.initial_question_id and seed.initial_question_id not in assessment_ids:
            issues.append(
                f"{seed_name} seed 引用了未知 initial question: {seed.initial_question_id}"
            )

    if issues:
        raise CurriculumValidationError(issues)
