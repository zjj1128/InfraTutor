import type { LearnerStatus, ProgressStatus } from "./roadmap";

export type EntryMode = "normal" | "diagnostic" | "review";
export type LearnerTurnKind =
  | "ANSWER"
  | "SIDE_QUESTION"
  | "REQUEST_HINT"
  | "REQUEST_ANSWER"
  | "SELF_REPORTED_MASTERY";

export interface SessionNode {
  node_id: string;
  title: string;
  learner_status: LearnerStatus;
  progress_status: ProgressStatus;
}

export interface QuestionOption {
  option_id: string;
  label: string;
}

export interface QuestionView {
  question_id: string;
  node_id: string;
  prompt: string;
  response_type: "single_choice" | "free_text";
  options: QuestionOption[];
}

export interface SessionMessage {
  message_id: string;
  sequence_number: number;
  role: "learner" | "tutor" | "system";
  message_kind: string;
  text: string;
  question_id: string | null;
  interaction_type: string | null;
  client_turn_id: string | null;
  created_at: string;
}

export interface AvailableActions {
  can_submit_answer: boolean;
  can_ask_side_question: boolean;
  can_request_hint: boolean;
  can_request_answer: boolean;
  can_report_mastery: boolean;
  can_abandon: boolean;
}

export interface RecoverableError {
  code: string;
  message: string;
  source: "assessor" | "teacher" | "session";
}

export interface DemoInput {
  label: string;
  text: string;
  selected_option_id: string | null;
}

export interface SessionDebug {
  session_id: string;
  session_version: number;
  client_turn_id: string | null;
  target_node_id: string;
  current_node_id: string;
  expected_question_id: string | null;
  current_assistance_level: string;
  canonical_assessment_summary: Record<string, unknown> | null;
  final_action: string | null;
  reason_codes: string[];
  remediation_target: string | null;
  return_stack: string[];
  state_delta: Record<string, unknown> | null;
  state_before: Record<string, unknown> | null;
  active_misconception_ids: string[];
  resolved_misconception_ids: string[];
  decision_trace_id: string | null;
  llm_metadata: Array<Record<string, unknown>>;
  llm_mode: "mock" | "live";
  recoverable_error_code: string | null;
  demo_inputs: DemoInput[];
}

export interface TutorSessionSnapshot {
  session_id: string;
  version: number;
  status: "active" | "completed" | "abandoned";
  mode: EntryMode;
  target_node: SessionNode;
  current_node: SessionNode;
  return_stack: SessionNode[];
  expected_question: QuestionView | null;
  messages: SessionMessage[];
  available_actions: AvailableActions;
  learner_state_summary: Array<{
    node_id: string;
    learner_status: LearnerStatus;
    progress_status: ProgressStatus;
  }>;
  roadmap_delta: Array<{ node_id: string; learner_status: LearnerStatus }>;
  next_ready_node: SessionNode | null;
  llm_mode: "mock" | "live";
  recoverable_error: RecoverableError | null;
  debug?: SessionDebug;
}

export interface SubmitTurnPayload {
  client_turn_id: string;
  expected_session_version: number;
  expected_question_id: string | null;
  kind: LearnerTurnKind;
  text: string;
  selected_option_id: string | null;
}
