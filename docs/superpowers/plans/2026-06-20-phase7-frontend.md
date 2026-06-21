# Phase 7 Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build TRIAGE's thin frontend — paste a GitHub issue URL, watch the three agents coordinate live alongside the real cloud browser, then read the final report card — plus a thin FastAPI backend that drives a live run and streams it over SSE.

**Architecture:** A Vite + React + TypeScript static app (Vercel-deployable) with two data sources behind one `StreamEvent` callback: a **client-side replay player** (reads a committed JSON fixture, emits events on timers — no backend, the no-backend default) and a **live SSE** connection to a thin FastAPI backend. The backend composes the three existing real agents (same as `scripts/phase6_live_run.py`) and taps the Band transcript by wrapping each `BandAgent`'s `send_message`/`send_event` at composition time — `band.py` is never modified.

**Tech Stack:** Vite, React 18, TypeScript, Vitest + @testing-library/react (frontend tests); FastAPI + uvicorn + sse-starlette, pytest + Starlette `TestClient` (backend tests); existing `triage` package + `.venv`.

## Global Constraints

- **Replay is built first; live is layered on after.** The demo must never show a blank/broken UI (replay is the no-backend default).
- **Browser-view embed is timeboxed**; the replay-link fallback is built before the iframe attempt.
- **Never modify `triage/shared/band.py`** (frozen, hard rule #8). The backend tap wraps bound methods at composition time only.
- **No fourth coordinating Band identity** (hard rule). The backend observes in-process; it does not join the room.
- **Agent names are exact**: `ParserAgent` / `ReproAgent` / `HypothesisAgent`.
- **Report schema in `src/types.ts` is a PLACEHOLDER** — must be reconciled to the Arize worktree's final shape (spec §6). Where they diverge, Arize wins.
- **Cursive (Cormorant Garamond italic) is scoped to exactly two elements**: the `Triage` wordmark and the report card verdict line. Nothing else.
- Node `v22`, Python `3.14` via repo `.venv`. Browserbase replay URL form: `https://www.browserbase.com/sessions/{sessionId}`.
- Backend wall-clock cap reuses the harness value: `WALL_CLOCK_TIMEOUT = 600`.

---

### Task 1: Frontend scaffold + design tokens + wordmark shell

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/index.html`, `frontend/.gitignore`
- Create: `frontend/src/main.tsx`, `frontend/src/App.tsx`
- Create: `frontend/src/styles/tokens.css`, `frontend/src/styles/app.css`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Produces: a Vite app whose `App` renders the `Triage` wordmark; `npm run dev` serves it, `npm run build` produces `dist/`, `npm test` runs Vitest.

- [ ] **Step 1: Write the failing test**

`frontend/src/App.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders the Triage wordmark", () => {
    render(<App />);
    expect(screen.getByRole("banner")).toHaveTextContent("Triage");
  });
});
```

- [ ] **Step 2: Scaffold the project files**

`frontend/package.json`:
```json
{
  "name": "triage-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.8",
    "@testing-library/react": "^16.0.1",
    "@types/react": "^18.3.5",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "jsdom": "^25.0.0",
    "typescript": "^5.5.4",
    "vite": "^5.4.3",
    "vitest": "^2.0.5"
  }
}
```

`frontend/vite.config.ts`:
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
```

`frontend/src/test-setup.ts`:
```ts
import "@testing-library/jest-dom/vitest";
```

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noEmit": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"]
}
```

`frontend/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Triage — autonomous bug reproduction</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@1,500;1,600&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap"
      rel="stylesheet"
    />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/.gitignore`:
```
node_modules
dist
*.local
```

- [ ] **Step 3: Write tokens + base styles**

`frontend/src/styles/tokens.css`:
```css
:root {
  /* palette — OKLCH, near-black editorial + honey-gold */
  --bg:        oklch(0.17 0.012 75);
  --surface:   oklch(0.21 0.014 75);
  --surface-2: oklch(0.25 0.016 75);
  --ink:       oklch(0.96 0.005 75);
  --muted:     oklch(0.74 0.02 75);   /* ≥4.5:1 on --bg; verify in Task 8 */
  --gold:      oklch(0.80 0.14 75);
  --gold-dim:  oklch(0.62 0.10 75);
  --ok:        oklch(0.80 0.14 75);   /* reproduced = gold */
  --cool:      oklch(0.72 0.03 240);  /* not_reproduced */
  --danger:    oklch(0.64 0.16 25);   /* error, restrained */
  --line:      oklch(0.30 0.012 75);

  /* type */
  --font-ui:    "Inter", system-ui, sans-serif;
  --font-mono:  "JetBrains Mono", ui-monospace, monospace;
  --font-script:"Cormorant Garamond", Georgia, serif;
  --t-xs: 0.78rem; --t-sm: 0.875rem; --t-base: 1rem;
  --t-lg: 1.2rem; --t-xl: 1.44rem; --t-2xl: 1.73rem;

  /* space + motion + z */
  --s1: 4px; --s2: 8px; --s3: 12px; --s4: 16px; --s5: 24px; --s6: 40px; --s7: 64px;
  --radius: 10px;
  --ease: cubic-bezier(0.22, 1, 0.36, 1); /* ease-out-quint */
  --dur: 200ms;
  --z-stream: 10; --z-sticky: 20; --z-toast: 40;
}

@media (prefers-reduced-motion: reduce) {
  :root { --dur: 1ms; }
}
```

`frontend/src/styles/app.css`:
```css
* { box-sizing: border-box; margin: 0; }
html, body, #root { height: 100%; }
body {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--font-ui);
  font-size: var(--t-base);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.shell { max-width: 1080px; margin: 0 auto; padding: var(--s6) var(--s5); }
.brand {
  display: flex; align-items: baseline; gap: var(--s3);
  border-bottom: 1px solid var(--line); padding-bottom: var(--s4);
}
.wordmark {
  font-family: var(--font-script); font-style: italic; font-weight: 600;
  font-size: var(--t-2xl); color: var(--gold); letter-spacing: -0.01em;
}
.tagline { color: var(--muted); font-size: var(--t-sm); }
```

- [ ] **Step 4: Write `main.tsx` and `App.tsx`**

`frontend/src/main.tsx`:
```tsx
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/tokens.css";
import "./styles/app.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

`frontend/src/App.tsx`:
```tsx
export default function App() {
  return (
    <div className="shell">
      <header className="brand" role="banner">
        <span className="wordmark">Triage</span>
        <span className="tagline">reproduces your bugs by using your app</span>
      </header>
    </div>
  );
}
```

