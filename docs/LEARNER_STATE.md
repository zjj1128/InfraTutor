# Learner State 设计

## 1. 定义

Learner State 是 InfraTutor 对“当前学习者会什么、不会什么、证据有多少、存在什么误解、现在应该学什么”的结构化记录。

它不是一段由 LLM 随手总结的文字，也不是一个粗略的“RDMA 60%”。状态必须细化到知识节点，并且每次变化都能追溯到证据。

## 2. 状态分层

### 2.1 Learner Profile

相对稳定的信息：

- `learner_id`
- `display_name`
- `target_role`
- `background_assumptions`
- `teaching_preferences`
- `created_at`

V0.1 使用固定 `default_learner`。教学偏好仅作为 Teacher 表达参考，不能覆盖课程门槛。

### 2.2 Per-node State

每个知识节点拥有独立状态：

- `status`（面向 UI 的 effective learner status）
- `progress_status`
- `access_status`（由前置闭包派生，不单独持久化）
- `mastery_score`
- `confidence_score`
- `evidence_weight`
- `attempts`
- `last_seen_at`
- `last_tested_at`
- `review_due_at`

### 2.3 Misconception State

误解状态：

- `suspected`：一次低置信度迹象。
- `active`：明确回答或多次证据支持。
- `resolved`：之后通过无提示回答证明已纠正。

### 2.4 Session State

当前教学上下文：

- `learner_id`、`mode`。
- `target_node_id`：用户想达到的目标节点。
- `current_node_id`：当前实际节点。
- `expected_question_id`：当前等待的课程问题。
- `return_stack`：补课返回栈。
- `status`、`last_action`、`current_assistance_level`。
- `used_target_diagnostic_probes`：本 session 已消费的目标探针。
- `created_at`、`updated_at`。

## 3. 学习进度、访问性与 UI 状态

节点内部同时保留两个互不替代的维度：

- `progress_status`：`no_evidence / learning / partial / mastered / review_needed`，只描述学习证据。
- `access_status`：`locked / available`，只由 prerequisite 闭包和 supporting assumption 策略决定。

UI 使用派生的 `learner_status`：访问性为 `locked` 时始终显示 `locked`；访问性为
`available` 且进度为 `no_evidence` 时显示 `ready`；其余显示对应的学习进度。

### `locked`

前置节点尚未满足，不能进入正常教学进度；只有课程人工声明的 target diagnostic probe 可以进行一次诊断，且不能因此绕过前置。

### `ready`

前置已满足，但尚未产生学习证据。

### `learning`

已经开始，有少量证据，但掌握度仍低或证据相互矛盾。

### `partial`

已有明显理解，但尚未满足 Mastered 的证据门槛。

### `mastered`

通过多种、相对独立、无提示的证据证明掌握，且没有 active critical misconception。

### `review_needed`

过去曾 mastered，但后续失败或达到复习时间。

## 4. 为什么同时需要 Mastery 与 Confidence

`mastery_score` 表示当前证据显示答得有多好。

`confidence_score` 表示系统对这一判断有多确信。

例如只回答一道简单选择题且答对：

```text
mastery_score ≈ 高
confidence_score ≈ 低
```

这意味着“看起来可能会，但证据不足”，不能直接 Mastered。

## 5. Evidence 模型

每次正式评估产生一个不可变 Evidence：

```json
{
  "id": "evidence_001",
  "node_id": "memory_registration",
  "question_id": "mr_q2_explain",
  "evidence_type": "free_explanation",
  "score": 0.75,
  "weight": 1.0,
  "assistance_level": "none",
  "rubric_results": [
    {"criterion_id": "mr_data_stays_in_host_memory", "result": "met"},
    {"criterion_id": "mr_enables_translation_and_protection", "result": "met"},
    {"criterion_id": "mr_links_to_dma", "result": "not_met"}
  ],
  "misconception_ids": [],
  "created_at": "..."
}
```

### Evidence Type 建议权重

| 类型 | 默认权重 | 说明 |
|---|---:|---|
| `recognition` | 0.40 | 单选、判断，容易猜中 |
| `short_answer` | 0.75 | 简短解释 |
| `free_explanation` | 1.00 | 自主解释概念 |
| `scenario_transfer` | 1.25 | 在新场景中迁移 |
| `delayed_review` | 1.25 | 隔一段时间再次回忆 |
| `lab` | 1.50 | 后续真实实践，V0.1 不使用 |

### Assistance Level 修正

| 提示级别 | 权重乘数 |
|---|---:|
| `none` | 1.00 |
| `light_hint` | 0.75 |
| `strong_hint` | 0.45 |
| `answer_revealed` | 0.15 |

最终 Evidence Weight：

```text
default_type_weight × assistance_multiplier
```

## 6. V0.1 的确定性更新规则

为了简单、可解释，V0.1 不使用复杂的 Bayesian Knowledge Tracing。

设：

