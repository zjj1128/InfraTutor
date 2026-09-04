import { Bug, ChevronDown } from "lucide-react";

import type { DemoInput, SessionDebug } from "../types/session";

interface DebugPanelProps {
  debug: SessionDebug;
  onUseDemoInput: (input: DemoInput) => void;
}

function JsonBlock({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}

export function DebugPanel({ debug, onUseDemoInput }: DebugPanelProps) {
  return (
    <details className="debug-panel">
      <summary>
        <Bug size={16} aria-hidden="true" />
        Decision Debug
        <ChevronDown size={15} aria-hidden="true" />
      </summary>
      <div className="debug-content">
        {debug.demo_inputs.length > 0 && (
          <section className="demo-fixtures" aria-label="Mock 演示输入">
            <h3>Mock Fixtures</h3>
            <div>
              {debug.demo_inputs.map((item) => (
                <button type="button" key={item.label} onClick={() => onUseDemoInput(item)}>
                  {item.label}
                </button>
              ))}
            </div>
          </section>
        )}

        <dl className="debug-grid">
          <div><dt>Session</dt><dd>{debug.session_id}</dd></div>
          <div><dt>Version</dt><dd>{debug.session_version}</dd></div>
          <div><dt>Client Turn</dt><dd>{debug.client_turn_id ?? "-"}</dd></div>
          <div><dt>Target</dt><dd>{debug.target_node_id}</dd></div>
          <div><dt>Current</dt><dd>{debug.current_node_id}</dd></div>
          <div><dt>Question</dt><dd>{debug.expected_question_id ?? "-"}</dd></div>
          <div><dt>Assistance</dt><dd>{debug.current_assistance_level}</dd></div>
          <div><dt>Action</dt><dd>{debug.final_action ?? "-"}</dd></div>
          <div><dt>Remediation</dt><dd>{debug.remediation_target ?? "-"}</dd></div>
          <div><dt>Trace</dt><dd>{debug.decision_trace_id ?? "-"}</dd></div>
          <div><dt>LLM mode</dt><dd>{debug.llm_mode}</dd></div>
          <div><dt>Error</dt><dd>{debug.recoverable_error_code ?? "-"}</dd></div>
        </dl>

        <section><h3>Reason Codes</h3><JsonBlock value={debug.reason_codes} /></section>
        <section><h3>Return Stack</h3><JsonBlock value={debug.return_stack} /></section>
        <section><h3>Canonical Assessment</h3><JsonBlock value={debug.canonical_assessment_summary} /></section>
        <section><h3>State Before</h3><JsonBlock value={debug.state_before} /></section>
        <section><h3>State Delta</h3><JsonBlock value={debug.state_delta} /></section>
        <section><h3>Misconceptions</h3><JsonBlock value={{ active: debug.active_misconception_ids, resolved: debug.resolved_misconception_ids }} /></section>
        <section><h3>LLM Metadata</h3><JsonBlock value={debug.llm_metadata} /></section>
      </div>
    </details>
  );
}
