import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { RoadmapData, RoadmapNode, RoadmapStage } from "./types/roadmap";

const stageNames = [
  "Shell / Slurm / C 基础",
  "HIP / DCU",
  "InfiniBand / RDMA 理论",
  "RDMA Verbs",
  "MPI",
  "UCX",
  "RCCL",
  "网络数据分析",
  "网络设计与综合性能优化",
];

function node(overrides: Partial<RoadmapNode>): RoadmapNode {
  return {
    id: "planned_node",
    title: "后续知识节点",
    summary: "后续阶段内容",
    type: "concept",
    implementation_status: "planned",
    availability: "coming_later",
    is_selectable: false,
    learner_status: null,
    progress_status: null,
    access_status: null,
    can_start_diagnostic_probe: false,
    prerequisites: [],
    missing_prerequisites: [],
    recommended_next: [],
    learning_objectives: [],
    ...overrides,
  };
}

function stage(title: string, index: number): RoadmapStage {
  const current = index === 2;
  return {
    id: current ? "stage_3_ib_rdma_theory" : `stage_${index + 1}`,
    order: index + 1,
    title,
    goal: current ? "理解 HCA、DMA、内存注册和 RDMA 数据路径。" : `${title} 阶段目标`,
    exit_capabilities: [],
    availability: current ? "in_progress" : "coming_later",
    nodes: current
      ? [
          node({
            id: "device_dma",
            title: "Device DMA",
            summary: "理解设备 DMA 数据搬运。",
            implementation_status: "pilot",
            availability: "available",
            is_selectable: true,
            learner_status: "ready",
            learning_objectives: ["区分 CPU 配置传输与设备执行数据搬运"],
          }),
          node({
            id: "memory_registration",
            title: "RDMA Memory Registration",
            summary: "理解 MR 的页固定、地址转换与保护。",
            implementation_status: "pilot",
            availability: "available",
            is_selectable: true,
            learner_status: "locked",
            prerequisites: [{ id: "device_dma", title: "Device DMA" }],
            missing_prerequisites: [{ id: "device_dma", title: "Device DMA" }],
            recommended_next: [{ id: "lkey_rkey_concept", title: "lkey / rkey Concept" }],
            learning_objectives: ["解释为什么 HCA 访问用户 buffer 前需要注册"],
          }),
          node({ id: "transport", title: "RC / UD 等传输概念" }),
        ]
      : [node({ id: `planned_${index}`, title: `${title} 知识节点` })],
  };
}

const roadmapFixture: RoadmapData = {
  course_id: "infratutor",
  title: "高速互联新人培训路线",
  target_learner: "计算机专业新人",
  current_stage_id: "stage_3_ib_rdma_theory",
  stage_count: 9,
  pilot_node_count: 8,
  learner_state_available: true,
  stages: stageNames.map(stage),
};

function response(body: RoadmapData, ok = true): Response {
  return { ok, status: ok ? 200 : 503, json: async () => body } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("roadmap application", () => {
  it("shows all nine stages and exposes only pilot node details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(roadmapFixture)));
    const user = userEvent.setup();

    render(<App />);

    expect(await screen.findByRole("heading", { name: "InfiniBand / RDMA 理论" })).toBeVisible();
    for (const name of stageNames) {
      expect(screen.getAllByText(name).length).toBeGreaterThan(0);
    }

    expect(screen.getAllByText("RDMA Memory Registration").length).toBeGreaterThan(0);
    expect(screen.getByText("解释为什么 HCA 访问用户 buffer 前需要注册")).toBeVisible();
    expect(screen.getAllByText("LOCKED").length).toBeGreaterThan(0);
    expect(screen.getByRole("region", { name: "缺失前置知识" })).toHaveTextContent(
      "Device DMA",
    );
    expect(screen.getByRole("button", { name: "学习会话暂未开放" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /全部节点/ }));
    const futureNode = screen.getByRole("button", { name: /RC \/ UD 等传输概念/ });
    expect(futureNode).toBeDisabled();
    expect(screen.getAllByText("Coming Later").length).toBeGreaterThan(0);
  });

  it("keeps a failed roadmap request recoverable", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(roadmapFixture, false))
      .mockResolvedValueOnce(response(roadmapFixture));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("课程路线暂时无法加载");
    await user.click(screen.getByRole("button", { name: /重新加载/ }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "InfiniBand / RDMA 理论" })).toBeVisible();
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("confirms a Golden Path reset and refreshes learner statuses", async () => {
    const goldenRoadmap: RoadmapData = {
      ...roadmapFixture,
      stages: roadmapFixture.stages.map((item) => ({
        ...item,
        nodes: item.nodes.map((entry) =>
          entry.id === "device_dma" ? { ...entry, learner_status: "partial" } : entry,
        ),
      })),
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(roadmapFixture))
      .mockResolvedValueOnce(response(roadmapFixture))
      .mockResolvedValueOnce(response(goldenRoadmap));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    const user = userEvent.setup();

    render(<App />);
    await screen.findByRole("heading", { name: "InfiniBand / RDMA 理论" });
    await user.click(screen.getByRole("button", { name: /Golden Path/ }));

    await waitFor(() => expect(screen.getByText("PARTIAL")).toBeVisible());
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/demo/reset",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