- [ ] **Step 5: Install and run the test**

Run: `cd frontend && npm install && npm test`
Expected: 1 passing test (`renders the Triage wordmark`).

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(frontend): scaffold Vite+React+TS, tokens, wordmark shell"
```

---

### Task 2: Stream + report types (placeholder schema)

**Files:**
- Create: `frontend/src/types.ts`
- Test: `frontend/src/types.test.ts`

**Interfaces:**
- Produces: `StreamEvent` (discriminated union on `type`), `RunReport`, `ReproStep`, `Attempt`, `SessionInfo`, and the type guard `isReport(e): e is ReportEvent`. Every later task imports from here.

- [ ] **Step 1: Write the failing test**

`frontend/src/types.test.ts`:
```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- types`
Expected: FAIL — cannot find module `./types`.

- [ ] **Step 3: Write `types.ts`**

```ts
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- types`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/types.test.ts
git commit -m "feat(frontend): StreamEvent + RunReport placeholder types"
```

---

### Task 3: Replay fixture + client-side replay player

**Files:**
- Create: `frontend/src/fixtures/recorded-run.json`
- Create: `frontend/src/replay.ts`
- Test: `frontend/src/replay.test.ts`

**Interfaces:**
- Consumes: `StreamEvent` from `./types`.
- Produces: `startReplay(events: StreamEvent[], onEvent: (e: StreamEvent) => void, opts?: { speed?: number }): () => void` — emits each event on a timer derived from `ts` deltas (capped), returns a cancel fn. And the committed `recorded-run.json` (the forced fail→succeed run from STATUS.md).

- [ ] **Step 1: Write the failing test**

`frontend/src/replay.test.ts`:
```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- replay`
Expected: FAIL — cannot find module `./replay`.

- [ ] **Step 3: Write `replay.ts`**

```ts
import type { StreamEvent } from "./types";

const STEP_DELAY_MS = 700;   // base cadence between events
const MAX_GAP_MS = 1500;     // cap, so replay never stalls

export function startReplay(
  events: StreamEvent[],
  onEvent: (e: StreamEvent) => void,
  opts: { speed?: number } = {}
): () => void {
  const speed = opts.speed ?? 1;
  let i = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let cancelled = false;

  const tick = () => {
    if (cancelled || i >= events.length) return;
    onEvent(events[i]);
    i += 1;
    if (i < events.length) {
      const delay = Math.min(STEP_DELAY_MS, MAX_GAP_MS) / speed;
      timer = setTimeout(tick, delay);
    }
  };
  timer = setTimeout(tick, STEP_DELAY_MS / speed);

  return () => {
    cancelled = true;
    if (timer) clearTimeout(timer);
  };
}
```

- [ ] **Step 4: Write the fixture**

`frontend/src/fixtures/recorded-run.json` — the forced fail→succeed run from `docs/STATUS.md` (sessions `9fd0293f` → `72bb755b`):
```json
[
  { "type": "status", "phase": "parsing", "attempt": 1, "maxAttempts": 3 },
  { "type": "message", "from": "ParserAgent", "to": ["ReproAgent"],
    "text": "extracted 2 steps (delete-only): click Delete, confirm delete", "ts": 1 },
  { "type": "status", "phase": "reproducing", "attempt": 1, "maxAttempts": 3 },
  { "type": "session", "session": { "sessionId": "9fd0293f",
    "liveViewUrl": "https://www.browserbase.com/sessions/9fd0293f",
    "replayUrl": "https://www.browserbase.com/sessions/9fd0293f", "attempt": 1 } },
  { "type": "step", "agent": "ReproAgent", "kind": "browser",
    "text": "navigate to app → list is empty, nothing to delete", "screenshot": null, "ts": 2 },
  { "type": "message", "from": "ReproAgent", "to": ["HypothesisAgent"],
    "text": "BUG NOT REPRODUCED — list was empty, session 9fd0293f", "ts": 3 },
  { "type": "status", "phase": "diagnosing", "attempt": 1, "maxAttempts": 3 },
  { "type": "message", "from": "HypothesisAgent", "to": ["ParserAgent"],
    "text": "steps must first create tasks before deleting (redirect_parser)", "ts": 4 },
  { "type": "status", "phase": "retrying", "attempt": 2, "maxAttempts": 3 },
  { "type": "message", "from": "ParserAgent", "to": ["ReproAgent"],
    "text": "revised steps: type task → click Add → delete → confirm", "ts": 5 },
  { "type": "session", "session": { "sessionId": "72bb755b",
    "liveViewUrl": "https://www.browserbase.com/sessions/72bb755b",
    "replayUrl": "https://www.browserbase.com/sessions/72bb755b", "attempt": 2 } },
  { "type": "step", "agent": "ReproAgent", "kind": "browser",
    "text": "focus input → type 'buy milk' → click Add", "screenshot": null, "ts": 6 },
  { "type": "step", "agent": "ReproAgent", "kind": "browser",
    "text": "click Delete → confirm → page went blank", "screenshot": null, "ts": 7 },
  { "type": "step", "agent": "ReproAgent", "kind": "error",
    "text": "TypeError: Cannot read properties of undefined (reading '0')", "screenshot": null, "ts": 8 },
  { "type": "message", "from": "ReproAgent", "to": ["HypothesisAgent"],
    "text": "BUG REPRODUCED — blank page + TypeError, session 72bb755b", "ts": 9 },
  { "type": "message", "from": "HypothesisAgent", "to": ["ReproAgent"],
    "text": "confirmed, matches the report. Repro valid.", "ts": 10 },
  { "type": "status", "phase": "done", "attempt": 2, "maxAttempts": 3 },
  { "type": "report", "report": {
    "issueUrl": "https://github.com/hanschundekad/triage-demo-app/issues/1",
    "status": "reproduced",
    "verdict": "Bug reproduced.",
    "reproSteps": [
      { "n": 1, "action": "Focus the task input", "screenshot": null },
      { "n": 2, "action": "Type a task and click Add", "screenshot": null },
      { "n": 3, "action": "Delete the task and confirm", "screenshot": null },
      { "n": 4, "action": "Observe the page go blank", "screenshot": null }
    ],
    "rootCause": {
      "hypothesis": "Render reads items[0] after the last item is deleted, so it dereferences undefined.",
      "evidence": "TypeError: Cannot read properties of undefined (reading '0')",
      "confidence": "high"
    },
    "attempts": [
      { "n": 1, "outcome": "fail", "sessionId": "9fd0293f", "replayUrl": "https://www.browserbase.com/sessions/9fd0293f" },
      { "n": 2, "outcome": "reproduced", "sessionId": "72bb755b", "replayUrl": "https://www.browserbase.com/sessions/72bb755b" }
    ],
    "consoleErrors": ["TypeError: Cannot read properties of undefined (reading '0')"]
  } }
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm test -- replay`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/replay.ts frontend/src/replay.test.ts frontend/src/fixtures
git commit -m "feat(frontend): client-side replay player + recorded-run fixture"
```

---

### Task 4: Run controller (`api.ts`) + GitHub-URL validation

**Files:**
- Create: `frontend/src/api.ts`
- Test: `frontend/src/api.test.ts`

**Interfaces:**
- Consumes: `StreamEvent` from `./types`, `startReplay` from `./replay`, fixture JSON.
- Produces:
  - `isGithubIssueUrl(url: string): boolean`
  - `startReplayRun(onEvent): () => void` — loads the bundled fixture, plays it.
  - `startLiveRun(apiBase, issueUrl, onEvent): () => void` — POSTs `/api/runs`, opens an `EventSource` on `/api/runs/{id}/stream`, parses frames into `StreamEvent`, returns a cancel fn that closes the source. (Live backend lands in Tasks 9–10; this function is written now and exercised against it then.)

- [ ] **Step 1: Write the failing test**

`frontend/src/api.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { isGithubIssueUrl } from "./api";

