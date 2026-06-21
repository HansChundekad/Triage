import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import BrowserView from "./BrowserView";
import type { SessionInfo } from "../types";

const session: SessionInfo = {
  sessionId: "abc", attempt: 1,
  liveViewUrl: "https://www.browserbase.com/sessions/abc",
  replayUrl: "https://www.browserbase.com/sessions/abc",
};

describe("BrowserView", () => {
  it("always shows a session link (fallback-first)", () => {
    render(<BrowserView session={session} live={false} />);
    const link = screen.getByRole("link", { name: /session|replay/i });
    expect(link).toHaveAttribute("href", "https://www.browserbase.com/sessions/abc");
  });
  it("shows an empty state when there is no session", () => {
    render(<BrowserView session={null} live={true} />);
    expect(screen.getByText(/no live session yet/i)).toBeInTheDocument();
  });
});
