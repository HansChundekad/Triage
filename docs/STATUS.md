# TRIAGE — Build Status & Phase 4 Handoff

_Last updated: 2026-06-20 · end of Phase 3 (three-agent echo chain merged + integration-proven)_

> For the agent starting Phase 4. Read this before touching any code.

---

## TL;DR

All three agents exist and coordinate end-to-end **as echo stubs**. The Band
choreography (issue trigger → steps → repro result → diagnosis, routed by
`@mention` in one room) is proven live and reproducible. Phase 4 replaces the
echoes with real logic — it does **not** need to touch the coordination layer.

---

## Commits (main branch, pushed to origin)

| Commit | What |
|---|---|
| `636e8ab` `f8a42d1` `853f8e7` | Phase 3: ParserAgent echo — placeholder steps, on_message ack, runnable process |
| `7e7772f` `1308499` `3cab044` | Phase 3: ReproAgent echo — fake result core, handler, three-way smoke |
| `0f5aa40` `30fdfaf` `a3399ed` | Phase 3: HypothesisAgent echo — callback, entrypoint, live demo |
| `7fa9411` `a2405f5` `ac117ef` | Phase 3: merges of parser / repro / hypothesis branches into main (0 conflicts) |
| `19828f5` | Phase 3: echo-chain integration harness — 3 live runs × 5 checks |

All 34 tests pass: `.venv/bin/pytest`. `main` is pushed and even with `origin/main`.

**Branch hygiene:** the empty `phase3-hypothesis` branch was deleted (the real
HypothesisAgent work lives on `worktree-phase3-hypothesis-agent`). The
`phase3-parser`, `phase3-repro`, and `worktree-phase3-hypothesis-agent` branches
and their worktrees are merged and prunable when convenient.

---

## Repo shape

```
triage/
  config.py              # fail-loud loader — reads all env vars, raises on missing
  shared/band.py         # BandAgent class + ReproStepsPayload/ReproResultPayload/HypothesisPayload
  parser_agent/
    echo.py              # pure echo logic: hardcoded steps, message format, sender→name map
    __main__.py          # runnable: connect, self-post @ReproAgent ~2s after connect, listen
  repro_agent/
    echo.py              # pure echo logic + run(): NO browser yet — posts a hardcoded fake result
    __main__.py
  hypothesis_agent/
    agent.py             # echo callback + run(): NO Claude yet — posts a hardcoded diagnosis
    __main__.py
scripts/
  handshake.py           # Phase 2 two-agent live proof
  three_way_smoke.py     # single-process three-way proof (uses test doubles)
  test_echo_chain.py     # Phase 3 integration harness — spawns all 3 real agents, 3 runs, 5 checks
tests/
  test_config.py · test_band_module.py · test_parser_echo.py
  test_repro_echo.py · test_hypothesis_agent.py    # 34 tests total
docs/
  TRIAGE_OVERVIEW.md · TRIAGE_INTEGRATIONS.md · STATUS.md
```

---

## What Phase 3 proved (the echo chain)

Each agent is an **echo stub** — no real GitHub fetch, no real browser, no real
Claude. They exist to prove three-agent Band coordination:

| Agent | Trigger | Phase 3 behaviour (echo only) |
|---|---|---|
| **ParserAgent** | self-posts ~2s after connect | Emits hardcoded steps `["focus input","type task","click add","click delete"]`; posts `@ReproAgent extracted 4 steps … (issue: <url>)`. Acks Repro/Hypothesis if they @mention it. |
| **ReproAgent** | ParserAgent's @mention | **No browser.** Logs steps, then posts a hardcoded fake `ReproResultPayload` `@HypothesisAgent` (verdict BUG REPRODUCED, fake evidence + TypeError, placeholder session_url). Ignores HypothesisAgent replies → chain ends. |
| **HypothesisAgent** | ReproAgent's @mention (sender-id verified) | **No Claude.** Posts a hardcoded `HypothesisPayload` `@ReproAgent` (root cause + `redirect=None`). Ignores non-Repro senders. |

### Integration harness — `scripts/test_echo_chain.py`

Run it: `.venv/bin/python scripts/test_echo_chain.py`

Spawns all three real agents as separate processes against the **live** Band
room (listeners first, ParserAgent last as the trigger), mints a **fresh room
per run** for isolation, runs **3 consecutive times**, and asserts 5 checks each:

1. **ALL THREE CONNECTED** — every agent joined promptly (~1.0–1.1s observed)
2. **MENTION ROUTING IS EXCLUSIVE** — strict order Parser→Repro→Hypothesis, correct targets, Hypothesis never speaks before Repro
3. **CHAIN COMPLETED** — all three posted with no manual nudging
4. **TRANSCRIPT READS LIKE A CONVERSATION** — correct `@mention` in each message
5. **WEBSOCKETS STAYED ALIVE** — no reconnect / closed / error events

