# TRIAGE frontend

Vite + React + TS. Paste a GitHub issue URL → watch the three agents coordinate
(Parser → Repro → Hypothesis) and the real cloud browser run → read the report
card. A thin shell over the TRIAGE agents (architecture in `docs/TRIAGE_OVERVIEW.md`).

## Dev

    cd frontend && npm install && npm run dev       # replay-only (no backend)
    VITE_API_BASE=http://localhost:8000 npm run dev # live (backend running)

The **Demo** button always plays a committed recorded run (`src/fixtures/recorded-run.json`)
with no backend or network — the demo safety net. **Run** kicks off a live run
against `VITE_API_BASE`.

## Test

    npm test

## Deploy (Vercel)

Static build (`npm run build` → `dist/`, config in `vercel.json`). Leave
`VITE_API_BASE` unset for a replay-only public deploy; set it to a reachable
backend for live runs.

## Seams to reconcile (flagged, cross-worktree)

- `src/types.ts` `RunReport` is a PLACEHOLDER — match the Arize worktree's
  synthesis schema; where they diverge, Arize wins.
- Per-step screenshots are `null` until the repro/synthesis layer surfaces the
  base64 PNGs `run_repro` already captures; the report card degrades to the
  session replay link.
- The Browserbase live-view URL equals the replay URL until the streamable
  live-view endpoint is verified against the live SDK.
- Live runs only surface a session panel at report time today; mid-run live
  `session` streaming is a follow-up (see `backend/README.md`).
