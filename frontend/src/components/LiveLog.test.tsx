import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import LiveLog from "./LiveLog";
import type { StreamEvent } from "../types";

const events: StreamEvent[] = [
  { type: "message", from: "ParserAgent", to: ["ReproAgent"], text: "extracted steps", ts: 1 },
  { type: "step", agent: "ReproAgent", kind: "browser", text: "focus input", screenshot: null, ts: 2 },
  { type: "status", phase: "diagnosing", attempt: 1, maxAttempts: 3 },
];

describe("LiveLog", () => {
  it("renders messages with sender and mention", () => {
    render(<LiveLog events={events} />);
    expect(screen.getByText("ParserAgent")).toBeInTheDocument();
    expect(screen.getByText(/@ReproAgent/)).toBeInTheDocument();
    expect(screen.getByText("extracted steps")).toBeInTheDocument();
  });
  it("renders steps as indented sub-activity", () => {
    render(<LiveLog events={events} />);
    expect(screen.getByText("focus input")).toBeInTheDocument();
  });
});