Last result: **3/3 runs PASS, 5/5 checks each.** Canonical transcript:

```
[ParserAgent → ReproAgent]:     @ReproAgent extracted 4 steps: focus input, type task, click add, click delete (issue: …)
[ReproAgent → HypothesisAgent]: @hanschundekad/hypothesisagent repro result … verdict: BUG REPRODUCED …
[HypothesisAgent → ReproAgent]: @hanschundekad/reproagent confirmed … Root cause: reading items[0] after delete …
```

Note: two intentional deviations from a literal observer-driven test — (a) no 4th
"observer" identity exists, so ParserAgent's startup self-post IS the trigger;
(b) the transcript is reconstructed from each agent's own logged sends.

---

## The shared Band module — reused unchanged by every agent

```python
from triage.shared.band import BandAgent, AgentName
from triage.shared.band import ReproStepsPayload, ReproResultPayload, HypothesisPayload

agent = BandAgent(name="ReproAgent", agent_id=..., api_key=..., on_message=cb)
room_id = await agent.connect(room_id=cfg.band_room_id)  # None → creates a room
await agent.add_participant("HypothesisAgent")            # before that agent connects
await agent.send_message(["HypothesisAgent"], "text")     # ≥1 mention required
await agent.send_event("doing X", "task")                 # thought|error|task — no mention
await agent.disconnect()
# on_message: async def cb(payload, agent) — payload has .sender_id/.sender_name/.content
```

```python
ReproStepsPayload(issue_url, steps)
ReproResultPayload(success, evidence, console_errors, session_url)
HypothesisPayload(root_cause, redirect)   # redirect != None → "retry with this tweak"
```

---

## Config (triage/config.py)

`load_config()` reads `.env`, raises `MissingConfigError` listing every missing var.

```python
cfg.anthropic_api_key
cfg.browserbase_api_key / cfg.browserbase_project_id
cfg.band_parser/.band_repro/.band_hypothesis  → .agent_id / .api_key
cfg.band_room_id                # str | None — currently EMPTY in .env (see below)
cfg.github_issue_url            # the bug report ParserAgent will parse for real in Phase 4
cfg.app_url                     # the live app ReproAgent will drive in Phase 4
cfg.phoenix_api_key / cfg.phoenix_collector_endpoint
```

⚠️ **`BAND_ROOM_ID` is empty in `.env`.** With no shared room, three separate
processes each create their own room and never see each other. The harness works
around this by minting a room per run. Phase 4 should either keep that
create-per-run pattern or set a persistent `BAND_ROOM_ID` (and add all three as
participants) before launching agents separately.

---

## Hard rules (do not violate)

1. Agent names: `ParserAgent`, `ReproAgent`, `HypothesisAgent` only. Never generic.
2. Every `send_message` needs ≥1 `@mention` (BandAgent enforces). No mention = no one sees it.
3. `send_message` = directed talk. `send_event` = logs. Never mixed.
4. Room creator must `add_participant(name)` for every other agent before they connect.
5. **All browser/Stagehand work stays in ReproAgent.** None in Parser or Hypothesis.
6. **New Browserbase session per retry** — never reuse `sessionId`.
7. Verify SDK details against live docs before integration code; flag drift.
8. Arize `bug.detected` must be honest — the fail→succeed flip must be real.

---

## Phase 4 — what to build next (replace the echoes with real logic)

The coordination scaffold is done and proven. Phase 4 swaps stub behaviour for
real behaviour, agent by agent, without changing the Band layer:

- **ReproAgent (the big one):** real Browserbase/Stagehand. Open a new session,
  drive the live app at `cfg.app_url` through the received steps, capture real
  evidence (screenshots, console errors, session URL) into `ReproResultPayload`.
  New session per retry. This is where the honest fail→succeed flip lives.
- **ParserAgent:** fetch the real issue at `cfg.github_issue_url` (httpx) and call
  `claude-sonnet-4-6` to turn prose into `ReproStepsPayload.steps`. Wrap the Claude
  call in an Arize Phoenix span.
- **HypothesisAgent:** real Claude diagnosis from `ReproResultPayload`; set
  `redirect` to drive a retry through ReproAgent when the evidence is inconclusive.
- **Arize:** emit an honest `bug.detected` only when a real repro flips fail→succeed.

**Before writing code, read:** `TRIAGE_OVERVIEW.md` (architecture),
`TRIAGE_INTEGRATIONS.md` §3 (Band — proven), §4 (Arize Phoenix), and the current
Anthropic + Browserbase/Stagehand SDK docs (verify against live docs; flag drift).
