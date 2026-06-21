# Phase 7 (Worktree B) — Frontend Design Spec

_Date: 2026-06-20 · Branch: `phase7-frontend` · Status: awaiting review_

The thin frontend for TRIAGE: paste a GitHub issue URL, watch the three agents
coordinate live, watch the real cloud browser break the app, read the final
report card. This is a **thin shell**, not the star — input, live log, browser
view, report card, done. No gold-plating.

> Read alongside `docs/TRIAGE_OVERVIEW.md` (architecture) and
> `docs/TRIAGE_INTEGRATIONS.md` (Browserbase / Band / Arize SDK details).

---

## 1. Goals & non-goals

**Goals**

1. **Entry point** — a GitHub issue URL input that kicks off a real run.
2. **Live log** — surface the Band room transcript (Parser → Repro → Hypothesis
   @mention coordination) *and* the browser steps as they happen, so the
   coordination is watchable.
3. **Browser hero** — embed the live Browserbase session view in-page so the
   real browser streaming is visible (the hero moment); fall back to a replay
   link if embedding is blocked.
4. **Report card** — render the final structured report: confirmed repro steps,
   root-cause hypothesis, per-step screenshots, and session replay link(s).
5. **Deploy-ready for Vercel** (static build). Live runs driven by a thin local
   backend; **replay fallback** so a flaky cloud browser can't break the demo.

**Non-goals**

- No auth, no multi-user, no persistence beyond an in-memory run registry.
- No agent logic, no browser/Stagehand code (that lives in `repro_agent` only).
- No re-implementation of the report schema — **consume** the Arize worktree's
  shape (see §6); build against a placeholder and flag the seam.

---

## 2. Decisions (locked with the user)

| Axis | Decision |
|---|---|
| **Stack** | Vite + React + TypeScript, minimal. No Next.js, no UI kit. `fetch` + `EventSource`. Static build → Vercel. |
| **Data seam** | Thin **FastAPI** backend in this worktree wraps the existing run harness and streams events over **SSE**. **Live is the hero**; **replay** (recorded JSON) is the safety net — *build the replay path first*. |
| **Browser view** | Embed live-view in an `<iframe>` (hero), **medium-hard, strictly timeboxed**. Build the **replay-link fallback first** so there's always something. Graceful fallback if the iframe is blocked (X-Frame-Options/CSP). |
| **Theme** | Near-black editorial surface + honey-gold accent. Live stream & screenshots glow against it. |
| **Cursive** | Refined italic (Cormorant Garamond italic), scoped to **two moments only**: the `Triage` wordmark and the report card's one-line verdict. Everything functional is clean sans (Inter/system); the transcript / console / code is monospace. |

---

## 3. Architecture & data flow

```
  ┌──────────────────────────── Vercel (static) ─────────────────────────────┐
  │  React app                                                                │
  │   UrlInput ──POST /api/runs {issueUrl}──►                                 │
  │   App (run state machine)  ◄──SSE /api/runs/{id}/stream──                 │
  │     ├─ LiveLog      (Band transcript + browser steps)                     │
  │     ├─ BrowserView  (live-view iframe → replay link fallback)             │
  │     └─ ReportCard   (final structured report)                            │
  └───────────────────────────────────┬───────────────────────────────────────┘
                                       │  VITE_API_BASE (localhost / tunnel)
                                       ▼
  ┌──────────────────────── FastAPI backend (demo laptop) ───────────────────┐
  │  server.py     REST + SSE endpoints                                       │
  │  run_manager.py  spawns a run (wraps phase6_live_run composition),        │
  │                  taps the Band transcript + browser steps → asyncio.Queue │
  │  replay.py     streams a recorded run JSON with original-ish timing        │
  └───────────────────────────────────┬───────────────────────────────────────┘
                                       ▼
                     existing triage agents (ParserAgent /
                     ReproAgent / HypothesisAgent) → Browserbase / Band / Claude
```

**Live mode**: the React app POSTs the issue URL, gets a `runId`, opens an
`EventSource` to the stream. The backend runs the three real agents in-process
(the same composition as `scripts/phase6_live_run.py`), observes the run, and
pushes normalized stream events into a per-run queue that the SSE endpoint
drains.

**Replay mode**: if `VITE_API_BASE` is unset (e.g. the bare Vercel deploy) or
the user toggles "Demo", the app reads a committed recorded-run fixture and the
backend (or the app directly) replays it with timing. The demo never shows a
blank, broken UI.

### 3.1 Observing the run (backend tap) — integration seam

