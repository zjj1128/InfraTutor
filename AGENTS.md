# AGENTS.md — InfraTutor 仓库规则

本仓库由人类产品负责人定义教学目标，由 Codex 实现工程。所有 Agent 在修改代码前必须遵守本文件。

## 1. 开工前必读

按顺序阅读：

1. `DECISIONS.md`
2. `PROJECT_SPEC.md`
3. `ARCHITECTURE.md`
4. `docs/COURSE_DESIGN.md`
5. `docs/LEARNER_STATE.md`
6. `docs/LLM_CONTRACT.md`
7. `docs/TUTOR_ENGINE.md`
8. `docs/ACCEPTANCE_TESTS.md`
9. `IMPLEMENTATION_PLAN.md`

不要只读 README 后自行发挥。

## 2. 产品底线

- InfraTutor 不是普通聊天机器人。
- Tutor Engine 拥有最终教学决策权。
- LLM 不能直接写 Mastery、状态或解锁结果。
- 课程 YAML 是“教什么”的来源。
- Learner State 是结构化长期状态，不能用聊天摘要替代。
- 所有影响程序逻辑的 LLM 输出必须 schema 校验。
- 每次状态变化必须关联 Evidence 和 Decision Trace。

## 3. V0.1 范围纪律

除非用户明确修改设计，不得加入：

- RAG / 向量数据库。
- 内部文档导入。
- SSH / Web Terminal。
- Slurm 自动执行。
- 多用户与主管后台。
- 多 Agent。
- Fine-tuning。
- 本地模型部署。
- 图数据库。
- 微服务、消息队列、Kubernetes。

不要为了“以后可能需要”提前抽象复杂框架。

## 4. 技术原则

- Frontend：React + TypeScript + Vite。
- Backend：FastAPI + Pydantic + SQLAlchemy。
- Database：SQLite。
- Curriculum：YAML。
- 外部模型通过 `LLMGateway` 接口。
- 默认 `LLM_MODE=mock`。
- 优先使用标准库和少量成熟依赖。
- 不引入 LangChain / LlamaIndex。

若确有理由改变技术选择，先在回复中说明影响，不得静默替换。

## 5. 实现顺序

严格按 `IMPLEMENTATION_PLAN.md` 分 Phase。

- 当前请求只做指定 Phase。
- 不提前实现后续大功能。
- 可以为后续留清晰接口，但不要创建大量空类和空目录。
- 每阶段必须形成可运行、可测试的增量。

## 6. 领域规则

### 6.1 Course Graph

- 启动时校验 ID、引用和环。
- `prerequisite` 是 V0.1 唯一硬决策关系。
- 不允许运行时由 LLM创建节点或边。

### 6.2 Learner State

- TEACH 不产生 Mastery Evidence。
- “我会了”不改变 Mastery。
- 提示后的正确回答权重必须降低。
- Mastered 必须满足硬门槛。
- Evidence 是不可变记录。

### 6.3 LLM

- Assessor 和 Teacher 使用不同合同。
- Assessor 只根据给定 rubric 判断。
- Teacher 只根据最终 directive 表达。
- 未知 ID、非法 JSON 或 question mismatch 必须拒绝。
- 真实 LLM 失败不得伪造成功结果。

### 6.4 Tutor Engine

- `recommended_action` 是建议，不是命令。
- Critical misconception 优先于推进。
- 未满足前置时不得 ADVANCE。
- 补课必须维护 return stack。
- 返回原节点后必须重新评估，不能自动继承掌握。

## 7. 测试规则

每个核心功能同时提供：

- 正常路径测试。
- 至少一个失败/边界测试。

必须优先完成：

- Curriculum validation tests。
- Mastery rule tests。
- Tutor policy tests。
- Golden Path integration test。

自动化测试不得依赖真实外部模型或网络。

## 8. 代码质量

- Python 和 TypeScript 使用明确类型。
- 路由层保持薄，领域逻辑进入 service / engine。
- 不复制课程事实到 prompt、代码和测试多个位置；测试可使用最小 fixture。
- 错误信息应可操作。
- 重要决策用简短注释解释“为什么”，不要逐行解释显而易见代码。
- 不提交 `.env`、数据库运行文件、API Key、日志和构建产物。

## 9. UI 原则

- 中文优先，技术术语可保留英文。
- 普通界面显示离散状态，不显示虚假精确百分比。
- Debug Panel 可显示内部值，但默认折叠。
- 非实现节点明确显示 Coming Later。
- Tutor 每次通常只问一个问题。
- 不把整页做成只有聊天框。

## 10. 完成任务时的报告格式

每次 Codex 完成一个 Phase 后，应报告：

1. 实现了什么。
2. 修改/创建了哪些关键文件。
3. 做了哪些工程取舍及原因。
4. 运行了哪些命令。
5. 测试结果。
6. 哪些内容仍属于后续 Phase。
7. 是否发现设计文档冲突。

不要只说“已完成”。

## 11. 发生冲突时

优先级：

```text
用户当前明确指令
  > DECISIONS.md
  > PROJECT_SPEC.md
  > 领域设计文档
  > IMPLEMENTATION_PLAN.md
  > 代码中的旧实现
```

若文档冲突影响行为，停止扩展该部分，采用最保守实现并在报告中指出冲突；不要私自改变核心教学规则。
