import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ReportCard from "./ReportCard";
import type { ReproReport } from "../types";

const base: ReproReport = {
  issue: { url: "https://github.com/org/repo/issues/1", title: "blank page on delete", summary: "deletes go blank" },
  verdict: "reproduced",
  repro_steps: [
    { n: 1, action: "Focus input", status: "ok", screenshot_ref: "screenshots/attempt2_step1.png" },
    { n: 2, action: "Delete and confirm", status: "crash", screenshot_ref: "screenshots/attempt2_step2.png" },
  ],
  root_cause: {
    hypothesis: "reads items[0] after delete",
    mechanism: "items[0] dereferences undefined once the array is empty",
    confidence: "high",
  },
  evidence: { console_error: "TypeError: x", blank_screen: true, body_snippet: "" },
  attempts: [
    { number: 1, session_replay_url: "https://www.browserbase.com/sessions/abc", bug_detected: true },
  ],
  eval_scores: { repro_fidelity: 1.0, root_cause_correctness: 0.5 },
  generated_at: "2026-06-20T00:00:00Z",
};

describe("ReportCard", () => {
  it("renders verdict, per-step status, root-cause mechanism, eval scores and replay link", () => {
    render(<ReportCard report={base} />);
    expect(screen.getByText("Reproduced")).toBeInTheDocument();
    expect(screen.getByText("Delete and confirm")).toBeInTheDocument();
    expect(screen.getByText("crash")).toBeInTheDocument();                 // per-step status badge
    expect(screen.getByText(/reads items\[0\]/)).toBeInTheDocument();
    expect(screen.getByText(/dereferences undefined/)).toBeInTheDocument(); // root_cause.mechanism
    expect(screen.getByText("100%")).toBeInTheDocument();                   // repro_fidelity
    expect(screen.getByText("50%")).toBeInTheDocument();                    // root_cause_correctness
    expect(screen.getByRole("link", { name: /replay/i }))
      .toHaveAttribute("href", base.attempts[0].session_replay_url);
  });
  it("does not crash with empty steps/attempts and renders no images for non-loadable refs", () => {
    render(<ReportCard report={{ ...base, repro_steps: [], attempts: [], eval_scores: null }} />);
    expect(screen.queryByRole("img")).toBeNull();
  });
});
