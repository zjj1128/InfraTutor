import {
  AlertCircle,
  ArrowRight,
  BookOpenCheck,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  CircleDot,
  CircleOff,
  History,
  Layers3,
  LockKeyhole,
  Network,
  Play,
  RotateCcw,
  Route,
  Target,
} from "lucide-react";
import { useMemo, useState } from "react";

import type {
  LearnerStatus,
  NodeAvailability,
  RoadmapData,
  RoadmapNode,
  RoadmapStage,
  SeedName,
} from "../types/roadmap";
import type { EntryMode } from "../types/session";

interface RoadmapDashboardProps {
  roadmap: RoadmapData;
  onReset: (seed: SeedName) => Promise<void>;
  isResetting: boolean;
  resetError: string | null;
  onNavigate: (path: string) => void;
  onStartSession: (nodeId: string, mode: EntryMode) => Promise<void>;
  onAbandonSession: (sessionId: string, version: number) => Promise<void>;
}

type NodeFilter = "pilot" | "all";

const availabilityLabel: Record<NodeAvailability, string> = {
  available: "可学习",
  supporting: "基础说明",
  coming_later: "Coming Later",
};

const learnerStatusLabel: Record<LearnerStatus, string> = {
  locked: "LOCKED",
  ready: "READY",
  learning: "LEARNING",
  partial: "PARTIAL",
  mastered: "MASTERED",
  review_needed: "REVIEW_NEEDED",
};

