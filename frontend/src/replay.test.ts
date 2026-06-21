import { describe, it, expect, vi } from "vitest";
import { startReplay } from "./replay";
import type { StreamEvent } from "./types";

const evs: StreamEvent[] = [
  { type: "status", phase: "parsing", attempt: 1, maxAttempts: 3 },
  { type: "message", from: "ParserAgent", to: ["ReproAgent"], text: "steps", ts: 1 },
];

describe("startReplay", () => {
  it("emits all events in order", async () => {
    vi.useFakeTimers();
    const seen: string[] = [];
    startReplay(evs, (e) => seen.push(e.type), { speed: 1000 });
    await vi.runAllTimersAsync();
    expect(seen).toEqual(["status", "message"]);
    vi.useRealTimers();
  });

  it("cancel stops further emits", async () => {
    vi.useFakeTimers();
    const seen: string[] = [];
    const cancel = startReplay(evs, (e) => seen.push(e.type), { speed: 1 });
    cancel();
    await vi.runAllTimersAsync();
    expect(seen.length).toBeLessThan(2);
    vi.useRealTimers();
  });
});