describe("isGithubIssueUrl", () => {
  it("accepts a real issue URL", () => {
    expect(isGithubIssueUrl("https://github.com/owner/repo/issues/42")).toBe(true);
  });
  it("rejects non-issue URLs", () => {
    expect(isGithubIssueUrl("https://github.com/owner/repo")).toBe(false);
    expect(isGithubIssueUrl("https://example.com/issues/1")).toBe(false);
    expect(isGithubIssueUrl("not a url")).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- api`
Expected: FAIL — cannot find module `./api`.

- [ ] **Step 3: Write `api.ts`**

```ts
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
          const data = JSON.parse((ev as MessageEvent).data);
          onEvent({ type: t, ...data } as StreamEvent);
          if (t === "report" || t === "error") source?.close();
        });
      }
      source.onerror = () => {
        if (!cancelled) onEvent({ type: "error", message: "stream connection lost" });
      };
    })
    .catch((e) => {
      if (!cancelled) onEvent({ type: "error", message: String(e.message ?? e) });
    });

  return () => {
    cancelled = true;
    source?.close();
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- api`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.ts frontend/src/api.test.ts
git commit -m "feat(frontend): run controller — replay/live sources + URL validation"
```

---

### Task 5: `UrlInput` + `App` run state machine (replay end-to-end)

**Files:**
- Create: `frontend/src/components/UrlInput.tsx`
- Modify: `frontend/src/App.tsx` (replace the shell with the state machine)
- Modify: `frontend/src/styles/app.css` (add input + layout styles)
- Test: `frontend/src/components/UrlInput.test.tsx`, `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `isGithubIssueUrl`, `startReplayRun`, `startLiveRun` from `../api`; `StreamEvent`, `RunReport` from `../types`.
- Produces: `UrlInput({ onRun, disabled }: { onRun: (mode: "live" | "replay", url: string) => void; disabled: boolean })`. `App` holds `events: StreamEvent[]`, `report: RunReport | null`, `phase`, drives the run, and renders child panes (LiveLog/BrowserView/ReportCard arrive in Tasks 6–8 — render placeholders here).

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/UrlInput.test.tsx`:
```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import UrlInput from "./UrlInput";

describe("UrlInput", () => {
  it("disables Run until the URL is a valid issue URL", () => {
    const onRun = vi.fn();
    render(<UrlInput onRun={onRun} disabled={false} />);
    const run = screen.getByRole("button", { name: /run/i });
    expect(run).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "https://github.com/o/r/issues/7" },
    });
    expect(run).toBeEnabled();
    fireEvent.click(run);
    expect(onRun).toHaveBeenCalledWith("live", "https://github.com/o/r/issues/7");
  });

  it("Demo button triggers a replay run", () => {
    const onRun = vi.fn();
    render(<UrlInput onRun={onRun} disabled={false} />);
    fireEvent.click(screen.getByRole("button", { name: /demo/i }));
    expect(onRun).toHaveBeenCalledWith("replay", expect.any(String));
  });
});
```

Update `frontend/src/App.test.tsx` (append):
```tsx
import { fireEvent } from "@testing-library/react";

it("plays the replay run when Demo is clicked", async () => {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: /demo/i }));
  expect(await screen.findByText(/extracted 2 steps/i, {}, { timeout: 4000 })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- UrlInput App`
Expected: FAIL — `./components/UrlInput` missing; App has no Demo button.

- [ ] **Step 3: Write `UrlInput.tsx`**

```tsx
import { useState } from "react";
import { isGithubIssueUrl } from "../api";

export default function UrlInput(
  { onRun, disabled }: { onRun: (mode: "live" | "replay", url: string) => void; disabled: boolean }
) {
  const [url, setUrl] = useState("");
  const valid = isGithubIssueUrl(url);
  return (
    <form
      className="urlbar"
      onSubmit={(e) => { e.preventDefault(); if (valid && !disabled) onRun("live", url.trim()); }}
    >
      <input
        type="url" className="urlbar__input" placeholder="Paste a GitHub issue URL…"
        value={url} onChange={(e) => setUrl(e.target.value)} disabled={disabled}
        aria-label="GitHub issue URL"
      />
      <button type="submit" className="btn btn--primary" disabled={!valid || disabled}>Run</button>
      <button type="button" className="btn btn--ghost" disabled={disabled}
        onClick={() => onRun("replay", "demo")}>Demo</button>
    </form>
  );
}
```

- [ ] **Step 4: Rewrite `App.tsx` with the state machine**

```tsx
import { useRef, useState } from "react";
import UrlInput from "./components/UrlInput";
import { startLiveRun, startReplayRun } from "./api";
import type { RunReport, RunPhase, StreamEvent } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

type Status = "idle" | "running" | "report" | "error";

export default function App() {
  const [status, setStatus] = useState<Status>("idle");
  const [phase, setPhase] = useState<RunPhase | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [report, setReport] = useState<RunReport | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const cancelRef = useRef<null | (() => void)>(null);

  function onEvent(e: StreamEvent) {
    setEvents((prev) => [...prev, e]);
    if (e.type === "status") setPhase(e.phase);
    if (e.type === "report") { setReport(e.report); setStatus("report"); }
    if (e.type === "error") { setErrorMsg(e.message); setStatus("error"); }
  }

  function onRun(mode: "live" | "replay", url: string) {
    cancelRef.current?.();
    setEvents([]); setReport(null); setErrorMsg(""); setPhase(null); setStatus("running");
    cancelRef.current = mode === "replay"
      ? startReplayRun(onEvent)
      : startLiveRun(API_BASE, url, onEvent);
  }

  return (
    <div className="shell">
      <header className="brand" role="banner">
        <span className="wordmark">Triage</span>
        <span className="tagline">reproduces your bugs by using your app</span>
      </header>

      <UrlInput onRun={onRun} disabled={status === "running"} />

      {status === "error" && <div className="banner banner--error" role="alert">{errorMsg}</div>}

      {status !== "idle" && (
        <main className="stage">
          {/* LiveLog (Task 6) */}
          <section aria-label="run log" className="pane pane--log">
            {events.map((e, i) => (
              <div key={i} className="rawline">{e.type}: {JSON.stringify(e).slice(0, 120)}</div>
            ))}
            {phase && <div className="phase">phase: {phase}</div>}
          </section>
          {/* BrowserView (Task 7) + ReportCard (Task 8) mount here later */}
          {report && <pre className="pane pane--report">{JSON.stringify(report, null, 2)}</pre>}
        </main>
      )}
    </div>
  );
}
```

> Note: the import line is exactly `import { useRef, useState } from "react";`.

- [ ] **Step 5: Add input/layout styles**

Append to `frontend/src/styles/app.css`:
```css
.urlbar { display: flex; gap: var(--s3); margin: var(--s5) 0; }
.urlbar__input {
  flex: 1; padding: var(--s3) var(--s4); border-radius: var(--radius);
  background: var(--surface); border: 1px solid var(--line); color: var(--ink);
  font-family: var(--font-mono); font-size: var(--t-sm);
}
.urlbar__input::placeholder { color: var(--muted); }
.urlbar__input:focus-visible { outline: 2px solid var(--gold); outline-offset: 1px; }
.btn {
  padding: var(--s3) var(--s5); border-radius: var(--radius); border: 1px solid var(--line);
  font: 500 var(--t-sm) var(--font-ui); cursor: pointer; transition: background var(--dur) var(--ease);
}
.btn--primary { background: var(--gold); color: var(--bg); border-color: var(--gold); }
.btn--primary:disabled { background: var(--surface-2); color: var(--muted); border-color: var(--line); cursor: not-allowed; }
.btn--ghost { background: transparent; color: var(--ink); }
.btn:not(:disabled):hover { filter: brightness(1.08); }
.stage { display: grid; gap: var(--s5); grid-template-columns: 1fr; }
.pane { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: var(--s4); }
.pane--log { font-family: var(--font-mono); font-size: var(--t-xs); max-height: 420px; overflow: auto; }
.banner--error { background: color-mix(in oklch, var(--danger) 18%, var(--surface)); color: var(--ink); padding: var(--s3) var(--s4); border-radius: var(--radius); margin-top: var(--s4); }
.phase { color: var(--gold-dim); margin-top: var(--s3); }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS (UrlInput 2, App 2, plus earlier tests).

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): URL input + run state machine, replay end-to-end"
```

---

### Task 6: `LiveLog` — Band transcript spine + browser steps

**Files:**
- Create: `frontend/src/components/LiveLog.tsx`
- Modify: `frontend/src/App.tsx` (mount `LiveLog` in the log pane)
- Modify: `frontend/src/styles/app.css`
- Test: `frontend/src/components/LiveLog.test.tsx`

**Interfaces:**
- Consumes: `StreamEvent`, `AgentName` from `../types`.
- Produces: `LiveLog({ events }: { events: StreamEvent[] })` — renders `message` events as the coordination spine (agent name + @mentions + text) and `step` events as indented sub-activity (mono, kind-colored). `status`/`session`/`report`/`error` are ignored here (owned by App/BrowserView/ReportCard). Auto-scrolls to the newest line.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/LiveLog.test.tsx`:
```tsx
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- LiveLog`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `LiveLog.tsx`**

```tsx
import { useEffect, useRef } from "react";
import type { StreamEvent } from "../types";

const AGENT_ABBR: Record<string, string> = {
  ParserAgent: "Parser", ReproAgent: "Repro", HypothesisAgent: "Hypothesis",
};

export default function LiveLog({ events }: { events: StreamEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [events.length]);

  return (
    <div className="log">
      {events.map((e, i) => {
        if (e.type === "message") {
          return (
            <div className="log__msg" key={i} data-agent={e.from}>
              <span className="log__from">{e.from}</span>
              <span className="log__to">{e.to.map((t) => `@${t}`).join(" ")}</span>
              <span className="log__text">{e.text}</span>
            </div>
          );
        }
        if (e.type === "step") {
          return (
            <div className={`log__step log__step--${e.kind}`} key={i}>
              <span className="log__agent">{AGENT_ABBR[e.agent] ?? e.agent}</span>
              <span className="log__text">{e.text}</span>
            </div>
          );
        }
        return null;
      })}
      <div ref={endRef} />
    </div>
  );
}
```

- [ ] **Step 4: Mount in `App.tsx`**

Replace the raw-line log block in `App.tsx` (the `<section aria-label="run log">` contents) with:
```tsx
import LiveLog from "./components/LiveLog";
// ...
<section aria-label="run log" className="pane pane--log">
  <LiveLog events={events} />
  {phase && <div className="phase">phase: {phase}</div>}
</section>
```

- [ ] **Step 5: Add log styles**

Append to `frontend/src/styles/app.css`:
```css
.log { display: flex; flex-direction: column; gap: var(--s2); }
.log__msg { display: grid; grid-template-columns: max-content max-content 1fr; gap: var(--s3);
  align-items: baseline; padding: var(--s2) 0; border-bottom: 1px solid var(--line);
  animation: linein var(--dur) var(--ease); }
.log__from { color: var(--gold); font-weight: 600; font-size: var(--t-sm); }
.log__to { color: var(--gold-dim); font-family: var(--font-mono); font-size: var(--t-xs); }
.log__text { color: var(--ink); }
.log__step { margin-left: var(--s6); display: flex; gap: var(--s3); font-family: var(--font-mono);
  font-size: var(--t-xs); color: var(--muted); animation: linein var(--dur) var(--ease); }
.log__step--error .log__text { color: var(--danger); }
.log__agent { color: var(--gold-dim); }
@keyframes linein { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .log__msg, .log__step { animation: none; } }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS (all tests).

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): LiveLog — Band transcript spine + browser steps"
```

---

### Task 7: `BrowserView` — replay-link fallback first, then live-view iframe

**Files:**
- Create: `frontend/src/components/BrowserView.tsx`
- Modify: `frontend/src/App.tsx` (track latest `SessionInfo`, mount `BrowserView`)
- Modify: `frontend/src/styles/app.css`
- Test: `frontend/src/components/BrowserView.test.tsx`

**Interfaces:**
- Consumes: `SessionInfo` from `../types`.
- Produces: `BrowserView({ session, live }: { session: SessionInfo | null; live: boolean })`. **Fallback first:** always renders a prominent "Open live session ↗" / "Watch replay ↗" link to `session.liveViewUrl` / `session.replayUrl`. **Then** (timeboxed) attempts an `<iframe src={session.liveViewUrl}>` when `live` is true; the link remains visible beneath as the guaranteed path. Empty state when `session` is null.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/BrowserView.test.tsx`:
```tsx
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- BrowserView`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `BrowserView.tsx`**

