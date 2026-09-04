import type { RoadmapData, SeedName } from "../types/roadmap";
import type {
  EntryMode,
  SubmitTurnPayload,
  TutorSessionSnapshot,
} from "../types/session";

const API_BASE_URL = "/api";

interface APIErrorBody {
  error?: {
    code?: string;
    message?: string;
    active_session_id?: string;
    active_target_node_id?: string;
  };
}

export class APIError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: APIErrorBody["error"];

  constructor(status: number, payload: APIErrorBody) {
    super(payload.error?.message ?? `请求失败 (${status})`);
    this.name = "APIError";
    this.status = status;
    this.code = payload.error?.code ?? "UNKNOWN_ERROR";
    this.details = payload.error;
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let payload: APIErrorBody = {};
    try {
      payload = (await response.json()) as APIErrorBody;
    } catch {
      // Keep a sanitized generic error when the backend does not return JSON.
    }
    throw new APIError(response.status, payload);
  }
  return response.json() as Promise<T>;
}

export async function fetchRoadmap(signal?: AbortSignal): Promise<RoadmapData> {
  const response = await fetch(`${API_BASE_URL}/roadmap`, { signal });
  return parseResponse<RoadmapData>(response);
}

export async function resetLearner(seed: SeedName): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/demo/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seed }),
  });
  if (!response.ok) {
    throw new Error(`学习状态重置失败 (${response.status})`);
  }
}

export async function startTutorSession(
  targetNodeId: string,
  entryMode: EntryMode,
): Promise<TutorSessionSnapshot> {
  const response = await fetch(`${API_BASE_URL}/tutor/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target_node_id: targetNodeId,
      entry_mode: entryMode,
      client_request_id: crypto.randomUUID(),
    }),
  });
  return parseResponse<TutorSessionSnapshot>(response);
}

export async function fetchTutorSession(
  sessionId: string,
  signal?: AbortSignal,
): Promise<TutorSessionSnapshot> {
  const response = await fetch(`${API_BASE_URL}/tutor/sessions/${sessionId}`, { signal });
  return parseResponse<TutorSessionSnapshot>(response);
}

export async function submitTutorTurn(
  sessionId: string,
  payload: SubmitTurnPayload,
): Promise<TutorSessionSnapshot> {
  const response = await fetch(`${API_BASE_URL}/tutor/sessions/${sessionId}/turns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse<TutorSessionSnapshot>(response);
}

export async function abandonTutorSession(
  sessionId: string,
  expectedVersion: number,
): Promise<TutorSessionSnapshot> {
  const response = await fetch(`${API_BASE_URL}/tutor/sessions/${sessionId}/abandon`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_session_version: expectedVersion }),
  });
  return parseResponse<TutorSessionSnapshot>(response);
}
