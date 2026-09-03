# Tutor Engine 设计

## 1. 定义

Tutor Engine 是 InfraTutor 中负责“下一步怎样教”的领域控制器。

它不等于 LLM。LLM 可以理解学生回答、按 rubric 提取证据、生成解释；Tutor Engine 根据课程图、Learner State、评估结果和固定策略做最终教学决定。

```text
LLM：这个回答暴露了什么？怎样表达更自然？
Tutor Engine：因此下一步必须做什么？状态是否改变？去哪个节点？
```

## 2. 输入与输出

### 输入

- 当前 Session State。
- 当前课程节点。
- 目标节点。
- 当前题目与 rubric。
- 学生输入。
- Assessor 的结构化结果。
- 当前 Learner State。
- 课程图的 prerequisite 与推荐后继。

### 输出

```json
{
  "action": "REMEDIATE",
  "target_node_id": "device_dma",
  "reason_codes": [
    "CRITICAL_MISCONCEPTION_DETECTED",
    "WEAK_PREREQUISITE"
  ],
  "state_updates": [],
  "return_stack": ["memory_registration"],
  "teacher_directive": {
    "goal": "纠正 DMA 是 CPU memcpy 的误解",
    "interaction_type": "guided_question",
    "must_not_reveal_answer": true
  }
}
```

## 3. 动作集合

### `ORIENT`

说明当前学习目标、为什么要学以及与整体路线的关系。

### `TEACH`

提供一小段新知识或换一种解释。默认后续应接 `ASK`，不能连续长篇灌输。

### `ASK`

提出用于激活思考的非正式问题，不一定产生正式 Evidence。

### `ASSESS`

提出有 rubric 的正式评估题，回答将产生 Evidence。

### `HINT`

学生思路接近但缺关键点时给分级提示。提示程度必须进入 Evidence。

### `RETRY`

同一目标换一个问法，让学生重新尝试。

### `REMEDIATE`

回退到前置节点补课。必须记录 return stack 和原因。

### `REVIEW`

对已经学过但需要再次确认的节点进行复习。

### `ADVANCE`

当前节点满足 Mastered 门槛后进入下一节点或返回原目标。

### `ANSWER_SIDE_QUESTION`

回答当前学习之外但仍相关的问题。默认不改变 Mastery，回答后返回主线。

## 4. 决策权边界

### LLM 可以建议

- 当前回答可能有哪些误解。
- 哪些 rubric 条件满足。
- 是否需要追问澄清。
- 适合怎样解释。

### Tutor Engine 必须决定

- 是否写入 Evidence。
- 误解是否 active / resolved。
- mastery、confidence、status。
- 是否 Mastered。
- 是否回退。
- 回退到哪个已定义节点。
- 是否解锁下一节点。
- 最终 action。

`recommended_action` 只是 Assessor 的参考字段，不能直接执行。

## 5. Target Diagnostic Probe

当用户主动选择尚未解锁的目标节点时，Tutor Engine 默认先解释缺失前置并回退。只有课程文件显式配置 `allow_target_diagnostic_probe=true` 且为该目标指定 probe question 时，才允许先进行一次诊断。

诊断探针规则：

- 只用于暴露误解和选择补课节点。
- 不会把 locked 节点改为 ready。
- 即使回答正确，也不能替代其前置 Mastery；可以记录低权重诊断 Evidence。
- 每个 session 对同一目标最多执行一次，避免绕过课程图。
- Golden Path 使用 `mr_q1_copy_check` 作为 Memory Registration 的探针。

## 6. 决策优先级

每轮按以下顺序判断，前面的规则优先：

### P0：系统完整性

- 结构化输出非法：不更新状态，选择安全重试或错误提示。
- 当前 question ID 与 session 不一致：拒绝写证据。
- Assessor 返回课程中不存在的 ID：视为非法输出。

### P1：需要澄清

若回答明显与问题不匹配、过短或语义不确定：

- 不急于判错。
- 选择 `ASK` 或 `RETRY`。
- 最多一次澄清后再决定。

### P2：Critical Misconception

若出现 active critical misconception：

1. 查找该 misconception 指向的 remediation nodes。
2. 根据当前 Learner State 选择最弱且最近的前置节点。
3. 若当前就在该节点，选择 `TEACH` / `HINT` / `RETRY`。
4. 若需要跨节点，选择 `REMEDIATE` 并压入 return stack。
5. 禁止 `ADVANCE`。

### P3：前置知识不足

即使没有明确误解，只要当前节点的必要前置未满足：

- 选择最近的未掌握前置。
- 优先补直接 prerequisite；必要时递归向上。
- 不能跳到图外节点。

### P4：当前回答错误

无 critical misconception 但 score 较低：

- 第一次：`HINT` 或简短 `TEACH`。
- 使用强提示后：下次证据权重降低。
- 连续失败达到阈值：检查是否需要 `REMEDIATE`。

### P5：当前回答部分正确

- 缺一项关键 criterion：针对该点 `ASK` 或 `HINT`。
- 不重复学生已经正确表达的全部内容。
- 不立即 ADVANCE。

### P6：当前回答正确但证据不足

- 如果 Mastered 门槛尚未满足，选择另一种证据类型。
- 常见顺序：recognition → free explanation → scenario transfer。

### P7：已满足 Mastered

- 解决相关 active misconception。
- 若 return stack 非空，回到原目标并重新检查。
- 否则选择 `ADVANCE` 到推荐后继。

## 7. 补课节点选择算法

输入：当前节点 `N`、评估结果、Learner State。

候选来源：

