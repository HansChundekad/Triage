# TRIAGE — Build Status & Phase 3 Handoff

_Last updated: 2026-06-20 · end of Phase 2_

> For the agent starting Phase 3. Read this before touching any code.

---

## Commits (main branch)

| Commit | What |
|---|---|
| `7866f05` | Phase 1: package skeleton, pyproject.toml, gitignore, README |
| `ec9ff4e` | Phase 1: .env.example + gitignored .env |
| `d697d3c` | Phase 1: fail-loud config loader + 6 tests |
| `6dfcf9c` | Phase 2: BAND_ROOM_ID added to Config (optional) |
| `fb75979` | Phase 2: shared Band module — BandAgent + message schemas + 9 tests |
| `05fde97` | Phase 2: two-agent handshake script (live-proven against real Band API) |

All 18 tests pass. `source .venv/bin/activate && pytest` to verify.

---

## Repo shape

```
triage/
  config.py              # fail-loud loader — reads all env vars, raises on missing
  shared/
    band.py              # BandAgent class + ReproStepsPayload/ReproResultPayload/HypothesisPayload
    __init__.py          # re-exports all of the above
  parser_agent/          # EMPTY — Phase 3 builds this
  repro_agent/           # EMPTY — Phase 4
  hypothesis_agent/      # EMPTY — Phase 4
scripts/
  handshake.py           # live two-agent proof — run this to sanity-check credentials
tests/
  test_config.py         # 9 tests
  test_band_module.py    # 9 tests
docs/
  TRIAGE_OVERVIEW.md     # system design — read before making architecture decisions
  TRIAGE_INTEGRATIONS.md # Band/Browserbase/Arize details — read §3 (Band) and §4 (Arize)
```

---

## What Phase 2 proved (the Band handshake)

`scripts/handshake.py` ran live:

1. ReproAgent connected WebSocket → created room `e24d8680-5f8c-48b8-af0c-0838001901b2`
2. ReproAgent added ParserAgent as room participant (required before ParserAgent can subscribe)
3. ParserAgent connected its own WebSocket
4. ParserAgent sent `@ReproAgent` a message with repro steps
5. ReproAgent received it via WebSocket subscription, replied `@ParserAgent`
6. Both connections stayed alive; both shut down cleanly

**SDK drift discovered:** Band rejects WebSocket subscription unless the agent is already a room participant. `BandAgent.add_participant(name)` handles this. Not in the doc.

---

## The shared Band module — what Phase 3 imports

```python
from triage.shared.band import BandAgent, AgentName
from triage.shared.band import ReproStepsPayload, ReproResultPayload, HypothesisPayload
```

### BandAgent interface (triage/shared/band.py)

```python
agent = BandAgent(
    name="ParserAgent",         # Literal["ParserAgent","ReproAgent","HypothesisAgent"]
    agent_id=cfg.band_parser.agent_id,
    api_key=cfg.band_parser.api_key,
    on_message=async_callback,  # async def cb(payload: MessageCreatedPayload, agent: BandAgent)
)
room_id = await agent.connect(room_id=cfg.band_room_id)  # None → creates new room
await agent.add_participant("ReproAgent")   # call before other agent connects
await agent.send_message(["ReproAgent"], "text")  # ≥1 mention required, raises ValueError otherwise
await agent.send_event("doing X", "thought")      # thought | error | task — no mention needed
await agent.disconnect()
```

### Message schemas

```python
ReproStepsPayload(issue_url: str, steps: list[str])
ReproResultPayload(success: bool, evidence: list[str], console_errors: list[str], session_url: str)
HypothesisPayload(root_cause: str, redirect: str | None)
```

---

## Config (triage/config.py)

`load_config()` reads `.env` and raises `MissingConfigError` listing every missing var. Key fields for Phase 3:

```python
cfg.anthropic_api_key           # Claude API — FILLED IN
cfg.band_parser.agent_id / .api_key
cfg.band_repro.agent_id / .api_key
cfg.band_room_id                # str | None — None means create room at runtime
cfg.github_issue_url            # https://github.com/HansChundekad/StrideAI/issues/1
cfg.app_url                     # https://hanschundekad.github.io/StrideAI/
```

`.env` is fully filled in — all Band, Browserbase, Phoenix, Anthropic credentials are present.

---

## Hard rules (from TRIAGE_INTEGRATIONS.md §7 — do not violate)

1. Agent names: `ParserAgent`, `ReproAgent`, `HypothesisAgent` only. Never generic.
2. Every `send_message` call needs ≥1 mention. `BandAgent` enforces this.
3. `send_message` = directed talk. `send_event` = logs. Never mixed.
4. Room creator must call `add_participant(name)` for every other agent before they connect.
5. All browser work stays in ReproAgent. No Stagehand in Parser or Hypothesis.
6. New Browserbase session per retry (no reusing `sessionId`).

---

## Phase 3 — what to build next: ParserAgent

ParserAgent is the simplest agent — no browser, no retry loop, just:

1. `load_config()` → get credentials
2. Fetch GitHub issue body at `cfg.github_issue_url` via `httpx`
3. Call `claude-sonnet-4-6` to parse prose → `ReproStepsPayload(issue_url, steps)`
4. Connect to Band room as ParserAgent; add ReproAgent as participant
5. Serialize `ReproStepsPayload` to a readable string and `send_message(["ReproAgent"], ...)`
6. Wrap the Claude call in an Arize Phoenix span (see TRIAGE_INTEGRATIONS.md §4) — `auto_instrument=True` captures it automatically

**Before writing any code, read:**
- `TRIAGE_INTEGRATIONS.md §4` (Arize Phoenix) — set up tracing at the top of the agent; it auto-instruments all Claude calls with zero extra code
- Anthropic Python SDK docs for current `claude-sonnet-4-6` Messages API
- `TRIAGE_INTEGRATIONS.md §3` (Band) — already proven; just use `BandAgent`
