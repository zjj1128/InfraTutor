# InfraTutor V0.1 项目设计包

InfraTutor 是一个面向高速互联部门新人的 AI 自适应学习 Web App。它不是“部门文档 + 聊天框”，而是由课程知识图谱、学习者状态、结构化评估和教学策略共同驱动的 Tutor 系统。

本设计包的用途是：在正式编码前，先把产品目标、V0.1 范围、课程结构、数据模型、LLM 契约、教学策略、黄金路径和验收标准固定下来，避免 Codex 自行脑补需求后做成普通 AI 问答网站。

## 已确认的核心决定

- 默认学习者：刚毕业、具备普通计算机基础，但几乎没有 HPC / 高速互联经验的计算机专业新人。
- 完整培训路线：共 9 个阶段，覆盖 Shell / Slurm / C、HIP / DCU、InfiniBand / RDMA、RDMA Verbs、MPI、UCX、RCCL、网络数据分析、网络设计与综合性能优化。
- V0.1 产品形态：本地 WSL 单用户 Web App。
- V0.1 教学切片：UI 展示完整九阶段路线，但真正跑通“虚拟/物理内存 → DMA → Pinned Memory → HCA → RDMA 数据路径 → Memory Registration → lkey/rkey 入门”。
- Tutor 拥有学习流程控制权，可以阻止跳级、回退前置知识、追加问题或安排补课。
- “学会”由证据决定，不以“看过课程”或学生自报完成为准。
- “教什么”由人工课程设计控制；“怎么讲”可由 LLM 动态生成。
- V0.1 不接入部门内部资料，不做 RAG、集群 SSH、Slurm 自动执行、多 Agent、自训练或本地模型。
- 第一核心验收目标：跑通 Golden Path，系统能识别“MR 会把内存复制到 HCA”这一误解，回退补习 DMA / Pinned Memory，再回到 MR 并完成掌握判定。

## 建议阅读顺序

1. `DECISIONS.md`
2. `PROJECT_SPEC.md`
3. `ARCHITECTURE.md`
4. `docs/COURSE_DESIGN.md`
5. `docs/LEARNER_STATE.md`
6. `docs/LLM_CONTRACT.md`
7. `docs/TUTOR_ENGINE.md`
8. `docs/MVP_USER_FLOW.md`
9. `docs/ACCEPTANCE_TESTS.md`
10. `IMPLEMENTATION_PLAN.md`
11. `AGENTS.md`
12. `CODEX_START_PROMPT.md`

## 目录说明

```text
InfraTutor_V0.1_Design_Package/
├── README.md
├── DECISIONS.md
├── PROJECT_SPEC.md
├── ARCHITECTURE.md
├── IMPLEMENTATION_PLAN.md
├── AGENTS.md
├── CODEX_START_PROMPT.md
├── .env.example
├── docs/
│   ├── COURSE_DESIGN.md
│   ├── LEARNER_STATE.md
│   ├── LLM_CONTRACT.md
│   ├── TUTOR_ENGINE.md
│   ├── MVP_USER_FLOW.md
│   └── ACCEPTANCE_TESTS.md
├── curriculum/
│   ├── roadmap.yaml
│   ├── v0_1_rdma_memory_registration.yaml
│   └── v0_1_assessments.yaml
├── schemas/
│   ├── assessment_output.schema.json
│   ├── tutor_message_output.schema.json
│   └── learner_state.schema.json
└── prompts/
    ├── assessor_system.md
    └── teacher_system.md
```

## V0.1 的灵魂

V0.1 只需要证明下面这条链成立：

```text
学生回答
   ↓
LLM 按 rubric 做结构化评估
   ↓
Tutor Engine 读取评估、Learner State 与课程前置关系
   ↓
确定 ASK / HINT / REMEDIATE / ADVANCE 等动作
   ↓
更新学习证据和状态
   ↓
LLM 按确定后的动作生成对学生的话
   ↓
继续下一轮
```

LLM 负责语言理解、诊断辅助和表达；Tutor Engine 才拥有最终教学决策权。

## 交给 Codex 前的操作

把整个目录复制为项目根目录，或放进空仓库。随后将 `CODEX_START_PROMPT.md` 中的提示词交给 Codex。第一轮只实现 Phase 0 和 Phase 1，不要一次性让 Codex 完成全部系统。