1. misconception 显式 `remediation_nodes`。
2. assessment 的 `missing_concept_ids`。
3. 当前节点 prerequisite 闭包中未 Mastered 节点。

排序建议：

1. 被 critical misconception 直接指向。
2. 与当前节点图距离更近。
3. status 更弱：learning < partial < review_needed。
4. confidence 更低。
5. 课程作者给出的 `remediation_priority`。

选择第一个节点。若所有候选都已 Mastered，则在当前节点选择 `RETRY` 或不同场景评估，而不是无依据回退。

## 8. Golden Path 的确定性规则

针对 `mr_copies_memory_to_hca`：

```text
IF misconception == mr_copies_memory_to_hca
THEN
    block ADVANCE
    activate misconception on memory_registration
    candidate remediation = [device_dma, pinned_memory, rdma_data_path]

    IF device_dma != mastered
        REMEDIATE device_dma
    ELSE IF pinned_memory != mastered
        REMEDIATE pinned_memory
    ELSE
        RETRY memory_registration with host-memory/data-path scenario
```

针对 `dma_is_cpu_memcpy`：

```text
IF misconception == dma_is_cpu_memcpy
THEN
    REMEDIATE device_dma
    teacher must contrast:
      CPU configures transfer
      device performs data movement
      CPU need not execute byte-by-byte copy loop
```

补课成功后：

```text
IF current remediation node becomes mastered
AND return_stack is not empty
THEN return to top target
BUT do not inherit mastery for target
ASK a fresh target-node assessment
```

## 9. 评估回合伪代码

```python
async def handle_assessment_answer(session, learner, answer):
    question = curriculum.get_assessment(session.expected_question_id)
    node = curriculum.get_node(question.node_id)

    assessment = await assessment_service.assess(
        question=question,
        learner_answer=answer,
        allowed_node_ids=curriculum.node_ids,
        allowed_misconception_ids=node.common_misconceptions,
    )

    if not assessment.valid:
        return safe_retry_without_state_change()

    evidence = evidence_factory.from_assessment(
        assessment=assessment,
        assistance_level=session.current_assistance_level,
        question=question,
    )
    learner_state.append_evidence(evidence)
    learner_state.update_misconceptions(assessment, question)
    learner_state.recalculate_node(node.id)

    decision = policy.choose(
        node=node,
        assessment=assessment,
        learner_state=learner_state,
        graph=curriculum.graph,
        session=session,
    )

    apply_session_transition(session, decision)

    message = await llm.compose_tutor_message(
        build_teacher_request(decision, learner_state, curriculum)
    )

    persist(evidence, decision, message, session)
    return build_response(message, decision, learner_state)
```

## 10. 非评估型输入

### 学生提问

若学生在等待回答问题时反问：

1. 判断问题是否与当前节点相关。
2. 相关：`ANSWER_SIDE_QUESTION`，回答后重新呈现原问题或一个等价问题。
3. 不相关：简短回答范围说明，再返回主线。
4. 该回合不写 Mastery Evidence。

### 学生要求跳过

若目标 locked：

- 解释阻塞原因。
- 展示最少缺失前置。
- 选择 `REMEDIATE` 或继续当前节点。

若目标 ready：可以切换，但旧节点的未完成状态保留。

### 学生说“我懂了”

- 可作为主观反馈记录。
- 不能更新 Mastery。
- 下一动作应是短评估，而不是 ADVANCE。

## 11. Teacher Directive

Tutor Engine 不直接拼最终文案，而是发出受约束指令：

```json
{
  "action": "REMEDIATE",
  "target_node_id": "device_dma",
  "learning_goal": "区分 CPU 发起配置与设备执行 DMA",
  "known_correct_points": [],
  "missing_points": ["device moves data without CPU bytewise copy"],
  "active_misconceptions": ["dma_is_cpu_memcpy"],
  "preferred_method": "concrete_data_path_question",
  "must_ask_one_question": true,
  "must_not_reveal_full_answer": true,
  "max_length_chars": 500
}
```

Teacher 必须遵守该指令，不得擅自 ADVANCE 或宣布 Mastered。

## 12. Decision Trace

每个关键回合保存：

```json
{
  "input": {
    "node_id": "memory_registration",
    "question_id": "mr_q1_copy_check"
  },
  "assessment_summary": {
    "score": 0.1,
    "misconceptions": ["mr_copies_memory_to_hca"]
  },
  "state_before": {
    "device_dma": "partial",
    "pinned_memory": "partial",
    "memory_registration": "learning"
  },
  "candidate_actions": [
    {"action": "REMEDIATE", "target": "device_dma", "priority": 100},
    {"action": "REMEDIATE", "target": "pinned_memory", "priority": 90}
  ],
  "final_action": "REMEDIATE",
  "target_node_id": "device_dma",
  "reason_codes": [
    "CRITICAL_MISCONCEPTION_DETECTED",
    "WEAK_PREREQUISITE"
  ],
  "state_delta": {}
}
```

调试面板用它回答：“为什么系统把我带回 DMA？”

## 13. 必须避免的反模式

- 让 LLM 返回 `mastery=0.9` 后直接写数据库。
- 用完整聊天历史代替 Learner State。
- 每次都把全课程 YAML 塞给模型。
- 让模型自由发明 node ID 或 misconception ID。
- 学生答错后直接长篇给出标准答案。
- Tutor 连续提出多个问题，导致无法判断每个回答对应什么。
- 只用关键词匹配自由回答，不使用 rubric 与语义评估。
- 因为真实模型不稳定而让核心自动化测试依赖外部 API。
