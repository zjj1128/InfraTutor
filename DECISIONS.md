# InfraTutor V0.1 决策记录

本文件记录已经拍板的产品与工程决定。Codex 不得在没有明确理由和记录的情况下改变这些决定。

## D-001：目标学习者

**决定：** 默认用户是刚毕业的计算机专业学生。

预期已有基础：

- 会使用基本 Linux 命令。
- 接触过 Python 和 C。
- 知道 CPU、内存、进程、网络等基础名词。

不默认掌握：

- Slurm 的资源模型。
- DCU / GPU 的异构执行模型。
- PCIe / NUMA 拓扑。
- InfiniBand、RDMA、Verbs。
- MPI、UCX、RCCL。
- 集群通信性能分析与设计。

## D-002：完整课程路线

**决定：** 产品长期路线固定为九阶段：

1. Shell / Slurm / C 基础
2. HIP / DCU
3. InfiniBand / RDMA 理论
4. RDMA Verbs
5. MPI
6. UCX
7. RCCL
8. 网络数据分析
9. 网络设计与综合性能优化

课程不是死板章节目录，而是由知识节点与前置关系组成的图。

## D-003：V0.1 教学切片

**决定：** V0.1 页面展示完整九阶段路线，但只实现 Stage 3 中围绕 RDMA Memory Registration 的纵向切片，并补齐它跨阶段依赖的基础节点。

实现节点：

- Virtual Address vs Physical Page
- Device DMA
- Pinned Memory
- HCA Role
- Why RDMA
- RDMA Data Path
- Memory Registration
- lkey / rkey Concept（作为解锁后的下一节点）

**理由：** 这个切片具有明确误解、前置依赖和回退路径，最适合验证自适应教学，而不是只验证页面与聊天。课程允许对用户主动选择的锁定目标执行一次人工声明的诊断探针；探针只能发现缺口，不能绕过前置或直接解锁后继。

## D-004：Tutor 的控制权

**决定：** Learn 模式由 Tutor 主导进度。

Tutor 可以：

- 阻止学习尚未解锁的节点。
- 追加确认问题。
- 在检测到误解时回退前置节点。
- 暂停 ADVANCE，要求解释或场景迁移题。
- 在掌握条件成立后解锁下一节点。

用户仍可随时提问，但不能通过一句“我会了”直接改变 Mastery。

## D-005：掌握判定

**决定：** UI 使用离散状态；内部保存连续分数和证据。

UI 状态：

- `locked`
- `ready`
- `learning`
- `partial`
- `mastered`
- `review_needed`

内部字段：

- `mastery_score`
- `confidence_score`
- `evidence`
- `misconceptions`
- `attempts`
- `last_tested_at`

只有满足规定证据门槛，状态才可进入 `mastered`。

## D-006：人工与 AI 的边界

**决定：**

- 人工定义知识节点、前置关系、学习目标、核心事实、常见误解、题目 rubric 和掌握门槛。
- LLM 可根据学习者状态动态选择类比、提问方式、解释深度和反馈语言。
- LLM 不能自行创造课程节点、改写正确答案标准、直接把节点标记为 mastered。

## D-007：资料范围

**决定：** V0.1 仅使用公开、人工整理的课程内容。

不接入：

- 部门内部 Wiki。
- 内部拓扑与配置。
- 内部代码和测试数据。
- 企业 RAG。

## D-008：部署方式

**决定：** V0.1 为 WSL 本地单用户版本。

- 无注册登录。
- 使用固定 `default_learner`。
- 后端 API Key 存放在环境变量中。
- SQLite 本地持久化。
- 浏览器通过 localhost 使用。

## D-009：核心成功标准

**决定：** Golden Path 是第一核心验收目标。

当学生声称“Memory Registration 会把用户内存复制到 HCA”时，系统必须：

1. 按 rubric 检测出 `mr_copies_memory_to_hca`。
2. 记录误解证据。
3. 判断相关前置知识不足。
4. 选择 `REMEDIATE`，而不是继续 lkey/rkey。
5. 补习 DMA / Pinned Memory。
6. 再次无提示评估。
7. 回到 Memory Registration。
8. 通过解释题与迁移题后才标记 Mastered。
9. 解锁 lkey/rkey。

## D-010：技术边界

**决定：** 推荐技术栈为：

- Frontend：React + TypeScript + Vite。
- Backend：FastAPI + Pydantic + SQLAlchemy。
- Database：SQLite。
- LLM：通过自有 LLM Gateway 接入任一支持结构化输出的外部模型。
- Curriculum：YAML 文件。
- Tests：pytest、前端单元测试、至少一条 Golden Path 端到端测试。

V0.1 不引入 LangChain、LlamaIndex、图数据库、消息队列、Kubernetes、多 Agent 或微服务。

## D-011：可解释调试

**决定：** V0.1 提供开发者调试面板，用来显示：

- 当前课程节点。
- 本轮评估结果。
- 检测到的误解 ID。
- Tutor Engine 最终动作。
- Mastery / Confidence 的变化。
- 为什么选择当前补课节点。

正式学员界面默认折叠这些内部信息。
