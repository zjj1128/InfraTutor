import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  CircleHelp,
  Lightbulb,
  LoaderCircle,
  LogOut,
  MessageCircleQuestion,
  Network,
  Send,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  APIError,
  abandonTutorSession,
  fetchTutorSession,
  startTutorSession,
  submitTutorTurn,
} from "../api/client";
import type {
  DemoInput,
  LearnerTurnKind,
  SubmitTurnPayload,
  TutorSessionSnapshot,
} from "../types/session";
import { DebugPanel } from "./DebugPanel";
import { QuestionRenderer } from "./QuestionRenderer";

interface TutorSessionPageProps {
  sessionId: string;
  onNavigate: (path: string) => void;
}

const statusLabel = {
  active: "学习中",
  completed: "已完成",
  abandoned: "已结束",
};

const errorCopy: Record<string, string> = {
  SESSION_NOT_FOUND: "学习会话不存在或已被重置。",
  SESSION_VERSION_CONFLICT: "会话已在其他页面更新。",
  EXPECTED_QUESTION_MISMATCH: "当前问题已经变化。",
  LLM_NOT_CONFIGURED: "Live 模型尚未配置，本轮评估没有保存。",
  LLM_TIMEOUT: "模型响应超时，本轮评估没有保存。",
  LLM_RATE_LIMITED: "模型请求过于频繁，本轮评估没有保存。",
  LLM_AUTH_FAILED: "模型认证失败，本轮评估没有保存。",
  LLM_PROVIDER_UNAVAILABLE: "模型服务暂时不可用，本轮评估没有保存。",
  LLM_REFUSED: "模型拒绝了本轮请求，本轮评估没有保存。",
  LLM_SCHEMA_VALIDATION_FAILED: "模型输出格式无效，本轮评估没有保存。",
  LLM_SEMANTIC_VALIDATION_FAILED: "模型输出未通过课程校验，本轮评估没有保存。",
};