`band.py` is **frozen** (hard rule #8 — do not modify). The backend already
holds the three `BandAgent` instances it composes, and every message/event is
already logged (`[Name] → [mentions]: text`, `event(type): ...`). Two candidate
taps, to be chosen during implementation after re-reading the live Band SDK:

- **(A) Callback wrap** — compose the agents in-process and wrap each agent's
  `on_message` callback + `run_repro` invocation so they *also* emit to the
  run queue. Most precise; no extra Band connection.
- **(B) Logging tap** — attach a `logging.Handler` that parses the existing
  INFO lines into stream events. Zero-touch but brittle to log-format drift.

**Default to (A).** Do **not** add a fourth coordinating Band identity (hard
rule). A passive read-only observer connection is acceptable only if (A) proves
infeasible; flag it if so.

---

## 4. Backend API

Base path `/api`. JSON in, JSON / `text/event-stream` out.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/runs` | Body `{ "issueUrl": "https://github.com/owner/repo/issues/42" }` → `{ "runId": "..." }`. Validates the URL is a GitHub issue. Starts the run async. |
| `GET` | `/api/runs/{runId}/stream` | **SSE.** Emits the event types in §5 until a terminal `report` or `error`, then closes. Replays buffered events on reconnect (so a late subscriber still sees the whole run). |
| `GET` | `/api/runs/{runId}` | Snapshot (current phase + buffered events + report-so-far) for reconnect / debugging. |
| `GET` | `/api/replays` | List committed recorded-run fixtures `[{ "name", "label" }]`. |
| `GET` | `/api/replays/{name}/stream` | SSE replay of a fixture with timing. Same event shape as a live run. |

**CORS**: allow the Vercel origin + `localhost`. **Errors**: any uncaught run
failure emits a terminal `error` event (never a silent hang); the run wall-clock
is capped (reuse the harness's `WALL_CLOCK_TIMEOUT = 600`).

---

## 5. SSE stream contract

Each SSE frame is `event: <type>` + `data: <json>`. Types:

```jsonc
// phase transitions of the run
event: status
data: { "phase": "parsing|reproducing|diagnosing|retrying|done",
        "attempt": 1, "maxAttempts": 3 }

// a Band MESSAGE — directed @mention talk between agents
event: message
data: { "from": "ParserAgent", "to": ["ReproAgent"],
        "text": "extracted 4 steps: focus input, type task, click add, click delete",
        "ts": 1718900000.0 }

// a Band EVENT / browser step — a log line (browser action, thought, error)
event: step
data: { "agent": "ReproAgent", "kind": "browser|thought|error",
        "text": "focus input → typed 'buy milk' → clicked Add",
        "screenshot": "data:image/png;base64,..." | null,   // see §6 seam
        "ts": 1718900001.0 }

// a Browserbase session came up — gives the live-view + replay URLs
event: session
data: { "sessionId": "9fd0293f",
        "liveViewUrl": "https://www.browserbase.com/sessions/9fd0293f",
        "replayUrl":   "https://www.browserbase.com/sessions/9fd0293f",
        "attempt": 1 }

// terminal: the synthesized report card payload (shape = §6)
event: report
data: { ...RunReport... }

// terminal: something failed; render an honest error state
event: error
data: { "message": "..." }
```

`message` vs `step` mirrors Band's **messages = directed talk** /
**events = logs** split (hard rule #6). The LiveLog renders messages as the
coordination spine and steps as indented sub-activity.

**`liveViewUrl` seam**: §2.5 of the integrations doc gives the replay URL
(`/sessions/{id}`). A *streamable live-view* URL may differ (Browserbase
debugger/live-view endpoint). **Verify against the live Browserbase SDK before
building the iframe** (hard rule #7); until confirmed, `liveViewUrl` === replay
URL and the iframe degrades to the link.

---

## 6. Report schema (PLACEHOLDER — must match the Arize worktree)

> ⚠️ **The Arize worktree owns the final report schema (Phase 7 synthesis).**
> This is a placeholder. When that schema lands, reconcile `src/types.ts` field
> names to it and delete this warning. Where they diverge, the Arize shape wins.

```jsonc
RunReport = {
  "issueUrl": "https://github.com/owner/repo/issues/42",
  "status": "reproduced" | "not_reproduced" | "error",
  "verdict": "Bug reproduced.",          // the cursive headline; one short line
  "reproSteps": [                         // confirmed steps
    { "n": 1, "action": "Focus the task input", "screenshot": "data:image/png;base64,…" | null }
  ],
  "rootCause": {
    "hypothesis": "Render reads items[0] after the last item is deleted.",
    "evidence": "TypeError: Cannot read properties of undefined (reading '0')",
    "confidence": "high" | "medium" | "low"
  },
  "attempts": [                           // every attempt across the whole run
    { "n": 1, "outcome": "fail",     "sessionId": "9fd0293f",
      "replayUrl": "https://www.browserbase.com/sessions/9fd0293f" },
    { "n": 2, "outcome": "reproduced","sessionId": "72bb755b",
      "replayUrl": "https://www.browserbase.com/sessions/72bb755b" }
  ],
  "consoleErrors": [ "TypeError: Cannot read properties of undefined (reading '0')" ]
}
```

**Per-step screenshot seam**: `run_repro` captures base64 PNGs per step but
`ReproResultPayload` (frozen `band.py`) does **not** surface them — so embedded
per-step screenshots depend on the **repro/synthesis layer** exposing them in
the report. The ReportCard **degrades gracefully**: if `screenshot` is null, the
step renders text-only and the card leans on the session replay link. Flag this
to the Repro/Arize worktrees as the data to plumb through.

---

## 7. Frontend components & state

```
frontend/
  index.html
  package.json · tsconfig.json · vite.config.ts
  vercel.json                      # static build config
  .env.example                     # VITE_API_BASE
  src/
    main.tsx
    App.tsx                        # run state machine (idle→submitting→streaming→report | error)
    api.ts                         # POST /runs, open EventSource, parse frames
    types.ts                       # RunReport, StreamEvent  (PLACEHOLDER — match Arize §6)
    components/
      UrlInput.tsx                 # the entry point; validates GitHub issue URL
      LiveLog.tsx                  # transcript (messages) + steps; auto-scroll, agent color-coding
      BrowserView.tsx              # live-view iframe → replay-link fallback (timeboxed)
      ReportCard.tsx               # final report; cursive verdict, steps+screenshots, replay links
    styles/
      tokens.css                   # OKLCH palette, type scale, spacing, z-index, motion vars
      app.css
    fixtures/
      recorded-run.json            # committed replay (forced fail→succeed run from STATUS.md)
backend/
  server.py                        # FastAPI app: REST + SSE
  run_manager.py                   # wraps phase6_live_run composition + run queue/tap
  replay.py                        # fixture replay with timing
  requirements.txt                 # fastapi, uvicorn, sse-starlette (or manual SSE)
```

**App state machine**: `idle` → `submitting` → `streaming` (LiveLog + BrowserView
live) → `report` (ReportCard swaps in; LiveLog collapses to a transcript pane) ·
`error` reachable from any state. A "Demo (replay)" toggle short-circuits to
replay mode.

**Component contracts** (one clear purpose each):
- `UrlInput(onSubmit)` — owns validation + the submit affordance.
- `LiveLog(events)` — pure render of the ordered event list; no fetching.
- `BrowserView(session)` — owns the iframe-or-link decision + its timeout.
- `ReportCard(report)` — pure render of a `RunReport`; degrades on null fields.

---

## 8. Visual / typographic system

- **Palette (OKLCH)**: near-black bg `oklch(0.17 0.012 75)`, raised surface
  `oklch(0.21 0.014 75)`, honey-gold accent `oklch(0.78 0.14 75)`, near-white
  ink `oklch(0.96 0.005 75)`, muted `oklch(0.70 0.02 75)`. Verify body contrast
  ≥4.5:1 (muted text must clear it too). Status hues: reproduced = gold,
  not_reproduced = cool-muted, error = restrained red.
- **Type**: Cormorant Garamond *italic* — wordmark + verdict only. Inter (or
  `system-ui`) — all UI text, fixed rem scale (1.2 ratio). `ui-monospace` /
  JetBrains Mono — transcript, console errors, code.
- **Motion**: 150–250 ms, ease-out; new log lines fade/slide in (staggered per
  arrival, not a uniform page-load reflex); `prefers-reduced-motion` →
  crossfade. The live stream and report are visible by default (no
  visibility-gated reveals).
- **Layout**: single column, generous left rail for the transcript spine; the
  BrowserView is the visual center during a run; the ReportCard takes the stage
  at the end. No card-grid; no eyebrow kickers; no gradient text.

---

## 9. Build order (replay-first, fallback-first)

1. **Scaffold** Vite+React+TS, tokens, wordmark, static layout shell.
2. **Replay path first** — `recorded-run.json` fixture + replay SSE + the app
   consuming it end-to-end (LiveLog + a stub ReportCard). The demo is safe from
   here on.
3. **ReportCard** against the placeholder schema (graceful null handling).
4. **BrowserView fallback first** (replay link), *then* timeboxed live-view
   iframe attempt.
5. **Live backend** — `POST /runs` + run_manager tap + live SSE.
6. **Polish** — motion, contrast pass, responsive, empty/error/loading states.
7. **Deploy** — Vercel static build; `VITE_API_BASE` documented; replay mode is
   the no-backend default.

---

## 10. Open seams to coordinate (flagged, not blocking)

1. **Report schema** (§6) — reconcile to the Arize worktree's final shape.
2. **Per-step screenshots** (§6) — needs the repro/synthesis layer to surface
   the base64 PNGs `run_repro` already captures.
3. **Browserbase live-view URL** (§5) — verify the streamable endpoint vs the
   replay URL against the live SDK before committing the iframe.
4. **Band tap** (§3.1) — choose callback-wrap vs logging-tap during build;
   never modify `band.py`; no fourth Band identity.
