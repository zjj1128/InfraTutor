import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { QuestionView } from "../types/session";
import { QuestionRenderer } from "./QuestionRenderer";

const freeTextQuestion: QuestionView = {
  question_id: "q_free",
  node_id: "node",
  prompt: "请解释数据路径",
  response_type: "free_text",
  options: [],
};

const choiceQuestion: QuestionView = {
  question_id: "q_choice",
  node_id: "node",
  prompt: "谁搬运 payload？",
  response_type: "single_choice",
  options: [
    { option_id: "cpu", label: "CPU" },
    { option_id: "dma", label: "DMA 引擎" },
  ],
};

describe("QuestionRenderer", () => {
  it("renders free text, character count, and keyboard submit", async () => {
    const onSubmit = vi.fn();
    const onTextChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <QuestionRenderer
        question={freeTextQuestion}
        text=""
        selectedOptionId={null}
        disabled={false}
        mode="answer"
        onTextChange={onTextChange}
        onOptionChange={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    await user.type(screen.getByRole("textbox", { name: "回答" }), "DMA");
    expect(onTextChange).toHaveBeenCalled();

    rerender(
      <QuestionRenderer
        question={freeTextQuestion}
        text="DMA"
        selectedOptionId={null}
        disabled={false}
        mode="answer"
        onTextChange={onTextChange}
        onOptionChange={vi.fn()}
        onSubmit={onSubmit}
      />,
    );
    await user.type(screen.getByRole("textbox", { name: "回答" }), "{Control>}{Enter}{/Control}");
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(screen.getByText("3 / 4000")).toBeVisible();
  });

  it("renders authoritative stable option IDs", async () => {
    const onOptionChange = vi.fn();
    const user = userEvent.setup();
    render(
      <QuestionRenderer
        question={choiceQuestion}
        text=""
        selectedOptionId={null}
        disabled={false}
        mode="answer"
        onTextChange={vi.fn()}
        onOptionChange={onOptionChange}
        onSubmit={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("radio", { name: "DMA 引擎" }));
    expect(onOptionChange).toHaveBeenCalledWith("dma");
  });

  it("renders learner-facing content as text rather than raw HTML", () => {
    render(
      <QuestionRenderer
        question={{ ...freeTextQuestion, prompt: '<img src=x onerror="alert(1)">' }}
        text=""
        selectedOptionId={null}
        disabled={false}
        mode="answer"
        onTextChange={vi.fn()}
        onOptionChange={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
    expect(document.querySelector("img")).toBeNull();
  });
});
