# 给 Codex 的首次启动提示词

将下面内容作为 Codex 在新仓库中的第一条任务。第一轮只做 Phase 0 和 Phase 1。

---

你正在实现 `InfraTutor V0.1`。这是一个面向高速互联部门新人的 AI 自适应学习 Web App，不是普通聊天机器人。

请先完整阅读并遵守：

- `AGENTS.md`
- `DECISIONS.md`
- `PROJECT_SPEC.md`
- `ARCHITECTURE.md`
- `docs/COURSE_DESIGN.md`
- `docs/LEARNER_STATE.md`
- `docs/LLM_CONTRACT.md`
- `docs/TUTOR_ENGINE.md`
- `docs/MVP_USER_FLOW.md`
- `docs/ACCEPTANCE_TESTS.md`
- `IMPLEMENTATION_PLAN.md`
- `curriculum/*.yaml`
- `schemas/*.json`

本轮仅实现 `IMPLEMENTATION_PLAN.md` 中的 **Phase 0 与 Phase 1**：

1. 建立 React + TypeScript + Vite 前端和 FastAPI 后端。
2. 建立清晰但不过度设计的目录结构。
3. 支持配置加载和 SQLite 初始化，但不要实现完整 Learner State。
4. 实现课程 YAML 的 Pydantic 模型、加载器和校验器。
5. 校验 node/stage/assessment/misconception ID、未知引用与 prerequisite 环。
6. 实现 Course Graph 的基本查询。
7. 实现 `GET /api/roadmap`。
8. 实现 Roadmap 初版页面，展示九阶段、V0.1 可用节点、状态占位和 Coming Later。
9. 编写并运行 Phase 0/1 所需测试，至少覆盖 `AT-CG-001` 到 `AT-CG-005` 中当前可实现的部分。
10. 更新项目根 README，写明本地启动与测试命令。

本轮明确不要实现：

- LLM 调用。
- Tutor Engine。
- Mastery 算法。
- 完整数据库状态模型。
- RAG。
- 登录、多用户、主管后台。
- SSH / Slurm / 集群操作。
- 多 Agent。

实现时优先保证：课程数据可校验、图关系可查询、Roadmap 可见、测试可重复。不要为了未来扩展加入复杂框架，不要使用 LangChain、LlamaIndex、图数据库或微服务。

完成后请：

1. 列出关键新增文件。
2. 说明架构取舍。
3. 给出运行过的命令和测试结果。
4. 明确哪些功能尚未实现并属于后续 Phase。
5. 若文档之间存在冲突，指出具体位置，不要自行改变核心决定。

---

## 后续 Phase 的推荐指令形式

不要说“继续把整个项目做完”，而应使用：

```text
阅读当前仓库设计文档和已有实现。只实现 IMPLEMENTATION_PLAN.md 的 Phase 2。
完成后运行相关单元与集成测试，并按 AGENTS.md 的格式报告。
不要提前实现 Phase 3 及以后内容。
```
