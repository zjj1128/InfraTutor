import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { RoadmapData, RoadmapNode } from "../types/roadmap";
import { RoadmapDashboard } from "./RoadmapDashboard";

function node(id: string, status: RoadmapNode["learner_status"]): RoadmapNode {
  return {
    id,
    title: id,
    summary: `${id} summary`,
    type: "concept",
    implementation_status: "pilot",
    availability: "available",
    is_selectable: true,
    learner_status: status,
    progress_status: status === "ready" || status === "locked" ? "no_evidence" : status,
    access_status: status === "locked" ? "locked" : "available",
    can_start_diagnostic_probe: false,
    active_session_id: null,
    prerequisites: [],
    missing_prerequisites: [],
    recommended_next: [],
    learning_objectives: ["objective"],
  };
}

function roadmap(nodes: RoadmapNode[]): RoadmapData {
  return {
    course_id: "course",
    title: "course",
    target_learner: "learner",
    current_stage_id: "stage",
    stage_count: 1,
    pilot_node_count: nodes.length,
    learner_state_available: true,
    active_session: null,
    stages: [
      {
        id: "stage",
        order: 1,
        title: "RDMA",
        goal: "goal",
        exit_capabilities: [],
        availability: "in_progress",
        nodes,
      },
    ],
  };
}

const props = {
  onReset: vi.fn(async () => undefined),
  isResetting: false,
  resetError: null,
  onNavigate: vi.fn(),
  onStartSession: vi.fn(async () => undefined),
  onAbandonSession: vi.fn(async () => undefined),
};

describe("Roadmap session actions", () => {
  it("maps Ready, diagnostic, locked, mastered and active nodes to backend entry actions", async () => {
    const ready = node("ready_node", "ready");
    const diagnostic = { ...node("memory_registration", "locked"), can_start_diagnostic_probe: true };
    const locked = {
      ...node("locked_node", "locked"),
      missing_prerequisites: [{ id: "ready_node", title: "ready_node" }],
    };
    const mastered = node("mastered_node", "mastered");
    const active = { ...node("active_node", "learning"), active_session_id: "session-active" };
    const onStartSession = vi.fn(async () => undefined);
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(
      <RoadmapDashboard
        {...props}
        roadmap={roadmap([ready, diagnostic, locked, mastered, active])}
        onStartSession={onStartSession}
        onNavigate={onNavigate}
      />,
    );

    expect(screen.getByRole("button", { name: "体验诊断" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "体验诊断" }));
    expect(onStartSession).toHaveBeenCalledWith("memory_registration", "diagnostic");

    await user.click(screen.getByRole("button", { name: /ready_node summary/ }));
    await user.click(screen.getByRole("button", { name: "开始学习" }));
    expect(onStartSession).toHaveBeenCalledWith("ready_node", "normal");

    await user.click(screen.getByRole("button", { name: /locked_node summary/ }));
    expect(screen.getByRole("button", { name: "前置知识未满足" })).toBeDisabled();
    expect(screen.getByRole("region", { name: "缺失前置知识" })).toHaveTextContent("ready_node");

    await user.click(screen.getByRole("button", { name: /mastered_node summary/ }));
    await user.click(screen.getByRole("button", { name: "复习" }));
    expect(onStartSession).toHaveBeenCalledWith("mastered_node", "review");

    await user.click(screen.getByRole("button", { name: /active_node summary/ }));
    await user.click(screen.getByRole("button", { name: "继续学习" }));
    expect(onNavigate).toHaveBeenCalledWith("/learn/session-active");
  }, 10_000);

  it("requires explicit choice before replacing an active session", async () => {
    const current = { ...node("current", "learning"), active_session_id: "session-active" };
    const target = node("target", "ready");
    const data = {
      ...roadmap([current, target]),
      active_session: {
        session_id: "session-active",
        target_node_id: "current",
        current_node_id: "current",
        version: 4,
        mode: "normal" as const,
      },
    };
    const user = userEvent.setup();
    render(<RoadmapDashboard {...props} roadmap={data} />);
    await user.click(screen.getByRole("button", { name: /target summary/ }));
    await user.click(screen.getByRole("button", { name: "开始学习" }));
    expect(screen.getByRole("dialog", { name: "已有进行中的学习会话" })).toBeVisible();
    expect(screen.getByRole("button", { name: "继续当前会话" })).toBeVisible();
    expect(screen.getByRole("button", { name: "结束并切换" })).toBeVisible();
  });

  it("keeps Coming Later nodes non-enterable", async () => {
    const planned = {
      ...node("coming", null),
      implementation_status: "planned" as const,
      availability: "coming_later" as const,
      is_selectable: false,
    };
    const user = userEvent.setup();
    render(<RoadmapDashboard {...props} roadmap={roadmap([node("ready", "ready"), planned])} />);
    await user.click(screen.getByRole("button", { name: "全部节点" }));
    expect(screen.getByRole("button", { name: /coming summary/ })).toBeDisabled();
  });
});
