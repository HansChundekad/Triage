# TRIAGE — Build Status & Phase 5 Handoff

_Last updated: 2026-06-20 · end of Phase 4 (ReproAgent real Browserbase integration — live verified)_

> For the agent starting Phase 5. Read this before touching any code.

---

## TL;DR

ReproAgent now drives a **real Browserbase browser** through the live buggy to-do app. The full session lifecycle is proven end-to-end: real browser opens, 5 steps execute (focus → type → add → delete → confirm), bug is detected via dual-signal logic, and real evidence is posted @HypothesisAgent in the Band room. Phase 5 replaces the hardcoded `_STEPS` in ReproAgent with real parsed steps from ParserAgent (GitHub issue → Claude → structured steps).

---

## Commits (main branch)

| Commit | What |
|---|---|
| `225103f` | Phase 3 complete / Phase 4 handoff in STATUS.md |
| `ff50ac9` | feat(repro): add playwright for CDP screenshots + console capture |
| `2ed1ad1` | feat(repro): TDD — DetectionResult + detect_bug with dual-signal logic |
| `c677cc1` | chore(repro): clarify BLANK_BODY_THRESHOLD comment |
| `4e6e2e8` | feat(repro): Part 1 — run_repro() full Browserbase/Stagehand session lifecycle |
| `9a5f3f9` | fix(repro): initialize detection before try — prevent UnboundLocalError |
| `4bc4efd` | feat(repro): wire run_repro() into Band handler — replace Phase 3 echo |
| `(this)` | feat(repro): add confirm-delete step + Phase 4 STATUS handoff |

All 43 tests pass: `.venv/bin/pytest`. `main` pushed to origin.

---

## Repo shape

```
triage/
  config.py              # fail-loud loader
  shared/band.py         # BandAgent + ReproStepsPayload/ReproResultPayload/HypothesisPayload
  parser_agent/
    echo.py              # still echo stub — Phase 5 replaces with real GitHub fetch + Claude
    __main__.py
  repro_agent/
    browser.py           # REAL: DetectionResult, detect_bug(), run_repro() ← Phase 4 hero
    echo.py              # Band handler: calls run_repro(), posts evidence @HypothesisAgent
    __main__.py
  hypothesis_agent/
    agent.py             # still echo stub — Phase 5 or 6 replaces with real Claude diagnosis
    __main__.py
scripts/
  handshake.py
  three_way_smoke.py
  test_echo_chain.py     # Phase 3 integration harness (echo chain) — still valid for Band layer
docs/
  TRIAGE_OVERVIEW.md · TRIAGE_INTEGRATIONS.md · STATUS.md
tests/
  test_config.py · test_band_module.py · test_parser_echo.py
  test_repro_echo.py · test_hypothesis_agent.py · test_repro_browser.py  ← Phase 4 new
```

---

## What Phase 4 proved (live end-to-end)

ReproAgent drives a real Browserbase session against `cfg.app_url`:

| Step | What happens |
|---|---|
| Session start | `AsyncStagehand` boots local SEA binary, creates Browserbase session, returns `session_id` + `cdp_url` |
| Playwright CDP | Python Playwright connects to `cdp_url` alongside Stagehand — registers console/pageerror listeners |
| Navigate | `session.navigate(url=cfg.app_url)` |
| focus input | observe → act |
| type task | act |
| click add | observe → act |
| click delete | observe → act → **confirmation popup appears** |
| confirm delete | observe → act (click Yes) → **app crashes** |
| Extract | `session.extract()` → body_text = "TaskFlow" (8 chars — blank) |
| detect_bug | `blank_body=True` (8 < 10) AND `console_match=True` (1 real TypeError) → `bug_detected=True` |
| Report | `ReproResultPayload` posted @HypothesisAgent: `verdict: BUG REPRODUCED`, real session URL |

**Live run result (session `928c369a`):**
```
bug_detected=True, blank_body=True, console_match=True
1 console error captured
verdict: BUG REPRODUCED
```

---

## The shared Band module — unchanged

```python
from triage.shared.band import BandAgent, AgentName
from triage.shared.band import ReproStepsPayload, ReproResultPayload, HypothesisPayload

ReproResultPayload(success, evidence, console_errors, session_url)
```

---

## Config (triage/config.py) — unchanged

```python
cfg.browserbase_api_key / cfg.browserbase_project_id
cfg.anthropic_api_key
cfg.app_url          # live buggy to-do app (set in .env)
cfg.github_issue_url # bug report ParserAgent will parse in Phase 5
```

---

## Key detection constants (triage/repro_agent/browser.py)

```python
BLANK_BODY_THRESHOLD = 10   # body chars after strip; <10 = blank/crashed
CRASH_SUBSTRING = "Cannot read properties of undefined"
```

Tune these at the top of `browser.py` — they are intentionally separated from the step logic.

---

## Hardcoded steps (triage/repro_agent/browser.py `_STEPS`)

**Phase 5 replaces this with real parsed steps from ParserAgent.** For now, 5 steps are hardcoded:

```python
_STEPS = [
    ("focus input",    "find the task text input field",              "click the task text input field to focus it"),
    ("type task",      None,                                           "type 'test task' into the focused input field"),
    ("click add",      "find the Add button to submit the task",      "click the Add button to add the task to the list"),
    ("click delete",   "find the Delete button next to the task item","click the Delete button to remove the task"),
    ("confirm delete", "find the confirmation popup with yes and no options", "click the Yes button to confirm deletion"),
]
```

When Phase 5 lands, `handle_parser_message` in `echo.py` should parse the steps out of the incoming Band message and pass them to `run_repro()` instead of using `_STEPS`.

---

## Hard rules (do not violate)

1. Agent names: `ParserAgent`, `ReproAgent`, `HypothesisAgent` only.
2. Every `send_message` needs ≥1 `@mention`.
3. `send_message` = directed talk. `send_event` = logs. Never mixed.
4. **All browser/Stagehand work stays in `triage/repro_agent/browser.py`.**
5. **New Browserbase session per retry** — never reuse `session_id`.
6. Verify SDK details against live docs before integration code; flag drift.
7. `bug.detected` must be honest — the fail→succeed flip must be real.

---

## Phase 5 — what to build next

**ParserAgent (the next hero):** replace the echo stub with real logic:

1. Fetch the GitHub issue at `cfg.github_issue_url` via `httpx`
2. Call `claude-sonnet-4-6` to extract structured repro steps from the issue prose — including unstated preconditions (e.g. "add a task first" before deleting)
3. Return a `ReproStepsPayload` with the steps list
4. Post into the Band room @mentioning ReproAgent
5. Wrap the Claude call in an Arize Phoenix span

**ReproAgent change needed for Phase 5:** `handle_parser_message` in `echo.py` currently ignores the incoming steps and uses hardcoded `_STEPS`. Phase 5 should parse the steps from the Band message payload and pass them into `run_repro()`.

**Read before coding:** `TRIAGE_OVERVIEW.md`, `TRIAGE_INTEGRATIONS.md` §3 (Band) and §4 (Arize Phoenix), and the current Anthropic SDK docs.
