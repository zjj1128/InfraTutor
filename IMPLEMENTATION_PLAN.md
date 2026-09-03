# InfraTutor V0.1 实施计划

Codex 应按阶段实现，每阶段完成后运行测试并提交可检查结果。不要一条指令做完整项目。

## Phase 0：仓库骨架与开发体验

### 交付

- Backend / Frontend 基础目录。
- FastAPI 健康检查。
- React 页面可打开。
- 配置加载与 `.env.example`。
- SQLite 初始化。
- 统一开发命令或 Makefile / scripts。
- 基础 lint / test 命令。

### 验收

- 本地可启动前后端。
- 无 API Key 也能运行。
- README 写明启动步骤。

## Phase 1：Curriculum Loader 与 Course Graph

### 交付

- YAML Pydantic 模型。
- 加载 `roadmap.yaml` 与 pilot curriculum。
- ID、引用、循环依赖校验。
- 图查询服务。
- `GET /api/roadmap`。
- Roadmap 初版 UI。

### 验收

- AT-CG 全部通过。
- 页面显示九阶段与 V0.1 节点。

## Phase 2：Learner State 与持久化

### 交付

- 数据库实体与 repository。
- default learner。
- Clean / Golden Path seed。
- Evidence、Misconception、Node State。
- Mastery / Confidence 计算。
- `GET /api/learner` 与 reset API。

### 验收

- AT-LS 全部通过。
- 重启后状态仍保存。

## Phase 3：Tutor Engine（先不用真实 LLM）

### 交付

- Action enum。
- Session State 与 return stack。
- Tutor Policy。
- Decision Trace。
- 使用固定 Assessment fixtures 驱动状态机。

### 验收

- AT-TE 全部通过。
- 单元测试能稳定复现 remediation 和 advance。

## Phase 4：LLM Gateway 与 Structured Output

### 交付

- LLM Gateway protocol。
- Mock Provider。
- 一个 Live Provider Adapter。
- Assessor / Teacher Pydantic contracts。
- Schema 校验、一次重试和失败降级。
- Prompt 模板加载。

### 验收

- AT-LLM 全部通过。
- Mock 与 Live 对上层使用同一接口。
- 缺少 API Key 时明确使用 Mock 或提示配置，不崩溃。

## Phase 5：Tutor Session UI

### 交付

- 开始 Session。
- Tutor 消息流。
- 自由文本、单选题等基础 Question Renderer。
- 当前节点与学习目标。
- Debug Panel。
- 状态变化刷新。

### 验收

- 浏览器可手动完成 Golden Path。
- Side question 与跳级交互不会破坏会话。

## Phase 6：Golden Path E2E

### 交付

- 自动化浏览器 Golden Path。
- 错误继续路径。
- Answer revealed 路径。
- Reset 后可重复运行。

### 验收

- AT-GP-001 必须通过。
- E2E 不调用真实 LLM。

## Phase 7：体验与可靠性收尾

### 交付

- 错误消息。
- Loading / Retry 状态。
- UI 可读性。
- 日志脱敏。
- 文档同步。
- 真实 LLM 可选 smoke test。

### 验收

- 全部必需测试通过。
- 从空目录按 README 可运行。
- 没有超出 V0.1 的大功能。

## 建议的第一次 Codex 任务

只让 Codex完成 Phase 0 和 Phase 1：

```text
请先阅读项目根目录全部设计文档，重点阅读 AGENTS.md、PROJECT_SPEC.md、ARCHITECTURE.md、docs/COURSE_DESIGN.md 和 IMPLEMENTATION_PLAN.md。

本轮只实现 Phase 0 与 Phase 1，不实现 LLM、Tutor Engine 或 Learner State。

完成后：
1. 运行课程 YAML 校验测试。
2. 运行后端和前端测试。
3. 报告创建的文件、关键取舍、测试结果和仍未实现的 Phase。
4. 不擅自扩大 V0.1 范围。
```

## 何时暂停让人体验

Phase 5 完成后，应先由项目负责人亲自体验 3 类路径：

1. 完全答错。
2. 部分正确。
3. 连续要求直接给答案。

在体验教学节奏之前，不进入完整课程扩展。
