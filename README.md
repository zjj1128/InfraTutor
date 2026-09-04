# InfraTutor V0.1

InfraTutor 是面向高速互联新人的自适应学习 Web App。当前仓库已完成 `IMPLEMENTATION_PLAN.md` 的 Phase 0 至 Phase 5：课程图、Learner State、确定性 Tutor Engine、LLM Gateway，以及可在浏览器手动完成 Golden Path 的 Tutor Session 已经就绪。

## 当前能力

- React + TypeScript + Vite Roadmap，展示完整九阶段路线。
- Stage 3 的 8 个 V0.1 pilot 节点可查看目标和前置关系。
- planned 节点显示 `Coming Later`，不进入空白课程。
- Roadmap 展示 `LOCKED / READY / LEARNING / PARTIAL / MASTERED / REVIEW NEEDED`，锁定节点列出缺失前置。
- 固定 `default_learner`、Clean / Golden Path Seed 和 SQLite 持久化。
- Learner、Node State、不可变 Evidence、Misconception 实体与 repository。
- 确定性的 Evidence 权重、Mastery、Confidence、Mastered 门槛和 prerequisite 闭包。
- 学习进度与节点访问性分离，Roadmap 同时返回 effective status、progress、access 和 probe 能力。
- 持久化 LearningSession、return stack 与 DecisionTrace。
- 按 P0-P7 优先级运行的确定性 TutorPolicy、Assessment Planner 和 remediation selector。
- 每个 session/target 最多一次的低权重 target diagnostic probe。
- 固定 Structured Assessment fixtures 驱动的 Golden Path 后端演示。
- 严格 Pydantic Structured Output、语义白名单校验和后端 rubric 重算。
- 模型无关 `LLMGateway`、无网络 Mock Provider 和 OpenAI Responses Live Adapter。
- 明确的 `LearnerTurnKind` 路由、Assessor/Teacher 分离及一次 repair retry。
- 安全的 LLM 调用 metadata 持久化，不记录 Key、完整 prompt 或完整回答。
- FastAPI 健康检查、`GET /api/roadmap`、`GET /api/learner`、`GET /api/llm/status` 与 reset API。
- Pydantic 课程模型与跨 YAML 校验。
- prerequisite 环、重复 ID、未知引用、assessment / misconception 关联校验。
- Course Graph 的节点、前置闭包、解锁和推荐后继查询。
- 开发态 Roadmap 提供带确认的 Clean / Golden Path reset。
- 单用户 active Session 的创建、恢复、结束、递增版本和 `client_turn_id` 幂等提交。
- 持久化 Tutor Turn、消息 transcript、QuestionView 和刷新恢复。
- `/learn/:sessionId` Tutor 页面、自由文本/单选 renderer、补课路线提示和可折叠 Debug Panel。
- Roadmap 的开始、继续、诊断、复习和锁定按钮由后端状态驱动。

## 环境要求

