export type NodeAvailability = "available" | "supporting" | "coming_later";
export type LearnerStatus =
  | "locked"
  | "ready"
  | "learning"
  | "partial"
  | "mastered"
  | "review_needed";
export type ProgressStatus = "no_evidence" | "learning" | "partial" | "mastered" | "review_needed";
export type AccessStatus = "locked" | "available";
export type SeedName = "clean" | "golden_path";

export interface ActiveSessionSummary {
  session_id: string;
  target_node_id: string;
  current_node_id: string;
  version: number;
  mode: "normal" | "diagnostic" | "review";
}

export interface NodeReference {
  id: string;
  title: string;
}

export interface RoadmapNode {
  id: string;
  title: string;
  summary: string;
  type: "concept" | "skill" | "procedure" | "lab" | "checkpoint";
  implementation_status: "pilot" | "supporting" | "planned";
  availability: NodeAvailability;
  is_selectable: boolean;
  learner_status: LearnerStatus | null;
  progress_status: ProgressStatus | null;
  access_status: AccessStatus | null;
  can_start_diagnostic_probe: boolean;
  active_session_id: string | null;
  prerequisites: NodeReference[];
  missing_prerequisites: NodeReference[];
  recommended_next: NodeReference[];
  learning_objectives: string[];
}

export interface RoadmapStage {
  id: string;
  order: number;
  title: string;
  goal: string;
  exit_capabilities: string[];
  availability: "in_progress" | "coming_later";
  nodes: RoadmapNode[];
}

export interface RoadmapData {
  course_id: string;
  title: string;
  target_learner: string;
  current_stage_id: string;
  stage_count: number;
  pilot_node_count: number;
  learner_state_available: boolean;
  active_session: ActiveSessionSummary | null;
  stages: RoadmapStage[];
}