```tsx
import type { SessionInfo } from "../types";

export default function BrowserView({ session, live }: { session: SessionInfo | null; live: boolean }) {
  if (!session) {
    return (
      <div className="browser browser--empty">
        <p className="browser__hint">No live session yet — the browser appears once ReproAgent starts.</p>
      </div>
    );
  }
  const label = live ? "Open live session ↗" : "Watch replay ↗";
  const href = live ? session.liveViewUrl : session.replayUrl;
  return (
    <div className="browser">
      {live && (
        <iframe
          className="browser__frame" src={session.liveViewUrl}
          title={`Browserbase session ${session.sessionId}`}
          sandbox="allow-scripts allow-same-origin"
        />
      )}
      <a className="browser__link" href={href} target="_blank" rel="noopener noreferrer">
        {label}<span className="browser__sid">{session.sessionId} · attempt {session.attempt}</span>
      </a>
    </div>
  );
}
```

- [ ] **Step 4: Track session + mount in `App.tsx`**

In `App.tsx`, add state and update `onEvent`:
```tsx
import BrowserView from "./components/BrowserView";
import type { SessionInfo } from "./types";
// in component state:
const [session, setSession] = useState<SessionInfo | null>(null);
const [mode, setMode] = useState<"live" | "replay">("replay");
// in onEvent, add:
if (e.type === "session") setSession(e.session);
// in onRun, set mode + clear session:
setSession(null); setMode(mode);
```
(Adjust `onRun(mode, url)` to `setMode(mode)`.) Mount inside `.stage`, before the report:
```tsx
<BrowserView session={session} live={mode === "live"} />
```

