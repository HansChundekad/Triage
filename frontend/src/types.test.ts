import { describe, it, expect } from "vitest";
import { isReport, type StreamEvent } from "./types";

describe("types", () => {
  it("isReport narrows report events", () => {
    const ev: StreamEvent = {
      type: "report",
      report: {
        issueUrl: "u", status: "reproduced", verdict: "Bug reproduced.",
        reproSteps: [], rootCause: { hypothesis: "", evidence: "", confidence: "high" },
        attempts: [], consoleErrors: [],
      },
    };
    expect(isReport(ev)).toBe(true);
    expect(isReport({ type: "status", phase: "parsing", attempt: 1, maxAttempts: 3 })).toBe(false);
  });
});
