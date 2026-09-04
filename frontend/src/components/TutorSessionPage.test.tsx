import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { TutorSessionSnapshot } from "../types/session";
import { TutorSessionPage } from "./TutorSessionPage";

function snapshot(overrides: Partial<TutorSessionSnapshot> = {}): TutorSessionSnapshot {
  return {
    session_id: "session-1",
    version: 1,
    status: "active",
    mode: "diagnostic",
    target_node: {
      node_id: "memory_registration",
      title: "Memory Registration",
      learner_status: "locked",
      progress_status: "learning",
    },
    current_node: {
      node_id: "device_dma",
      title: "Device DMA",
      learner_status: "partial",
      progress_status: "partial",
    },
    return_stack: [],
    expected_question: {
      question_id: "dma_q3_explain",
      node_id: "device_dma",
      prompt: "请解释 CPU 与 DMA 的职责。",
      response_type: "free_text",
      options: [],
    },
    messages: [
      {
        message_id: "m1",
        sequence_number: 1,
        role: "tutor",
        message_kind: "initial",
        text: '<script>alert("x")</script> 请回答当前问题。',
        question_id: "dma_q3_explain",
        interaction_type: "formal_assessment",
        client_turn_id: null,
        created_at: "2026-09-04T00:00:00Z",
      },
    ],
    available_actions: {
      can_submit_answer: true,
      can_ask_side_question: true,
      can_request_hint: true,
      can_request_answer: true,
      can_report_mastery: true,
      can_abandon: true,
    },
    learner_state_summary: [],
    roadmap_delta: [],
    next_ready_node: null,
    llm_mode: "mock",
    recoverable_error: null,
    debug: {
      session_id: "session-1",
      session_version: 1,
      client_turn_id: null,
      target_node_id: "memory_registration",
      current_node_id: "device_dma",
      expected_question_id: "dma_q3_explain",
      current_assistance_level: "none",
      canonical_assessment_summary: null,
      final_action: "REMEDIATE",
      reason_codes: ["WEAK_PREREQUISITE"],
      remediation_target: "device_dma",
      return_stack: ["memory_registration"],
      state_delta: null,
      state_before: null,
      active_misconception_ids: ["mr_copies_memory_to_hca"],
      resolved_misconception_ids: [],
      decision_trace_id: "trace-1",
      llm_metadata: [],
      llm_mode: "mock",
      recoverable_error_code: null,
      demo_inputs: [{ label: "正确解释", text: "fixture answer", selected_option_id: null }],
    },
    ...overrides,
  };
}

