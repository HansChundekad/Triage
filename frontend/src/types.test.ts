import { describe, it, expect } from "vitest";
import { isReport, type StreamEvent } from "./types";

describe("types", () => {
  it("isReport narrows report events", () => {
    const ev: StreamEvent = {
      type: "report",
      report: {
        issue: { url: "u", title: "t", summary: "s" },
        verdict: "reproduced",
        repro_steps: [],
        root_cause: { hypothesis: "", mechanism: "", confidence: "high" },
        evidence: { console_error: "", blank_screen: false, body_snippet: "" },
        attempts: [],
        eval_scores: null,
        generated_at: "2026-06-20T00:00:00Z",
      },
    };
    expect(isReport(ev)).toBe(true);
    expect(isReport({ type: "status", phase: "parsing", attempt: 1, maxAttempts: 3 })).toBe(false);
  });
});
