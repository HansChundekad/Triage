# TRIAGE

Autonomous bug-reproduction agent (UC Berkeley AI Hackathon 2026). Reproduces a
reported bug by driving a real cloud browser through a live app, then diagnoses
and reports root cause.

**Read first:** `docs/TRIAGE_OVERVIEW.md` (architecture, source of truth) and
`docs/TRIAGE_INTEGRATIONS.md` (how to connect Browserbase/Band/Arize).
**Current state / what's next:** `docs/STATUS.md`.

## Architecture

Three agents coordinate in one Band room:
- **ParserAgent** (`triage/parser_agent/`) — GitHub issue → structured repro steps.
- **ReproAgent** (`triage/repro_agent/`) — drives the Browserbase browser.
- **HypothesisAgent** (`triage/hypothesis_agent/`) — diagnoses, can redirect for retry.
- Shared Band layer: `triage/shared/band.py`. Config loader: `triage/config.py`.

## Non-negotiable rules

1. All browser/Stagehand work lives in **ReproAgent only**.
2. Every cross-agent Band message must **@mention** a recipient (no @mention = no one sees it).
3. Agent names are exact: `ParserAgent` / `ReproAgent` / `HypothesisAgent` — never generic.
4. Three **distinct Band identities** (`BAND_PARSER_*`, `BAND_REPRO_*`, `BAND_HYPOTHESIS_*`).
5. **New Browserbase session per retry** (no sessionId).
6. Band **messages** = directed @mention talk; **events** = logs. Don't mix.
7. **Verify SDK details against live docs before writing integration code**; flag drift.
8. Arize `bug.detected` must be honest — the fail→succeed flip must be real.

## Commands

Always use the repo venv (`.venv/`):
- Install: `.venv/bin/pip install -e ".[dev]"`
- Test: `.venv/bin/pytest`
- Config is loaded via `from triage.config import load_config` (fails loud on missing env vars).

## Conventions

- All-Python; target Python 3.11+ (dev on 3.14).
- TDD for real logic (write the failing test first).
- Per-task commits, scoped messages. Never commit secrets — `.env` is gitignored;
  keep `.env.example` in sync when adding a config var.
- When adding a config var: update `.env.example`, `triage/config.py`, and its test together.