function response(body: TutorSessionSnapshot, ok = true): Response {
  return { ok, status: ok ? 200 : 500, json: async () => body } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TutorSessionPage", () => {
  it("restores transcript and shows target/current remediation context", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(snapshot())));
    render(<TutorSessionPage sessionId="session-1" onNavigate={vi.fn()} />);

    expect(await screen.findByText("当前正在补习：Device DMA")).toBeVisible();
    expect(screen.getAllByText("原始目标：Memory Registration").length).toBeGreaterThan(0);
    expect(screen.getByText(/<script>alert/)).toBeVisible();
    expect(document.querySelector("script")).toBeNull();
  });

  it("switches to side-question mode and restores the main question after submit", async () => {
    const updated = snapshot({
      version: 2,
      messages: [
        ...snapshot().messages,
        { ...snapshot().messages[0], message_id: "m2", sequence_number: 2, role: "learner", text: "完成事件是什么？" },
      ],
    });
    const fetchMock = vi.fn().mockResolvedValueOnce(response(snapshot())).mockResolvedValueOnce(response(updated));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<TutorSessionPage sessionId="session-1" onNavigate={vi.fn()} />);
    await screen.findByRole("textbox", { name: "回答" });
    await user.click(screen.getByRole("button", { name: "我有个问题" }));
    const input = screen.getByRole("textbox", { name: "旁支问题" });
    await user.type(input, "完成事件是什么？");
    await user.click(screen.getByRole("button", { name: "提交问题" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const payload = JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body));
    expect(payload.kind).toBe("SIDE_QUESTION");
    expect(payload.expected_question_id).toBe("dma_q3_explain");
    expect(await screen.findByRole("textbox", { name: "回答" })).toBeVisible();
  });

  it("disables all turn actions while a request is processing", async () => {
    let resolveTurn: ((value: Response) => void) | undefined;
    const pending = new Promise<Response>((resolve) => { resolveTurn = resolve; });
    const fetchMock = vi.fn().mockResolvedValueOnce(response(snapshot())).mockReturnValueOnce(pending);
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<TutorSessionPage sessionId="session-1" onNavigate={vi.fn()} />);
    const input = await screen.findByRole("textbox", { name: "回答" });
    await user.type(input, "DMA answer");
    await user.click(screen.getByRole("button", { name: "提交回答" }));
    expect(screen.getByRole("button", { name: "处理中" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "给我提示" })).toBeDisabled();
    resolveTurn?.(response(snapshot({ version: 2 })));
    await waitFor(() => expect(screen.queryByRole("button", { name: "处理中" })).not.toBeInTheDocument());
  });

  it("submits hint without calling the answer path", async () => {
    const updated = snapshot({ version: 2, debug: { ...snapshot().debug!, current_assistance_level: "light_hint" } });
    const fetchMock = vi.fn().mockResolvedValueOnce(response(snapshot())).mockResolvedValueOnce(response(updated));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<TutorSessionPage sessionId="session-1" onNavigate={vi.fn()} />);
    await screen.findByText("请解释 CPU 与 DMA 的职责。");
    await user.click(screen.getByRole("button", { name: "给我提示" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const payload = JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body));
    expect(payload.kind).toBe("REQUEST_HINT");
    expect(payload.text).toBe("");
  });

  it("requires confirmation before requesting the full answer", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(snapshot()));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(false));
    const user = userEvent.setup();
    render(<TutorSessionPage sessionId="session-1" onNavigate={vi.fn()} />);
    await screen.findByText("请解释 CPU 与 DMA 的职责。");
    await user.click(screen.getByRole("button", { name: "直接讲解" }));
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("不能作为独立掌握证据"));
  });

  it("keeps assessor-failed input available for a new submission", async () => {
    const failed = snapshot({
      recoverable_error: {
        code: "LLM_TIMEOUT",
        message: "timeout",
        source: "assessor",
      },
    });
    const fetchMock = vi.fn().mockResolvedValueOnce(response(snapshot())).mockResolvedValueOnce(response(failed));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<TutorSessionPage sessionId="session-1" onNavigate={vi.fn()} />);
    const input = await screen.findByRole("textbox", { name: "回答" });
    await user.type(input, "my answer");
    await user.click(screen.getByRole("button", { name: "提交回答" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("本轮评估没有保存");
    expect(screen.getByRole("textbox", { name: "回答" })).toHaveValue("my answer");
  });

  it("shows completion and the next ready node", async () => {
    const complete = snapshot({
      status: "completed",
      expected_question: null,
      current_node: { ...snapshot().current_node, node_id: "memory_registration", title: "Memory Registration", learner_status: "mastered", progress_status: "mastered" },
      next_ready_node: { node_id: "lkey_rkey_concept", title: "lkey / rkey", learner_status: "ready", progress_status: "no_evidence" },
      available_actions: {
        can_submit_answer: false,
        can_ask_side_question: false,
        can_request_hint: false,
        can_request_answer: false,
        can_report_mastery: false,
        can_abandon: false,
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(complete)));
    render(<TutorSessionPage sessionId="session-1" onNavigate={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Memory Registration 已掌握" })).toBeVisible();
    expect(screen.getByRole("button", { name: /进入 lkey \/ rkey/ })).toBeVisible();
  });

  it("shows debug fields and fills a mock fixture without auto-submit", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(snapshot()));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<TutorSessionPage sessionId="session-1" onNavigate={vi.fn()} />);
    await user.click(await screen.findByText("Decision Debug"));
    expect(screen.getByText("trace-1")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "正确解释" }));
    expect(screen.getByRole("textbox", { name: "回答" })).toHaveValue("fixture answer");
    expect(fetchMock).toHaveBeenCalledOnce();
  });
});
