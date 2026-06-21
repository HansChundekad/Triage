# TRIAGE frontend backend

Thin FastAPI shim. Wraps the real 3-agent run (same composition as
`scripts/phase6_live_run.py`) and streams the Band transcript + browser steps
over SSE. **Never modifies `band.py`**; observes the run by wrapping each
`BandAgent` instance's `send_message`/`send_event` at composition time. No
fourth Band identity.

## Run

    .venv/bin/pip install -r backend/requirements.txt
    .venv/bin/uvicorn backend.server:app --port 8000

Requires the same `.env` the agents use (Browserbase / Band / Anthropic keys).

## Endpoints

- `POST /api/runs` `{issueUrl}` → `{runId}` (validates a GitHub issue URL)
- `GET  /api/runs/{id}/stream`  SSE: `status | message | report | error`
  (`message` = directed @mention talk, `step` = browser/event logs)
- `GET  /api/runs/{id}`         snapshot (`{runId, done, events}`)
- `GET  /api/replays`           server-side fixtures (none — the frontend bundles its own)

## Honest verdict

`reproduced` is derived from the live transcript: the tap calls
`triage.repro_agent.loop.is_confirm(...)` on HypothesisAgent→ReproAgent messages
and flips `run.reproduced` only on a real confirmation — never from a faked or
assumed state field.

## Known follow-up

The backend currently surfaces Browserbase sessions to the frontend at report
time (via `attempts[].replayUrl`). Streaming a per-attempt `session` SSE event
mid-run (so the live-view iframe appears while the browser is still driving)
means extracting the session id from the tapped ReproAgent messages — a
follow-up, not wired here.