- [ ] **Step 5: Add browser styles**

Append to `frontend/src/styles/app.css`:
```css
.browser { background: var(--surface-2); border: 1px solid var(--line); border-radius: var(--radius);
  overflow: hidden; display: flex; flex-direction: column; }
.browser__frame { width: 100%; aspect-ratio: 16 / 10; border: 0; background: #000; }
.browser__link { display: flex; justify-content: space-between; align-items: center; gap: var(--s4);
  padding: var(--s3) var(--s4); color: var(--gold); font-weight: 600; text-decoration: none; }
.browser__link:hover { background: var(--surface); }
.browser__sid { color: var(--muted); font-family: var(--font-mono); font-size: var(--t-xs); font-weight: 400; }
.browser--empty { padding: var(--s6); text-align: center; }
.browser__hint { color: var(--muted); font-size: var(--t-sm); }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS (all tests).

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): BrowserView — replay-link fallback + live-view iframe"
```

---

### Task 8: `ReportCard` — verdict, steps, root cause, replay links (graceful nulls)

**Files:**
- Create: `frontend/src/components/ReportCard.tsx`
- Modify: `frontend/src/App.tsx` (replace the `<pre>` report dump)
- Modify: `frontend/src/styles/app.css`
- Test: `frontend/src/components/ReportCard.test.tsx`

**Interfaces:**
- Consumes: `RunReport`, `ReproStep` from `../types`.
- Produces: `ReportCard({ report }: { report: RunReport })`. Renders the cursive verdict, status pill, repro steps (screenshot `<img>` only when non-null — else text-only), root-cause block (hypothesis + mono evidence + confidence), and per-attempt replay links. Must not crash on empty `reproSteps`/`attempts`/null screenshots.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/ReportCard.test.tsx`:
```tsx
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- ReportCard`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `ReportCard.tsx`**

```tsx
import type { RunReport } from "../types";

const STATUS_LABEL: Record<RunReport["status"], string> = {
  reproduced: "Reproduced", not_reproduced: "Not reproduced", error: "Error",
};