export function TutorSessionPage({ sessionId, onNavigate }: TutorSessionPageProps) {
  const [session, setSession] = useState<TutorSessionSnapshot | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [text, setText] = useState("");
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);
  const [inputMode, setInputMode] = useState<"answer" | "side_question">("answer");
  const [pendingPayload, setPendingPayload] = useState<SubmitTurnPayload | null>(null);
  const messageEndRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setSession(await fetchTutorSession(sessionId));
    } catch (reason: unknown) {
      setLoadError(reason instanceof Error ? reason.message : "会话加载失败");
    }
  }, [sessionId]);

  useEffect(() => {
    const controller = new AbortController();
    fetchTutorSession(sessionId, controller.signal)
      .then((restored) => {
        setSession(restored);
        setLoadError(null);
        setIsProcessing(false);
        setSelectedOptionId(null);
        setText("");
        setInputMode("answer");
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setLoadError(reason instanceof Error ? reason.message : "会话加载失败");
        }
      });
    return () => controller.abort();
  }, [sessionId]);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView?.({ block: "end" });
  }, [session?.messages.length]);

  const executeTurn = useCallback(
    async (payload: SubmitTurnPayload) => {
      if (!session) return;
      setIsProcessing(true);
      setActionError(null);
      try {
        const updated = await submitTutorTurn(session.session_id, payload);
        setSession(updated);
        setPendingPayload(null);
        if (updated.recoverable_error?.source === "assessor") {
          setActionError(errorCopy[updated.recoverable_error.code] ?? updated.recoverable_error.message);
        } else {
          setText("");
          setSelectedOptionId(null);
          setInputMode("answer");
          if (updated.recoverable_error) {
            setActionError(updated.recoverable_error.message);
          }
        }
      } catch (reason: unknown) {
        if (reason instanceof APIError) {
          setActionError(errorCopy[reason.code] ?? reason.message);
          if (reason.code === "SESSION_VERSION_CONFLICT" || reason.code === "EXPECTED_QUESTION_MISMATCH") {
            await load();
          }
        } else {
          setPendingPayload(payload);
          setActionError("网络连接中断，可重试本次提交。答案尚未确认保存。");
        }
      } finally {
        setIsProcessing(false);
      }
    },
    [load, session],
  );

  const submit = (kind: LearnerTurnKind) => {
    if (!session) return;
    const payload: SubmitTurnPayload = {
      client_turn_id: crypto.randomUUID(),
      expected_session_version: session.version,
      expected_question_id: session.expected_question?.question_id ?? null,
      kind,
      text: kind === "ANSWER" || kind === "SIDE_QUESTION" ? text : "",
      selected_option_id: kind === "ANSWER" ? selectedOptionId : null,
    };
    void executeTurn(payload);
  };

  const abandon = async () => {
    if (!session || !window.confirm("确认结束当前会话？已有学习证据会保留。")) return;
    setIsProcessing(true);
    try {
      await abandonTutorSession(session.session_id, session.version);
      onNavigate("/");
    } catch (reason: unknown) {
      setActionError(reason instanceof Error ? reason.message : "结束会话失败");
    } finally {
      setIsProcessing(false);
    }
  };

  const useDemoInput = (input: DemoInput) => {
    setInputMode("answer");
    setText(input.text);
    setSelectedOptionId(input.selected_option_id);
  };

  const startNext = async () => {
    if (!session?.next_ready_node) return;
    setIsProcessing(true);
    try {
      const next = await startTutorSession(session.next_ready_node.node_id, "normal");
      onNavigate(`/learn/${next.session_id}`);
    } catch (reason: unknown) {
      setActionError(reason instanceof Error ? reason.message : "下一节点启动失败");
      setIsProcessing(false);
    }
  };

  if (loadError) {
    return (
      <main className="centered-state" role="alert">
        <AlertCircle size={28} aria-hidden="true" />
        <h1>学习会话无法加载</h1>
        <p>{loadError}</p>
        <button type="button" onClick={() => onNavigate("/")}>
          <ArrowLeft size={17} aria-hidden="true" />返回路线图
        </button>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="centered-state loading-state" aria-live="polite">
        <LoaderCircle className="spinner" size={28} aria-hidden="true" />
        <span>正在恢复学习会话</span>
      </main>
    );
  }

  const question = session.expected_question;
  const inputActionAllowed =
    inputMode === "side_question"
      ? session.available_actions.can_ask_side_question
      : session.available_actions.can_submit_answer;
  const canSubmit = Boolean(
    question && inputActionAllowed &&
      (inputMode === "side_question"
        ? text.trim()
        : question.response_type === "single_choice"
          ? selectedOptionId
          : text.trim()),
  );

  return (
    <div className="session-shell">
      <header className="session-topbar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true"><Network size={22} /></span>
          <div><strong>InfraTutor</strong><span>Tutor Session</span></div>
        </div>
        <div className="session-context">
          <span><small>原始目标</small>{session.target_node.title}</span>
          <span><small>当前节点</small>{session.current_node.title}</span>
          <span className={`session-status ${session.status}`}>{statusLabel[session.status]}</span>
          <span className="llm-mode">LLM · {session.llm_mode.toUpperCase()}</span>
        </div>
        <button className="back-button" type="button" onClick={() => onNavigate("/")}>
          <ArrowLeft size={16} aria-hidden="true" />返回路线图
        </button>
      </header>

      <main className="session-main">
        {session.target_node.node_id !== session.current_node.node_id && (
          <div className="remediation-banner">
            <BookOpen size={18} aria-hidden="true" />
            <div>
              <strong>当前正在补习：{session.current_node.title}</strong>
              <span>原始目标：{session.target_node.title}</span>
            </div>
          </div>
        )}

        <section className="transcript" aria-label="会话记录" aria-live="polite">
          {session.messages.map((message) => (
            <article className={`message ${message.role}`} key={message.message_id}>
              <span className="message-role">
                {message.role === "tutor" ? "Tutor" : message.role === "learner" ? "你" : "System"}
              </span>
              <p>{message.text}</p>
            </article>
          ))}
          <div ref={messageEndRef} />
        </section>

        {session.status === "completed" ? (
          <section className="session-complete" aria-label="节点完成">
            <CheckCircle2 size={30} aria-hidden="true" />
            <div>
              <h2>{session.target_node.title} 已掌握</h2>
              <p>学习状态已写入路线图。</p>
            </div>
            <button type="button" onClick={() => onNavigate("/")}>返回路线图</button>
            {session.next_ready_node && (
              <button type="button" className="primary" disabled={isProcessing} onClick={() => void startNext()}>
                进入 {session.next_ready_node.title}<ArrowRight size={16} aria-hidden="true" />
              </button>
            )}
          </section>
        ) : session.status === "abandoned" ? (
          <section className="session-complete"><LogOut size={28} aria-hidden="true" /><h2>会话已结束</h2></section>
        ) : question ? (
          <section className="interaction-panel">
            <div className="question-heading">
              <span>{question.response_type === "single_choice" ? "单选题" : "回答题"}</span>
              <code>{question.question_id}</code>
            </div>
            <h2>{question.prompt}</h2>
            <QuestionRenderer
              question={question}
              text={text}
              selectedOptionId={selectedOptionId}
              disabled={isProcessing || !inputActionAllowed}
              mode={inputMode}
              onTextChange={setText}
              onOptionChange={setSelectedOptionId}
              onSubmit={() => submit(inputMode === "side_question" ? "SIDE_QUESTION" : "ANSWER")}
            />

            {actionError && (
              <div className="turn-error" role="alert">
                <AlertCircle size={16} aria-hidden="true" />
                <span>{actionError}</span>
                {pendingPayload && (
                  <button type="button" disabled={isProcessing} onClick={() => void executeTurn(pendingPayload)}>
                    重试本次提交
                  </button>
                )}
              </div>
            )}

            <div className="interaction-actions">
              <button
                type="button"
                className="primary submit-answer"
                disabled={isProcessing || !canSubmit}
                onClick={() => submit(inputMode === "side_question" ? "SIDE_QUESTION" : "ANSWER")}
              >
                {isProcessing ? <LoaderCircle className="spinner" size={16} /> : <Send size={16} />}
                {isProcessing ? "处理中" : inputMode === "side_question" ? "提交问题" : "提交回答"}
              </button>
              <button
                type="button"
                disabled={isProcessing || !session.available_actions.can_ask_side_question}
                aria-pressed={inputMode === "side_question"}
                onClick={() => setInputMode((value) => value === "answer" ? "side_question" : "answer")}
              >
                <MessageCircleQuestion size={16} aria-hidden="true" />
                {inputMode === "side_question" ? "返回答题" : "我有个问题"}
              </button>
              <button type="button" disabled={isProcessing || !session.available_actions.can_request_hint} onClick={() => submit("REQUEST_HINT")}>
                <Lightbulb size={16} aria-hidden="true" />给我提示
              </button>
              <button
                type="button"
                disabled={isProcessing || !session.available_actions.can_request_answer}
                onClick={() => {
                  if (window.confirm("直接查看讲解后，本题不能作为独立掌握证据，系统会换一道题重新确认。")) {
                    submit("REQUEST_ANSWER");
                  }
                }}
              >
                <BookOpen size={16} aria-hidden="true" />直接讲解
              </button>
              <button type="button" disabled={isProcessing || !session.available_actions.can_report_mastery} onClick={() => submit("SELF_REPORTED_MASTERY")}>
                <CircleHelp size={16} aria-hidden="true" />我觉得我已经会了
              </button>
              <button className="danger-text" type="button" disabled={isProcessing || !session.available_actions.can_abandon} onClick={() => void abandon()}>
                <LogOut size={16} aria-hidden="true" />结束会话
              </button>
            </div>
          </section>
        ) : null}

        {session.debug && <DebugPanel debug={session.debug} onUseDemoInput={useDemoInput} />}
      </main>
    </div>
  );
}
