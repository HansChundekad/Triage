import type { StreamEvent } from "./types";
import { startReplay } from "./replay";
import fixture from "./fixtures/recorded-run.json";

const ISSUE_RE = /^https:\/\/github\.com\/[^/]+\/[^/]+\/issues\/\d+\/?$/;

export function isGithubIssueUrl(url: string): boolean {
  return ISSUE_RE.test(url.trim());
}

export function startReplayRun(onEvent: (e: StreamEvent) => void): () => void {
  return startReplay(fixture as StreamEvent[], onEvent);
}

const STREAM_TYPES = ["status", "message", "step", "session", "report", "error"];

export function startLiveRun(
  apiBase: string,
  issueUrl: string,
  onEvent: (e: StreamEvent) => void
): () => void {
  let source: EventSource | null = null;
  let cancelled = false;
  const close = () => { cancelled = true; source?.close(); };

  fetch(`${apiBase}/api/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ issueUrl }),
  })
    .then((r) => {
      if (!r.ok) throw new Error(`run start failed: ${r.status}`);
      return r.json();
    })
    .then(({ runId }: { runId: string }) => {
      if (cancelled) return;
      source = new EventSource(`${apiBase}/api/runs/${runId}/stream`);
      for (const t of STREAM_TYPES) {
        source.addEventListener(t, (ev) => {
          let data: unknown;
          try { data = JSON.parse((ev as MessageEvent).data); }
          catch { onEvent({ type: "error", message: "malformed stream frame" }); close(); return; }
          onEvent({ type: t, ...(data as object) } as StreamEvent);
          if (t === "report" || t === "error") close();
        });
      }
      source.onerror = () => {
        if (!cancelled) onEvent({ type: "error", message: "stream connection lost" });
      };
    })
    .catch((e) => {
      if (!cancelled) onEvent({ type: "error", message: String(e.message ?? e) });
    });

  return () => { close(); };
}
