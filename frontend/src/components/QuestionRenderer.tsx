import type { QuestionView } from "../types/session";

interface QuestionRendererProps {
  question: QuestionView;
  text: string;
  selectedOptionId: string | null;
  disabled: boolean;
  mode: "answer" | "side_question";
  onTextChange: (value: string) => void;
  onOptionChange: (optionId: string) => void;
  onSubmit: () => void;
}

export function QuestionRenderer({
  question,
  text,
  selectedOptionId,
  disabled,
  mode,
  onTextChange,
  onOptionChange,
  onSubmit,
}: QuestionRendererProps) {
  if (mode === "side_question") {
    return (
      <div className="free-text-input">
        <textarea
          aria-label="旁支问题"
          value={text}
          maxLength={4000}
          disabled={disabled}
          placeholder="输入与当前主题相关的问题"
          onChange={(event) => onTextChange(event.target.value)}
          onKeyDown={(event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && text.trim()) {
              event.preventDefault();
              onSubmit();
            }
          }}
        />
        <span className="character-count">{text.length} / 4000</span>
      </div>
    );
  }

  if (question.response_type === "single_choice") {
    return (
      <fieldset className="choice-list" disabled={disabled}>
        <legend className="sr-only">选择一个答案</legend>
        {question.options.map((option) => (
          <label
            className={selectedOptionId === option.option_id ? "is-selected" : ""}
            key={option.option_id}
          >
            <input
              type="radio"
              name={question.question_id}
              value={option.option_id}
              checked={selectedOptionId === option.option_id}
              onChange={() => onOptionChange(option.option_id)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </fieldset>
    );
  }

  return (
    <div className="free-text-input">
      <textarea
        aria-label="回答"
        value={text}
        maxLength={4000}
        disabled={disabled}
        placeholder="写下你的理解"
        onChange={(event) => onTextChange(event.target.value)}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && text.trim()) {
            event.preventDefault();
            onSubmit();
          }
        }}
      />
      <span className="character-count">{text.length} / 4000</span>
    </div>
  );
}
