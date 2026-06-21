// PLACEHOLDER report schema — must be reconciled to the Arize worktree's
// final synthesis shape (spec §6). Where they diverge, Arize wins.

export type Confidence = "high" | "medium" | "low";

export interface ReproStep {
  n: number;
  action: string;
  screenshot: string | null; // data: URI or URL; null → text-only (graceful)
}

export interface Attempt {
  n: number;
  outcome: "fail" | "reproduced" | "not_reproduced";
  sessionId: string;
  replayUrl: string;
}

export interface RunReport {
  issueUrl: string;
  status: "reproduced" | "not_reproduced" | "error";
  verdict: string;
  reproSteps: ReproStep[];
  rootCause: { hypothesis: string; evidence: string; confidence: Confidence };
  attempts: Attempt[];
  consoleErrors: string[];
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
export type ReportEvent = { type: "report"; report: RunReport };
export type ErrorEvent = { type: "error"; message: string };

export type StreamEvent =
  | StatusEvent | MessageEvent | StepEvent | SessionEvent | ReportEvent | ErrorEvent;

export function isReport(e: StreamEvent): e is ReportEvent {
  return e.type === "report";
}
