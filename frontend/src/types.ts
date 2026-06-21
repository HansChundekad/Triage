// Report schema — the canonical Arize `ReproReport` emitted by triage.synthesis
// (single source of truth). Field names + casing match the Python schema exactly
// (snake_case); do NOT alias or translate. See triage/synthesis/schema.py.

export type Confidence = "high" | "medium" | "low";
export type Verdict = "reproduced" | "not_reproduced";
export type StepStatus = "ok" | "fail" | "crash";

export interface ReportIssue {
  url: string;
  title: string;
  summary: string;
}

export interface ReproStep {
  n: number;
  action: string;
  status: StepStatus;
  screenshot_ref: string; // relative artifact path, or "" → text-only (graceful)
}

export interface RootCause {
  hypothesis: string;
  mechanism: string;
  confidence: Confidence;
}

export interface ReportEvidence {
  console_error: string;
  blank_screen: boolean;
  body_snippet: string;
}

export interface Attempt {
  number: number;
  session_replay_url: string;
  bug_detected: boolean;
}

export interface EvalScores {
  repro_fidelity: number | null;
  root_cause_correctness: number | null;
}

export interface ReproReport {
  issue: ReportIssue;
  verdict: Verdict;
  repro_steps: ReproStep[];
  root_cause: RootCause;
  evidence: ReportEvidence;
  attempts: Attempt[];
  eval_scores: EvalScores | null;
  generated_at: string;
}

export interface SessionInfo {
  sessionId: string;
  liveViewUrl: string;
  replayUrl: string;
  attempt: number;
}

export type AgentName = "ParserAgent" | "ReproAgent" | "HypothesisAgent";
export type RunPhase = "parsing" | "reproducing" | "diagnosing" | "retrying" | "done";

export type StatusEvent = { type: "status"; phase: RunPhase; attempt: number; maxAttempts: number };
export type MessageEvent = { type: "message"; from: AgentName; to: AgentName[]; text: string; ts: number };
export type StepEvent = {
  type: "step"; agent: AgentName; kind: "browser" | "thought" | "error";
  text: string; screenshot: string | null; ts: number;
};
export type SessionEvent = { type: "session"; session: SessionInfo };
export type ReportEvent = { type: "report"; report: ReproReport };
export type ErrorEvent = { type: "error"; message: string };

export type StreamEvent =
  | StatusEvent | MessageEvent | StepEvent | SessionEvent | ReportEvent | ErrorEvent;

export function isReport(e: StreamEvent): e is ReportEvent {
  return e.type === "report";
}
