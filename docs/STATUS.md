# TRIAGE — Build Status & Phase 7 Handoff

_Last updated: 2026-06-20 · end of Phase 6 (retry loop closed — live verified, including a forced fail→succeed)_

> For the agent starting Phase 7 (Arize tracing). Read this before touching any code.

---

## TL;DR

**All three agents are real and the coordination loop is closed.** ParserAgent fetches the live GitHub issue and Claude turns it into structured steps; ReproAgent drives a **real Browserbase browser** through those steps with dual-signal bug detection; HypothesisAgent diagnoses root cause and routes `confirm` / `redirect_repro` / `redirect_parser` by @mention. On a redirect, ReproAgent spins a **fresh** Browserbase session and retries, bounded by a hard cap that always terminates. Verified live end-to-end, including a deliberate **fail → re-parse → succeed** run. Phase 7 wraps this loop in **Arize Phoenix** spans so the progression is traceable.

---

## Commits (main branch) — Phase 6

| Commit | What |
|---|---|
| `4efa525` | feat(repro): consume real Parser steps — replace hardcoded `_STEPS` |
| `5390da8` | feat(repro): retry loop — `redirect_repro` spins fresh session + retries |
| `50c87be` | feat(repro): loop safety — hard cap + terminal states, never spins |
| `f7fe381` | fix(parser,hypothesis): real repro steps (A) + sharper retry routing (C) |
| `9a069e2` | chore(scripts): phase6 live-run harness (real 3-agent end-to-end) |
| `0effc77` | feat(scripts): `--force-retry` — drive a live fail→succeed via `redirect_parser` |

Preceded by the Phase 5 merges (`54a4607` parser, `80ce128` hypothesis). **84 tests pass:** `.venv/bin/pytest`.

---

## Repo shape

```
triage/
  config.py              # fail-loud loader (band_parser/repro/hypothesis identities)
  shared/band.py         # BandAgent + payloads — UNCHANGED since Phase 4 (hash 3656ea5d)
  parser_agent/
    github.py            # fetch_issue() — httpx public GET
    claude.py            # extract_steps() — Claude → structured steps (+ precondition prompt)
    agent.py             # format_steps_message(), make_on_message(), post_initial_steps()
    __main__.py
  repro_agent/
    browser.py           # detect_bug(), run_repro(cfg, steps, tweak=None) ← real browser
    loop.py              # parse_steps, classify_message, is_confirm, extract_tweak,
                         #   ReproLoopState, format_giveup_message, MAX_REPRO_ATTEMPTS
    echo.py              # make_repro_callback(cfg, state) — stateful retry loop + _run_attempt
    __main__.py
  hypothesis_agent/
    reasoning.py         # diagnose() — Claude root-cause + confirm/redirect decision
    agent.py             # route_diagnosis(), make_diagnosis_callback()
    __main__.py
scripts/
  phase6_live_run.py     # real 3-agent end-to-end harness; --force-retry drives fail→succeed
  three_way_smoke.py     # Phase 3 throwaway — STALE (imports removed handle_parser_message)
docs/
  TRIAGE_OVERVIEW.md · TRIAGE_INTEGRATIONS.md · STATUS.md
tests/
  test_config.py · test_band_module.py · test_repro_browser.py · test_repro_echo.py
  test_repro_loop.py ← Phase 6 · test_parser_*.py · test_hypothesis_*.py
```

---

## What Phase 6 proved (live end-to-end)

The full loop, all real, no faked detection:

1. **Parser → Repro fully live.** ReproAgent parses ParserAgent's numbered-line block (`parse_steps`) and drives those exact steps — the hardcoded `_STEPS` is gone.
2. **Retry on a fresh session.** A `redirect` from HypothesisAgent triggers a new `run_repro` call → a brand-new Browserbase session (no reused `sessionId`), carrying the redirect's tweak.
3. **Loop safety.** `MAX_REPRO_ATTEMPTS = 3` (single knob in `loop.py`). Two latched terminal states — **bug confirmed** and **could-not-reproduce after N** (posts one give-up message + stops). Once terminal, all further redirects/confirms are ignored — the loop can **never** spin. A fresh Parser steps message resets the cycle (`redirect_parser` re-parse path).

### Three live runs

| Run | Outcome | Evidence |
|---|---|---|
| Success-first | confirm on attempt 1 → terminal | both detection signals fired; `attempts 1/3` |
| Give-up | 3 attempts fail → "could not reproduce after 3 attempts" → terminal | **no hang**; cap held under repeated redirects |
| **Forced retry** (`--force-retry`) | attempt 1 fail → `redirect_parser` → re-parse → attempt 2 reproduces → confirm | sessions `9fd0293f` (fail) → `72bb755b` (reproduce); honest `bug.detected` False→True |

### The coordination transcript (forced-retry run)

> **ParserAgent** → @ReproAgent: repro steps *(deliberately incomplete: delete-only)*
> **ReproAgent** → @HypothesisAgent: BUG NOT REPRODUCED — list was empty, session `9fd0293f`
> **HypothesisAgent** → @ParserAgent: "steps must first create tasks before deleting" *(`redirect_parser`)*
> **ParserAgent** → @ReproAgent: revised steps *(type → Add → delete → confirm)*
> **ReproAgent** → @HypothesisAgent: BUG REPRODUCED — blank page + TypeError, session `72bb755b`
> **HypothesisAgent** → @ReproAgent: "confirmed, matches the report … Repro valid."

---

## Key tunables

```python
# triage/repro_agent/loop.py
MAX_REPRO_ATTEMPTS = 3        # initial attempt + up to 2 retries; single dial

# triage/repro_agent/browser.py
BLANK_BODY_THRESHOLD = 10     # body chars after strip; <10 = blank/crashed
CRASH_SUBSTRING = "Cannot read properties of undefined"
```

---

## Hard rules (do not violate)

1. Agent names: `ParserAgent`, `ReproAgent`, `HypothesisAgent` only.
2. Every `send_message` needs ≥1 `@mention`.
3. `send_message` = directed talk. `send_event` = logs. Never mixed.
4. **All browser/Stagehand work stays in `triage/repro_agent/`** (browser.py).
5. **New Browserbase session per retry** — never reuse `session_id`.
6. Verify SDK details against live docs before integration code; flag drift.
7. `bug.detected` must be honest — the fail→succeed flip must be real. *(It is: Phase 6's forced run flips False→True for real reasons.)*
8. **Do not modify `triage/shared/band.py`** — stop and ask if it seems necessary.

---

## Phase 7 — what to build next (Arize Phoenix tracing)

Wrap the retry loop in spans so the fail→adjust→succeed progression is visible (`TRIAGE_INTEGRATIONS.md` §4).

1. Set up the OpenTelemetry/Phoenix tracer (`cfg.phoenix_api_key`, `cfg.phoenix_collector_endpoint`).
2. Span the Claude calls (Parser `extract_steps`, Hypothesis `diagnose`) and each `run_repro` attempt.
3. Emit an honest `bug.detected` attribute that flips across attempts; embed each attempt's **session replay URL**.

**Carry-forward from Phase 6 (do this in Phase 7):** `ReproLoopState.reset()` clears `session_urls` on a `redirect_parser` re-parse, so state-held URLs from before the re-parse are dropped (they survive only in the Band event transcript). For tracing, accumulate session replay URLs at the **run** level (separate from the per-cycle state) so the trace embeds *every* attempt across the whole run.

**Read before coding:** `TRIAGE_OVERVIEW.md`, `TRIAGE_INTEGRATIONS.md` §4 (Arize Phoenix), and the current Arize/OpenInference SDK docs (verify span/attribute API before writing).
