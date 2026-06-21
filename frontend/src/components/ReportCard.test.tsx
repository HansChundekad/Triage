import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ReportCard from "./ReportCard";
import type { RunReport } from "../types";

const base: RunReport = {
  issueUrl: "u", status: "reproduced", verdict: "Bug reproduced.",
  reproSteps: [{ n: 1, action: "Focus input", screenshot: null }],
  rootCause: { hypothesis: "reads items[0] after delete", evidence: "TypeError: x", confidence: "high" },
  attempts: [{ n: 1, outcome: "reproduced", sessionId: "abc", replayUrl: "https://www.browserbase.com/sessions/abc" }],
  consoleErrors: ["TypeError: x"],
};

describe("ReportCard", () => {
  it("renders verdict, step, root cause and replay link", () => {
    render(<ReportCard report={base} />);
    expect(screen.getByText("Bug reproduced.")).toBeInTheDocument();
    expect(screen.getByText("Focus input")).toBeInTheDocument();
    expect(screen.getByText(/reads items\[0\]/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /replay/i })).toHaveAttribute("href", base.attempts[0].replayUrl);
  });
  it("does not crash with empty steps/attempts and renders no images for null screenshots", () => {
    render(<ReportCard report={{ ...base, reproSteps: [], attempts: [] }} />);
    expect(screen.queryByRole("img")).toBeNull();
  });
});