function StageRail({
  stages,
  selectedStageId,
  onSelect,
}: {
  stages: RoadmapStage[];
  selectedStageId: string;
  onSelect: (stageId: string) => void;
}) {
  return (
    <nav className="stage-rail" aria-label="九阶段课程路线">
      <div className="rail-heading">
        <Route size={18} aria-hidden="true" />
        <span>完整路线</span>
      </div>
      <ol className="stage-list">
        {stages.map((stage) => {
          const active = stage.id === selectedStageId;
          return (
            <li key={stage.id}>
              <button
                className={`stage-button ${active ? "is-active" : ""}`}
                type="button"
                aria-current={active ? "step" : undefined}
                onClick={() => onSelect(stage.id)}
              >
                <span className="stage-index">{String(stage.order).padStart(2, "0")}</span>
                <span className="stage-copy">
                  <strong>{stage.title}</strong>
                  <span>
                    {stage.availability === "in_progress" ? "V0.1 进行中" : "Coming Later"}
                  </span>
                </span>
                {stage.availability === "in_progress" ? (
                  <CircleDashed className="stage-state active" size={17} aria-hidden="true" />
                ) : (
                  <LockKeyhole className="stage-state" size={16} aria-hidden="true" />
                )}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function NodeStateIcon({ node }: { node: RoadmapNode }) {
  if (node.availability === "coming_later" || node.learner_status === "locked") {
    return <LockKeyhole size={17} aria-hidden="true" />;
  }
  if (node.availability === "supporting") {
    return <Layers3 size={18} aria-hidden="true" />;
  }
  if (node.learner_status === "mastered") {
    return <CheckCircle2 size={18} aria-hidden="true" />;
  }
  if (node.learner_status === "review_needed") {
    return <History size={18} aria-hidden="true" />;
  }
  if (node.learner_status === "learning" || node.learner_status === "partial") {
    return <CircleDot size={18} aria-hidden="true" />;
  }
  return <BookOpenCheck size={18} aria-hidden="true" />;
}

function NodeList({
  nodes,
  selectedNodeId,
  onSelect,
}: {
  nodes: RoadmapNode[];
  selectedNodeId: string | null;
  onSelect: (node: RoadmapNode) => void;
}) {
  return (
    <ol className="node-list" aria-label="知识节点">
      {nodes.map((node, index) => {
        const selected = node.id === selectedNodeId;
        const statusLabel =
          node.availability === "coming_later"
            ? availabilityLabel.coming_later
            : node.learner_status
              ? learnerStatusLabel[node.learner_status]
              : availabilityLabel[node.availability];
        return (
          <li className="node-row" key={node.id}>
            <span className="node-sequence" aria-hidden="true">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span
              className={`node-marker ${node.availability} ${node.learner_status ?? ""}`}
            >
              <NodeStateIcon node={node} />
            </span>
            <button
              type="button"
              className={`node-button ${selected ? "is-selected" : ""}`}
              disabled={!node.is_selectable}
              onClick={() => onSelect(node)}
            >
              <span className="node-main">
                <strong>{node.title}</strong>
                <span>{node.summary}</span>
              </span>
              <span
                className={`availability-label ${
                  node.availability === "coming_later"
                    ? "coming_later"
                    : (node.learner_status ?? node.availability)
                }`}
              >
                {statusLabel}
              </span>
              {node.is_selectable && <ChevronRight size={18} aria-hidden="true" />}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function startMode(node: RoadmapNode): EntryMode {
  if (node.learner_status === "mastered" || node.learner_status === "review_needed") {
    return "review";
  }
  if (node.learner_status === "locked" && node.can_start_diagnostic_probe) {
    return "diagnostic";
  }
  return "normal";
}

function actionLabel(node: RoadmapNode): string {
  if (node.active_session_id) return "继续学习";
  if (node.learner_status === "mastered" || node.learner_status === "review_needed") {
    return "复习";
  }
  if (node.learner_status === "locked") {
    return node.can_start_diagnostic_probe ? "体验诊断" : "前置知识未满足";
  }
  return "开始学习";
}

function NodeDetails({
  node,
  isStarting,
  onStart,
}: {
  node: RoadmapNode | null;
  isStarting: boolean;
  onStart: (node: RoadmapNode, mode: EntryMode) => void;
}) {
  if (!node) {
    return (
      <aside className="node-details empty-state">
        <LockKeyhole size={24} aria-hidden="true" />
        <strong>该阶段尚未开放</strong>
        <span>Coming Later</span>
      </aside>
    );
  }

  return (
    <aside className="node-details" aria-label={`${node.title} 详情`}>
      <div className="detail-kicker">
        <Target size={16} aria-hidden="true" />
        V0.1 学习节点
      </div>
      <h3>{node.title}</h3>
      {node.learner_status && (
        <div className={`detail-status ${node.learner_status}`}>
          <NodeStateIcon node={node} />
          <span>{learnerStatusLabel[node.learner_status]}</span>
        </div>
      )}
      <p className="detail-summary">{node.summary}</p>

      {node.learner_status === "locked" && (
        <section className="locked-reasons" aria-label="缺失前置知识">
          <div>
            <CircleOff size={16} aria-hidden="true" />
            <strong>缺少前置知识</strong>
          </div>
          <ul>
            {node.missing_prerequisites.map((item) => (
              <li key={item.id}>{item.title}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="detail-section">
        <h4>学习目标</h4>
        <ul>
          {node.learning_objectives.map((objective) => (
            <li key={objective}>
              <CheckCircle2 size={15} aria-hidden="true" />
              <span>{objective}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="detail-section">
        <h4>前置节点</h4>
        <div className="reference-list">
          {node.prerequisites.length > 0 ? (
            node.prerequisites.map((item) => <span key={item.id}>{item.title}</span>)
          ) : (
            <span>无</span>
          )}
        </div>
      </section>

      {node.recommended_next.length > 0 && (
        <section className="detail-section next-section">
          <h4>推荐后继</h4>
          {node.recommended_next.map((item) => (
            <div className="next-node" key={item.id}>
              <ArrowRight size={15} aria-hidden="true" />
              {item.title}
            </div>
          ))}
        </section>
      )}

      <button
        className="session-placeholder"
        type="button"
        disabled={isStarting || (node.learner_status === "locked" && !node.can_start_diagnostic_probe)}
        title={node.learner_status === "locked" && !node.can_start_diagnostic_probe ? "请先完成缺失的前置知识" : undefined}
        onClick={() => onStart(node, startMode(node))}
      >
        <Play size={16} aria-hidden="true" />
        {isStarting ? "正在进入" : actionLabel(node)}
      </button>
    </aside>
  );
}

function DevResetControl({
  onReset,
  isResetting,
}: {
  onReset: (seed: SeedName) => Promise<void>;
  isResetting: boolean;
}) {
  const reset = (seed: SeedName, label: string) => {
    if (window.confirm(`确认重置为 ${label}？当前本地学习状态将被清除。`)) {
      void onReset(seed);
    }
  };

  return (
    <div className="dev-reset" aria-label="开发态学习状态重置">
      <span>DEV RESET</span>
      <button
        type="button"
        disabled={isResetting}
        onClick={() => reset("clean", "Clean Seed")}
      >
        <RotateCcw size={14} aria-hidden="true" />
        Clean
      </button>
      <button
        type="button"
        disabled={isResetting}
        onClick={() => reset("golden_path", "Golden Path Seed")}
      >
        <RotateCcw size={14} aria-hidden="true" />
        Golden Path
      </button>
    </div>
  );
}

export function RoadmapDashboard({
  roadmap,
  onReset,
  isResetting,
  resetError,
  onNavigate,
  onStartSession,
  onAbandonSession,
}: RoadmapDashboardProps) {
  const [selectedStageId, setSelectedStageId] = useState(roadmap.current_stage_id);
  const [filter, setFilter] = useState<NodeFilter>("pilot");
  const currentStage =
    roadmap.stages.find((stage) => stage.id === selectedStageId) ?? roadmap.stages[0];

  const initialNode = currentStage.nodes.find((node) => node.id === "memory_registration") ??
    currentStage.nodes.find((node) => node.is_selectable) ??
    null;
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(initialNode?.id ?? null);
  const [isStarting, setIsStarting] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [pendingSwitch, setPendingSwitch] = useState<{
    node: RoadmapNode;
    mode: EntryMode;
  } | null>(null);

  const visibleNodes = useMemo(() => {
    if (filter === "all") {
      return currentStage.nodes;
    }
    const scoped = currentStage.nodes.filter((node) => node.availability !== "coming_later");
    return scoped.length > 0 ? scoped : currentStage.nodes;
  }, [currentStage, filter]);

  const selectedNode =
    currentStage.nodes.find((node) => node.id === selectedNodeId && node.is_selectable) ?? null;

  const handleStageSelect = (stageId: string) => {
    const nextStage = roadmap.stages.find((stage) => stage.id === stageId);
    if (!nextStage) return;
    setSelectedStageId(stageId);
    setSelectedNodeId(nextStage.nodes.find((node) => node.is_selectable)?.id ?? null);
    if (!nextStage.nodes.some((node) => node.availability !== "coming_later")) {
      setFilter("all");
    }
  };

  const openSession = async (node: RoadmapNode, mode: EntryMode) => {
    if (node.active_session_id) {
      onNavigate(`/learn/${node.active_session_id}`);
      return;
    }
    if (roadmap.active_session && roadmap.active_session.target_node_id !== node.id) {
      setPendingSwitch({ node, mode });
      return;
    }
    setIsStarting(true);
    setSessionError(null);
    try {
      await onStartSession(node.id, mode);
    } catch (reason: unknown) {
      setSessionError(reason instanceof Error ? reason.message : "学习会话启动失败");
    } finally {
      setIsStarting(false);
    }
  };

  const abandonAndSwitch = async () => {
    if (!pendingSwitch || !roadmap.active_session) return;
    if (!window.confirm("确认结束当前会话并切换目标？已有学习证据会保留。")) return;
    setIsStarting(true);
    setSessionError(null);
    try {
      await onAbandonSession(roadmap.active_session.session_id, roadmap.active_session.version);
      await onStartSession(pendingSwitch.node.id, pendingSwitch.mode);
    } catch (reason: unknown) {
      setSessionError(reason instanceof Error ? reason.message : "切换学习会话失败");
      setPendingSwitch(null);
      setIsStarting(false);
    }
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            <Network size={23} />
          </span>
          <div>
            <strong>InfraTutor</strong>
            <span>高速互联学习路径</span>
          </div>
        </div>
        <div className="topbar-meta">
          <span className="service-state">
            <span aria-hidden="true" />
            本地课程已加载
          </span>
          <span>{roadmap.stage_count} STAGES</span>
        </div>
      </header>

      <div className="mobile-stage-picker">
        <label htmlFor="stage-select">课程阶段</label>
        <select
          id="stage-select"
          value={selectedStageId}
          onChange={(event) => handleStageSelect(event.target.value)}
        >
          {roadmap.stages.map((stage) => (
            <option value={stage.id} key={stage.id}>
              {stage.order}. {stage.title}
            </option>
          ))}
        </select>
      </div>

      <main className="roadmap-layout">
        <StageRail
          stages={roadmap.stages}
          selectedStageId={selectedStageId}
          onSelect={handleStageSelect}
        />

        <section className="stage-workspace">
          <div className="stage-header">
            <div>
              <div className="stage-eyebrow">STAGE {String(currentStage.order).padStart(2, "0")}</div>
              <h1>{currentStage.title}</h1>
              <p>{currentStage.goal}</p>
            </div>
            <div className="stage-count">
              <strong>{currentStage.nodes.length}</strong>
              <span>知识节点</span>
            </div>
          </div>

          <div className="workspace-toolbar">
            <div className="segmented-control" aria-label="节点范围">
              <button
                type="button"
                className={filter === "pilot" ? "is-active" : ""}
                aria-pressed={filter === "pilot"}
                onClick={() => setFilter("pilot")}
              >
                当前切片
              </button>
              <button
                type="button"
                className={filter === "all" ? "is-active" : ""}
                aria-pressed={filter === "all"}
                onClick={() => setFilter("all")}
              >
                全部节点
              </button>
            </div>
            <div className="toolbar-actions">
              <div className="legend" aria-label="学习状态图例">
                <span><i className="ready" />Ready</span>
                <span><i className="learning" />Learning</span>
                <span><i className="partial" />Partial</span>
                <span><i className="mastered" />Mastered</span>
                <span><i className="review_needed" />Review</span>
                <span><i className="locked" />Locked</span>
              </div>
              {import.meta.env.DEV && (
                <DevResetControl onReset={onReset} isResetting={isResetting} />
              )}
            </div>
          </div>

          {resetError && (
            <div className="inline-error" role="alert">
              <AlertCircle size={16} aria-hidden="true" />
              {resetError}
            </div>
          )}

          {sessionError && (
            <div className="inline-error" role="alert">
              <AlertCircle size={16} aria-hidden="true" />
              {sessionError}
            </div>
          )}

          <div className="node-workspace">
            <div className="node-column">
              <div className="column-heading">
                <span>学习序列</span>
                <span>{visibleNodes.length} NODES</span>
              </div>
              <NodeList
                nodes={visibleNodes}
                selectedNodeId={selectedNodeId}
                onSelect={(node) => setSelectedNodeId(node.id)}
              />
            </div>
            <NodeDetails
              node={selectedNode}
              isStarting={isStarting}
              onStart={(node, mode) => void openSession(node, mode)}
            />
          </div>
        </section>
      </main>

      {pendingSwitch && roadmap.active_session && (
        <div className="dialog-backdrop" role="presentation">
          <section className="session-dialog" role="dialog" aria-modal="true" aria-labelledby="active-session-title">
            <h2 id="active-session-title">已有进行中的学习会话</h2>
            <p>继续当前会话，或明确结束后切换到 {pendingSwitch.node.title}。</p>
            <div>
              <button type="button" onClick={() => onNavigate(`/learn/${roadmap.active_session!.session_id}`)}>
                继续当前会话
              </button>
              <button className="danger" type="button" disabled={isStarting} onClick={() => void abandonAndSwitch()}>
                结束并切换
              </button>
              <button type="button" onClick={() => setPendingSwitch(null)}>取消</button>
            </div>
          </section>
        </div>
      )}

      <footer className="statusbar">
        <span>CURRICULUM v0.1</span>
        <span>{roadmap.pilot_node_count} 个已实现节点</span>
        <span>LEARNER STATE · PERSISTED</span>
      </footer>
    </div>
  );
}