- Python 3.11+
- Node.js 22.12+
- [uv](https://docs.astral.sh/uv/)
- npm 10+

## 安装

```bash
cp .env.example .env
make setup
```

也可以分别安装：

```bash
uv sync --extra dev
npm install --prefix frontend
```

## 本地启动

一条命令同时启动前后端：

```bash
make dev
```

- Web App: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/health`

也可以在两个终端分别运行：

```bash
make backend
make frontend
```

`make dev` 会打印实际 Frontend URL、Backend URL、LLM mode 和当前数据库 seed。若配置端口已被占用，命令会指出具体端口并退出，不会静默切换或终止未知进程。

开发环境中前端始终请求相对路径 `/api`，Vite 会将它代理到配置的 FastAPI。端口可在根目录 `.env` 中调整：

```text
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_HOST=0.0.0.0
FRONTEND_PORT=5173
```

开发服务器监听 `0.0.0.0`。在 WSL2 中启动后，Windows 浏览器通常可直接访问 `make dev` 打印的 `127.0.0.1` 地址：Windows 的 localhost forwarding 会转发到 WSL。若无法访问，先确认命令没有报告端口占用，再检查 `%UserProfile%\.wslconfig` 是否禁用了 `localhostForwarding`；也可用 `hostname -I` 显示的 WSL 地址加当前 `FRONTEND_PORT` 访问。

## 校验与测试

```bash
make validate-curriculum
make demo-tutor-engine
make demo-llm-mock
make demo-tutor-session
make test
make lint
make build
```

单独运行：

```bash
.venv/bin/pytest
npm --prefix frontend test
```

测试和 `make demo-llm-mock` 不访问真实 LLM 或外部网络。`make smoke-llm-live` 是显式可选命令，不属于默认测试或 CI。

## 课程校验范围

后端同时加载：

- `curriculum/roadmap.yaml`
- `curriculum/v0_1_rdma_memory_registration.yaml`
- `curriculum/v0_1_assessments.yaml`

启动和 `make validate-curriculum` 会检查：

- stage、node、assessment、criterion、misconception ID 唯一。
- node 的 stage、prerequisite、recommended next、reinforces 引用存在。
- prerequisite 图无环，并在失败时给出环路径。
- pilot 节点与 roadmap 的类型、前置和实现状态一致。
- assessment 与所属 node、rubric misconception、选项互相匹配。
- target diagnostic probe、remediation node 与 seed 引用有效。
- Mastered 所需 assessment 类型与独立题目数量在当前课程集合中可达到。

任一校验失败都会阻止应用带着不完整课程图启动。

## 项目结构

```text
backend/
  app/
    api/             # 薄 HTTP 路由
    core/            # 环境配置
    curriculum/      # Pydantic 模型、加载、校验、图查询
    db/              # SQLAlchemy / SQLite 初始化
    learner/         # 实体、repository、Seed、状态规则与 API DTO
    tutor/           # Engine Session、Trace、Policy、Planner、selector 与 fixtures
    llm/             # contracts、Gateway、Provider、校验、应用服务与 metadata
    sessions/        # Tutor Session API 编排、Turn/Message 持久化与前端 DTO
  tests/
frontend/
  src/
    api/             # Roadmap API client
    components/      # Roadmap dashboard
    types/           # API DTO 类型
curriculum/          # 人工课程事实来源
docs/                # 产品与领域设计
schemas/             # 由 Pydantic 生成的 LLM schema 与 learner schema
```

## API

### `GET /api/health`

确认 API、课程和数据库启动完成。

### `GET /api/roadmap`

返回按顺序排列的九个 Stage、节点实现范围、真实 `learner_status`、底层 `progress_status`、`access_status`、probe 能力、缺失前置、pilot 学习目标和推荐后继。

### `GET /api/learner`

返回固定 `default_learner` 的 profile、逐节点状态、Evidence ID 和 misconception 状态。

### `GET /api/llm/status`

只返回 mode、provider、模型/Key 是否已配置、`live_ready` 和可选的最后错误码；不会返回 Key 或 base URL。

### Tutor Session API

- `POST /api/tutor/sessions`：按 `normal / diagnostic / review` 创建或恢复会话。
- `GET /api/tutor/sessions/active`：返回默认 learner 的 active Session。
- `GET /api/tutor/sessions/{session_id}`：返回可直接渲染的 Snapshot 与 transcript。
- `POST /api/tutor/sessions/{session_id}/turns`：提交显式 `LearnerTurnKind`。
- `POST /api/tutor/sessions/{session_id}/abandon`：保留 Evidence 并结束会话。

Turn 请求必须携带当前 `version`、`expected_question_id` 和唯一 `client_turn_id`。网络中断重试复用同一个 ID，后端直接重放第一次持久化响应，不重复调用模型或写 Evidence。

### `POST /api/demo/reset`

开发态重置为 Clean Seed：

```bash
curl -X POST http://127.0.0.1:8000/api/demo/reset \
  -H 'Content-Type: application/json' \
  -d '{"seed":"clean"}'
```

将 `clean` 替换为 `golden_path` 可载入 Golden Path Seed。reset 会清除当前本地学习状态并在单个事务中重建默认 learner；Web UI 调用前会要求确认。

## 配置

默认配置见 `.env.example`。基础配置：

- `APP_ENV`
- `DATABASE_URL`
- `CORS_ORIGINS`
- `ENABLE_DEBUG_PANEL`
- `BACKEND_HOST` / `BACKEND_PORT`
- `FRONTEND_HOST` / `FRONTEND_PORT`
- `CURRICULUM_DIR`（可选，默认是仓库的 `curriculum/`）

LLM 默认使用无需 Key 和网络的 Mock：

```text
LLM_MODE=mock
LLM_PROVIDER=openai
```

启用 Live 时设置 `LLM_MODE=live`、`LLM_API_KEY`、`LLM_ASSESSOR_MODEL` 和
`LLM_TEACHER_MODEL`。`LLM_BASE_URL` 可选；自定义 endpoint 必须支持 Responses API 与
Structured Outputs，Adapter 不会偷偷回退到 Chat Completions。Assessor 和 Teacher 模型分开配置，
也可以填同一个 model ID。

可靠性参数：

- `LLM_TIMEOUT_SECONDS=30`：单次传输超时。
- `LLM_TRANSPORT_MAX_RETRIES=1`：SDK 对超时、连接、429/部分 5xx 的传输重试。
- `LLM_REPAIR_RETRIES=1`：结构或课程语义校验失败后的修复重试。

Live 配置缺失不会阻止应用启动；真正调用时会返回 `LLM_NOT_CONFIGURED`，不会静默降级为 Mock。

## Tutor Engine 后端演示

```bash
make demo-tutor-engine
```

命令使用内存 SQLite、Golden Path Seed 和固定结构化 assessment fixtures，打印 MR probe、
DMA/Pinned 补课、return stack、返回 MR、证据不足继续评估、最终解锁和完整 trace 摘要。
它不访问网络或模型。

## LLM Mock 演示

```bash
make demo-llm-mock
```

命令用自然语言“MR 会把内存复制到 HCA。”跑通 Assessor、后端 canonical 评估、Tutor
Engine、Teacher 和 metadata，最终稳定得到 `REMEDIATE device_dma`。可选 Live 连通性检查：

```bash
make smoke-llm-live
```

缺少 Live 配置时该命令明确报告“未运行”，且不会输出 Key。

## Tutor Session 演示与手动 Golden Path

纯 API/应用层演示不访问网络：

```bash
make demo-tutor-session
```

浏览器中先 Reset 到 Golden Path，选择 Memory Registration 并点击“体验诊断”。按 Debug Panel 的 Mock Fixtures 填入典型误解和各节点正确解释/迁移答案，即可依次观察 Device DMA、Pinned Memory、返回 MR、MR Mastered 和 lkey/rkey Ready。Fixture 按钮只填充输入框，不会自动提交，Live 模式不显示。

## 后续 Phase

- Phase 6：Golden Path 浏览器 E2E。
- Phase 7：可靠性与体验收尾。

课程与教学规则以 `DECISIONS.md`、领域文档和 `IMPLEMENTATION_PLAN.md` 为准。

Phase 6 的 Playwright 浏览器自动化 E2E 尚未实现；Phase 5 使用后端 API 集成测试、React 组件测试和人工浏览器流程验收。