export default function ReportCard({ report }: { report: RunReport }) {
  return (
    <article className="report" data-status={report.status}>
      <header className="report__head">
        <h2 className="report__verdict">{report.verdict}</h2>
        <span className={`pill pill--${report.status}`}>{STATUS_LABEL[report.status]}</span>
      </header>

      {report.reproSteps.length > 0 && (
        <section className="report__block">
          <h3 className="report__h">Confirmed repro steps</h3>
          <ol className="steps">
            {report.reproSteps.map((s) => (
              <li className="steps__item" key={s.n}>
                <span className="steps__action">{s.action}</span>
                {s.screenshot && (
                  <img className="steps__shot" src={s.screenshot} alt={`Step ${s.n}: ${s.action}`} loading="lazy" />
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="report__block">
        <h3 className="report__h">Root cause</h3>
        <p className="report__hyp">{report.rootCause.hypothesis}</p>
        {report.rootCause.evidence && <pre className="report__evidence">{report.rootCause.evidence}</pre>}
        <span className="report__conf">confidence: {report.rootCause.confidence}</span>
      </section>

      {report.attempts.length > 0 && (
        <section className="report__block">
          <h3 className="report__h">Browser sessions</h3>
          <ul className="attempts">
            {report.attempts.map((a) => (
              <li className="attempts__item" key={a.n}>
                <span className="attempts__outcome" data-outcome={a.outcome}>attempt {a.n} · {a.outcome}</span>
                <a href={a.replayUrl} target="_blank" rel="noopener noreferrer">replay ↗</a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}
```

- [ ] **Step 4: Mount in `App.tsx`**

Replace the `{report && <pre …>}` block with:
```tsx
import ReportCard from "./components/ReportCard";
// ...
{report && <ReportCard report={report} />}
```

- [ ] **Step 5: Add report styles**

Append to `frontend/src/styles/app.css`:
```css
.report { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: var(--s5); }
.report__head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s4);
  border-bottom: 1px solid var(--line); padding-bottom: var(--s4); }
.report__verdict { font-family: var(--font-script); font-style: italic; font-weight: 600;
  font-size: var(--t-2xl); color: var(--gold); letter-spacing: -0.01em; }
.pill { font: 600 var(--t-xs) var(--font-ui); padding: var(--s1) var(--s3); border-radius: 999px; }
.pill--reproduced { background: color-mix(in oklch, var(--ok) 22%, var(--surface)); color: var(--gold); }
.pill--not_reproduced { background: color-mix(in oklch, var(--cool) 22%, var(--surface)); color: var(--cool); }
.pill--error { background: color-mix(in oklch, var(--danger) 22%, var(--surface)); color: var(--danger); }
.report__block { margin-top: var(--s5); }
.report__h { font-size: var(--t-sm); color: var(--muted); font-weight: 500; margin-bottom: var(--s3); }
.steps { list-style: none; padding: 0; display: flex; flex-direction: column; gap: var(--s3); counter-reset: s; }
.steps__item { counter-increment: s; }
.steps__action::before { content: counter(s) ". "; color: var(--gold-dim); font-family: var(--font-mono); }
.steps__shot { display: block; margin-top: var(--s2); max-width: 100%; border-radius: 6px; border: 1px solid var(--line); }
.report__hyp { color: var(--ink); max-width: 70ch; }
.report__evidence { margin-top: var(--s3); padding: var(--s3); background: var(--bg); border-radius: 6px;
  font-family: var(--font-mono); font-size: var(--t-xs); color: var(--danger); overflow-x: auto; }
.report__conf { display: inline-block; margin-top: var(--s3); color: var(--muted); font-size: var(--t-xs); }
.attempts { list-style: none; padding: 0; display: flex; flex-direction: column; gap: var(--s2); }
.attempts__item { display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: var(--t-sm); }
.attempts__item a { color: var(--gold); }
.attempts__outcome[data-outcome="fail"] { color: var(--muted); }
.attempts__outcome[data-outcome="reproduced"] { color: var(--gold); }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: PASS (all tests, including ReportCard 2).

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat(frontend): ReportCard — verdict, steps, root cause, replay links"
```

---

### Task 9: Backend — FastAPI run manager with Band tap

**Files:**
- Create: `backend/__init__.py`, `backend/server.py`, `backend/run_manager.py`, `backend/requirements.txt`
- Test: `tests/test_backend_server.py`

**Interfaces:**
- Consumes: `triage.config.load_config`, the agent callbacks/`BandAgent` (same composition as `scripts/phase6_live_run.py`), `ReproLoopState`.
- Produces:
  - `run_manager.normalize_message(from_name, mentions, text) -> dict` and `run_manager.normalize_event(agent, content, event_type, metadata) -> dict` — pure functions turning Band traffic into §5 stream-event dicts.
  - `run_manager.RunRegistry` — `create(issue_url) -> run_id`, `async stream(run_id)` (async generator of `(event_name, data_dict)`), `snapshot(run_id) -> dict`.
  - `server.app` — FastAPI app with the §4 routes.

- [ ] **Step 1: Write the failing test (pure normalizers + app smoke)**

`tests/test_backend_server.py`:
```python
from starlette.testclient import TestClient

from backend.run_manager import normalize_message, normalize_event


def test_normalize_message_shape():
    ev = normalize_message("ParserAgent", ["ReproAgent"], "extracted 4 steps")
    assert ev["type"] == "message"
    assert ev["from"] == "ParserAgent"
    assert ev["to"] == ["ReproAgent"]
    assert ev["text"] == "extracted 4 steps"
    assert "ts" in ev


def test_normalize_event_maps_browser_step():
    ev = normalize_event("ReproAgent", "focus input", "task", None)
    assert ev["type"] == "step"
    assert ev["agent"] == "ReproAgent"
    assert ev["kind"] == "browser"          # "task" → browser
    assert ev["text"] == "focus input"


def test_app_replays_list_endpoint():
    from backend.server import app
    client = TestClient(app)
    r = client.get("/api/replays")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_backend_server.py -v`
Expected: FAIL — `backend` package not importable.

- [ ] **Step 3: Add backend deps**

`backend/requirements.txt`:
```
fastapi>=0.115
uvicorn[standard]>=0.30
sse-starlette>=2.1
```
Install: `.venv/bin/pip install -r backend/requirements.txt`

- [ ] **Step 4: Write `run_manager.py`**

`backend/__init__.py`: empty file.

`backend/run_manager.py`:
```python
"""Drive a live TRIAGE run and tap the Band transcript into a stream queue.

The three real agents are composed exactly as scripts/phase6_live_run.py does.
We never modify band.py: the tap wraps each BandAgent's bound send_message /
send_event at composition time, so every directed message and logged event is
mirrored into the run's asyncio.Queue as a normalized stream event (spec §5).
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import AsyncIterator

import anthropic
import httpx

from triage.config import load_config
from triage.hypothesis_agent.agent import make_diagnosis_callback
from triage.parser_agent.agent import make_on_message, post_initial_steps
from triage.parser_agent.github import fetch_issue  # noqa: F401  (parity w/ harness)
from triage.repro_agent.echo import make_repro_callback
from triage.repro_agent.loop import ReproLoopState
from triage.shared.band import BandAgent

WALL_CLOCK_TIMEOUT = 600
_EVENT_KIND = {"task": "browser", "thought": "thought", "error": "error"}


def normalize_message(from_name: str, mentions: list[str], text: str) -> dict:
    return {"type": "message", "from": from_name, "to": list(mentions),
            "text": text, "ts": time.time()}


def normalize_event(agent: str, content: str, event_type: str, metadata: dict | None) -> dict:
    ev = {"type": "step", "agent": agent, "kind": _EVENT_KIND.get(event_type, "thought"),
          "text": content, "screenshot": None, "ts": time.time()}
    if metadata and metadata.get("session_url"):
        url = metadata["session_url"]
        ev["session_url"] = url
    return ev


def _tap(agent: BandAgent, run: "_Run") -> None:
    """Wrap bound send_message/send_event to mirror traffic into the run.

    Routes through `run.emit` so tapped traffic lands in both the live `queue`
    (for the SSE stream) and `buffer` (for the snapshot endpoint), exactly like
    the run's own status/report/error emits.
    """
    orig_msg = agent.send_message
    orig_evt = agent.send_event

    async def send_message(mentions, text):
        await run.emit("message", normalize_message(agent.name, mentions, text))
        return await orig_msg(mentions, text)

    async def send_event(content, event_type, metadata=None):
        await run.emit("step", normalize_event(agent.name, content, event_type, metadata))
        return await orig_evt(content, event_type, metadata)

    agent.send_message = send_message  # type: ignore[method-assign]
    agent.send_event = send_event      # type: ignore[method-assign]


class _Run:
    """One live run. Single SSE subscriber (the frontend opens exactly one
    EventSource right after POST). `queue` is the live tail the stream drains;
    `buffer` is a parallel history used only by the snapshot endpoint, so the
    two never double-emit."""

    def __init__(self, run_id: str, issue_url: str) -> None:
        self.run_id = run_id
        self.issue_url = issue_url
        self.queue: asyncio.Queue = asyncio.Queue()
        self.buffer: list[tuple[str, dict]] = []
        self.done = False

    async def emit(self, name: str, data: dict) -> None:
        self.buffer.append((name, data))
        await self.queue.put((name, data))


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, _Run] = {}

    def create(self, issue_url: str) -> str:
        run_id = uuid.uuid4().hex[:12]
        run = _Run(run_id, issue_url)
        self._runs[run_id] = run
        asyncio.create_task(self._drive(run))
        return run_id

    def snapshot(self, run_id: str) -> dict:
        run = self._runs[run_id]
        return {"runId": run_id, "done": run.done, "events": [d for _, d in run.buffer]}

    async def stream(self, run_id: str) -> AsyncIterator[tuple[str, dict]]:
        run = self._runs[run_id]
        while True:                              # drain the live tail only
            name, data = await run.queue.get()
            yield name, data
            if name in ("report", "error"):
                break

    async def _drive(self, run: _Run) -> None:
        try:
            cfg = load_config()
            parser_anthropic = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)
            hypothesis_anthropic = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
            http_client = httpx.AsyncClient()
            issue_cache: dict = {"issue": None}
            state = ReproLoopState()

            repro = BandAgent("ReproAgent", cfg.band_repro.agent_id, cfg.band_repro.api_key,
                              on_message=make_repro_callback(cfg, state))
            parser = BandAgent("ParserAgent", cfg.band_parser.agent_id, cfg.band_parser.api_key,
                               on_message=make_on_message(cfg, anthropic_client=parser_anthropic,
                                                          http_client=http_client, issue_cache=issue_cache))
            hypothesis = BandAgent("HypothesisAgent", cfg.band_hypothesis.agent_id,
                                   cfg.band_hypothesis.api_key,
                                   on_message=make_diagnosis_callback(hypothesis_anthropic,
                                                                      cfg.band_repro.agent_id))
            for a in (repro, parser, hypothesis):
                _tap(a, run)

            await run.emit("status", {"phase": "parsing", "attempt": 1,
                                      "maxAttempts": state.max_attempts})
            room_id = await repro.connect(room_id=cfg.band_room_id)
            if cfg.band_room_id is None:
                await repro.add_participant("ParserAgent")
                await repro.add_participant("HypothesisAgent")
            await parser.connect(room_id=room_id)
            await hypothesis.connect(room_id=room_id)
            await asyncio.sleep(2.0)

            await post_initial_steps(cfg, anthropic_client=parser_anthropic,
                                     http_client=http_client, agent=parser, issue_cache=issue_cache)

            deadline = time.monotonic() + WALL_CLOCK_TIMEOUT
            while not state.terminal and time.monotonic() < deadline:
                await asyncio.sleep(1)

            report = _build_report(run.issue_url, state)
            await run.emit("report", report)

            for a in (parser, hypothesis, repro):
                await a.disconnect()
            await http_client.aclose()
        except Exception as exc:  # honest terminal error — never hang
            await run.emit("error", {"message": f"{type(exc).__name__}: {exc}"})
        finally:
            run.done = True


def _build_report(issue_url: str, state: ReproLoopState) -> dict:
    """Synthesize the placeholder RunReport from the loop state (spec §6).

    PLACEHOLDER — reconcile to the Arize worktree's synthesis output. Per-step
    screenshots are not surfaced by ReproResultPayload, so steps are text-only
    here and the card leans on the session replay links.
    """
    urls = list(state.session_urls)
    reproduced = bool(state.terminal and state.attempts and not _gave_up(state))
    attempts = [{"n": i + 1,
                 "outcome": "reproduced" if (reproduced and i == len(urls) - 1) else "fail",
                 "sessionId": u.rstrip("/").split("/")[-1], "replayUrl": u}
                for i, u in enumerate(urls)]
    return {
        "issueUrl": issue_url,
        "status": "reproduced" if reproduced else "not_reproduced",
        "verdict": "Bug reproduced." if reproduced else "Could not reproduce.",
        "reproSteps": [],
        "rootCause": {"hypothesis": getattr(state, "root_cause", "") or "see transcript",
                      "evidence": "", "confidence": "medium"},
        "attempts": attempts,
        "consoleErrors": [],
    }


def _gave_up(state: ReproLoopState) -> bool:
    return state.attempts >= state.max_attempts and not getattr(state, "confirmed", False)
```

> Implementation note for the engineer: all stream output flows through
> `run.emit(...)` (status/report/error from `_drive`, message/step from the
> `_tap` wrappers) — one path, buffer + queue stay in sync, no duplicates.
> Verify `ReproLoopState` exposes `session_urls`, `attempts`, `max_attempts`,
> `terminal` (it does per STATUS.md §Key tunables); if `root_cause`/`confirmed`
> are absent on the state object, fall back to the transcript text already
> streamed (don't invent fields).

- [ ] **Step 5: Write `server.py`**

`backend/server.py`:
```python
from __future__ import annotations

import asyncio
import json
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.run_manager import RunRegistry

ISSUE_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/issues/\d+/?$")

app = FastAPI(title="TRIAGE frontend backend")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
_registry = RunRegistry()


class RunRequest(BaseModel):
    issueUrl: str


@app.post("/api/runs")
def start_run(req: RunRequest):
    if not ISSUE_RE.match(req.issueUrl.strip()):
        raise HTTPException(422, "not a GitHub issue URL")
    return {"runId": _registry.create(req.issueUrl.strip())}


@app.get("/api/runs/{run_id}")
def snapshot(run_id: str):
    try:
        return _registry.snapshot(run_id)
    except KeyError:
        raise HTTPException(404, "unknown run")


@app.get("/api/runs/{run_id}/stream")
async def stream(run_id: str):
    async def gen():
        async for name, data in _registry.stream(run_id):
            yield {"event": name, "data": json.dumps(data)}
    return EventSourceResponse(gen())


@app.get("/api/replays")
def replays():
    # The frontend ships its own bundled fixture; this lists server-side ones (none yet).
    return []
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_backend_server.py -v`
Expected: PASS (3 tests). Then full suite: `.venv/bin/pytest` — still 84+ passing (no regressions).

- [ ] **Step 7: Commit**

```bash
git add backend tests/test_backend_server.py
git commit -m "feat(backend): FastAPI run manager — live SSE + Band transcript tap"
```

---

### Task 10: Wire live mode end-to-end, env, Vercel deploy

**Files:**
- Create: `frontend/.env.example`, `frontend/vercel.json`
- Modify: `frontend/src/App.tsx` (already calls `startLiveRun` via `onRun("live", …)` — verify wiring)
- Create: `frontend/README.md` (replace placeholder), `backend/README.md`
- Test: manual live smoke (documented)

**Interfaces:**
- Consumes: `startLiveRun(API_BASE, url, onEvent)` (Task 4) against `backend.server.app` (Task 9).
- Produces: a deployable static frontend (replay default when `VITE_API_BASE` unset) + documented live-run procedure.

- [ ] **Step 1: Add frontend env + Vercel config**

`frontend/.env.example`:
```
# Base URL of the TRIAGE backend (FastAPI). Leave UNSET for the Vercel deploy:
# with no backend, the app defaults to replay-only (Demo button) and live runs
# surface a clear connection error.
VITE_API_BASE=http://localhost:8000
```

`frontend/vercel.json`:
```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

- [ ] **Step 2: Verify `App.tsx` live wiring**

Confirm `onRun("live", url)` path calls `startLiveRun(API_BASE, url, onEvent)` and `mode` is set to `"live"` so `BrowserView` attempts the iframe. No code change if Tasks 5/7 wired it; otherwise fix to match.

- [ ] **Step 3: Run the backend + frontend together (manual smoke)**

Run backend: `.venv/bin/uvicorn backend.server:app --port 8000`
Run frontend: `cd frontend && VITE_API_BASE=http://localhost:8000 npm run dev`
In the browser: paste `cfg.github_issue_url` (the demo issue), click **Run**. Expected: `status: parsing` → Band messages stream in LiveLog → a `session` link appears in BrowserView → terminal `report` renders the ReportCard. If the live browser flakes, the **Demo** button still plays the recorded run.

- [ ] **Step 4: Write READMEs**

`frontend/README.md`:
```markdown
# TRIAGE frontend

Vite + React + TS. Paste a GitHub issue URL → watch the three agents coordinate
and the real cloud browser run → read the report card.

## Dev
    cd frontend && npm install && npm run dev      # replay-only (no backend)
    VITE_API_BASE=http://localhost:8000 npm run dev # live (backend running)

## Test
    npm test

## Deploy (Vercel)
Static build (`npm run build` → `dist/`). Leave `VITE_API_BASE` unset for a
replay-only public deploy; set it to a reachable backend for live runs.

## Seams (must reconcile)
- `src/types.ts` RunReport is a PLACEHOLDER — match the Arize worktree schema.
- Per-step screenshots are null until the repro/synthesis layer surfaces them.
- Browserbase live-view URL == replay URL until the streamable endpoint is verified.
```

`backend/README.md`:
```markdown
# TRIAGE frontend backend

Thin FastAPI shim. Wraps the real 3-agent run (same composition as
scripts/phase6_live_run.py) and streams the Band transcript + browser steps
over SSE. Never modifies band.py.

## Run
    .venv/bin/pip install -r backend/requirements.txt
    .venv/bin/uvicorn backend.server:app --port 8000

## Endpoints
- POST /api/runs {issueUrl} -> {runId}
- GET  /api/runs/{id}/stream  (SSE: status|message|step|session|report|error)
- GET  /api/runs/{id}         (snapshot)
- GET  /api/replays           (server-side fixtures; none — frontend bundles its own)
```

- [ ] **Step 5: Run full test suites**

Run: `cd frontend && npm test && npm run build` (build must succeed) then `.venv/bin/pytest`
Expected: all frontend tests pass + `dist/` builds; backend/full suite green.

- [ ] **Step 6: Commit**

```bash
git add frontend/.env.example frontend/vercel.json frontend/README.md backend/README.md
git commit -m "feat(frontend): live mode wiring + Vercel deploy config + docs"
```

---

## Self-Review

**Spec coverage:**
- §1 goals — input (Task 5), live log (Task 6), browser hero (Task 7), report card (Task 8), Vercel/replay (Tasks 3, 10). ✓
- §2 decisions — stack (Task 1), data seam live+replay (Tasks 3/4/9), browser embed fallback-first (Task 7), theme/cursive (Tasks 1/8). ✓
- §3 architecture + §3.1 tap — Task 9 (`_tap` wraps bound methods; no band.py edits; no 4th identity). ✓
- §4 API — Task 9 (`/api/runs`, `/stream`, snapshot, `/replays`). ✓
- §5 SSE contract — Task 2 (types) + Task 9 (normalizers/emit). ✓
- §6 placeholder schema + screenshot seam — Task 2 (types), Task 8 (graceful nulls), Task 9 (`_build_report`). ✓
- §7 components/state — Tasks 5–8. ✓
- §8 visual system — Task 1 tokens + per-component styles. ✓
- §9 build order replay-first/fallback-first — Tasks ordered 3→4→5 (replay) before 9 (live), 7 fallback before iframe. ✓
- §10 seams — flagged in READMEs (Task 10), types (Task 2), `_build_report` (Task 9). ✓

**Placeholder scan:** No "TODO/TBD/handle edge cases" left as instructions. Task 9 routes all output through a single `run.emit` path (no dead-ends); its prose note only tells the engineer which `ReproLoopState` fields to trust vs. fall back from. Report schema is a deliberate, flagged PLACEHOLDER per spec.

**Type consistency:** `StreamEvent`/`RunReport`/`SessionInfo` defined in Task 2 and consumed verbatim in Tasks 5–9; backend normalizers emit the same field names (`from`/`to`/`text`/`ts`, `agent`/`kind`/`screenshot`, `session`). `startLiveRun`/`startReplayRun` signatures match between Task 4 (def) and Task 5 (call). `ReproLoopState` fields used in Task 9 (`session_urls`, `attempts`, `max_attempts`, `terminal`) match STATUS.md; the NOTE hedges `root_cause`/`confirmed`.

**One correction folded in:** Task 5 Step 4 had a stray self-referential comment about `useRef`; the import line is canonical `import { useRef, useState } from "react";`.