- `old_mastery`：旧掌握分数。
- `old_weight`：历史有效证据权重，上限取 3.0，避免历史永久压制新证据。
- `evidence_score`：本次 rubric 得分，0～1。
- `new_weight`：本次修正后的证据权重。

更新：

```text
bounded_old_weight = min(old_weight, 3.0)

new_mastery =
    (old_mastery × bounded_old_weight + evidence_score × new_weight)
    / (bounded_old_weight + new_weight)
```

若没有旧证据，则 `new_mastery = evidence_score`。

累计置信度：

```text
confidence_score = min(1.0, total_effective_evidence_weight / 3.0)
```

若存在 active critical misconception：

```text
confidence_score = max(0, confidence_score - 0.15)
```

> 数字只用于内部稳定决策，不在普通 UI 展示为“73% 学会”。

## 7. Status 派生规则

先独立计算学习进度：

1. 已经 mastered，但后续无提示评估 `< 0.50`：`review_needed`。
2. 没有 Evidence：`no_evidence`。
3. `mastery_score < 0.55`：`learning`。
4. 不满足 Mastered 门槛：`partial`。
5. 满足全部 Mastered 门槛：`mastered`。

再计算访问性：完整 prerequisite 闭包未 Mastered 时为 `locked`，否则为 `available`。
`learner_status` 最后合并这两个维度，因此 Golden Path 中的 `memory_registration` 可以同时是：

```text
progress_status = learning
access_status = locked
learner_status = locked
can_start_diagnostic_probe = true
```

## 8. Mastered 的硬性门槛

一个节点进入 `mastered` 必须同时满足：

- `mastery_score >= 0.80`。
- `confidence_score >= 0.65`。
- 至少两个独立 Evidence。
- 至少一个无提示 `free_explanation`。
- 至少一个无提示 `scenario_transfer`，或课程节点显式允许的替代证据。
- 没有 `active` 的 critical misconception。
- 必要 rubric criterion 均至少在一次无提示证据中被满足。

因此：

- 看过解释不会 Mastered。
- 一道选择题答对不会 Mastered。
- LLM 说“你掌握得很好”不会 Mastered。
- 用户点击“已完成”不会 Mastered。

## 9. Misconception 更新规则

### 激活

若 Assessor 在明确自由回答中检测到 critical misconception，直接标为 `active`。

若只在模糊回答中出现，先标记 `suspected`；第二次出现或追问确认后转为 `active`。

### 解决

只有满足以下条件才能转为 `resolved`：

- 学生在没有揭示答案的情况下明确否定该误解。
- 同时给出正确替代模型。
- 最好再通过一个相关场景题。

例如 `mr_copies_memory_to_hca` 的解决不只是回答“不会复制”，还应能说明数据仍在主机内存，MR 建立访问所需的固定、转换与保护信息。

## 10. 前置节点与解锁

V0.1 默认要求 prerequisite 状态为 `mastered` 才解锁后继节点。

为了避免过度僵硬，课程节点可声明：

```yaml
prerequisite_policy:
  all_mastered: true
  allow_partial:
    - ib_fabric_components
```

但该例外必须由人工课程文件定义，不能由 LLM 临时决定。

## 11. 补课返回栈

当学生在 `memory_registration` 上暴露 `device_dma` 缺口：

```text
return_stack = [memory_registration]
current_node = device_dma
```

补课节点 Mastered 后：

1. 检查返回目标的其他前置。
2. 若仍有缺口，继续补最近前置。
3. 否则回到 `memory_registration`。
4. 不自动把 MR 标记为已掌握，必须重新评估。

## 12. 初始状态

V0.1 提供两种 seed：

### Clean Seed

- 所有 pilot 节点从 `ready` 或 `locked` 开始。
- 用于正常体验。

### Golden Path Seed

为了快速演示关键闭环：

- `virtual_vs_physical_memory`: mastered
- `device_dma`: partial
- `pinned_memory`: partial
- `hca_role`: mastered
- `why_rdma`: mastered
- `rdma_data_path`: progress mastered（0.86 mastery / 0.74 confidence；DMA 完成前 access locked）
- `memory_registration`: progress learning / access locked / effective locked
- `lkey_rkey_concept`: locked

`rdma_data_path` 的基线避免它在 DMA/Pinned 补课完成后额外阻塞返回 MR。这个跳过只属于
Golden Path Seed；Clean Seed 仍按完整课程依赖学习。

## 13. 状态展示原则

普通学习者看到：

```text
DMA                 Partial
Pinned Memory       Partial
Memory Registration Learning
```

调试面板才显示：

```text
mastery=0.62
confidence=0.48
active_misconceptions=[mr_copies_memory_to_hca]
```

避免给学习者造成虚假精确感，同时保留开发与研究价值。

Learner reset 删除默认 learner 时通过 SQLite 外键级联清除 LearningSession、TutorTurnRecord、
SessionMessage、DecisionTrace 和 LLM metadata，再按所选 Seed 重建状态。abandon Session 则只改变
Session 状态，不删除或回滚已经产生的 Evidence、Misconception 和 Mastery。
