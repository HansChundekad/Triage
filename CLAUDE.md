# TRIAGE — Agent Context

Autonomous bug-reproduction agent (UC Berkeley AI Hackathon 2026). A developer
pastes a GitHub issue; TRIAGE opens a real cloud browser, clicks through a live
app to trigger the bug, captures the crash + console error, diagnoses root
cause, and writes a structured report.

**Source of truth:** `docs/TRIAGE_OVERVIEW.md` (product + architecture) and
`docs/TRIAGE_INTEGRATIONS.md` (connectivity reference). Read both before doing
integration work. The build plan history lives in `docs/superpowers/plans/`.

## Architecture (three agents, one Band room)

- **ParserAgent** (`triage/parser_agent/`) — GitHub issue → structured repro
  steps (incl. unstated preconditions). Posts into the Band room @mentioning ReproAgent.
- **ReproAgent** (`triage/repro_agent/`) — the hero. Drives a real Browserbase
  browser via Stagehand, screenshots each step, captures console errors, reports
  to HypothesisAgent. **ALL browser work lives here, nowhere else.**
- **HypothesisAgent** (`triage/hypothesis_agent/`) — diagnoses root cause, can
  redirect ("@ReproAgent retry with a slower delete"). That redirect is the loop.
- **Shared** (`triage/shared/band.py`) — Band coordination layer. Currently a
  STUB (`connect()` raises NotImplementedError, no SDK import). Phase 2 implements it.

## Non-negotiable rules (from the architecture — do not violate)

1. **All browser work in ReproAgent only.** Never spread Stagehand calls.
2. **Every cross-agent Band message must @mention.** No @mention = no recipient.
3. **Never name an agent generically** ("Agent"/"Bot"/"Assistant"). Only
   `ParserAgent` / `ReproAgent` / `HypothesisAgent`.
4. **Three distinct Band identities** — separate API key + agent ID each
   (`BAND_PARSER_*`, `BAND_REPRO_*`, `BAND_HYPOTHESIS_*`).
5. **New Browserbase session per retry** (no sessionId) — clean state + per-attempt replay URL.
6. **Messages = directed talk (@mention); Events = logs.** Don't mix them.
7. **Verify integration details against live docs before coding** — the
   integration doc is a baseline; live docs win. Flag drift.
8. **`bug.detected` in Arize traces must be honest** — the fail→succeed flip must be real.

## Tech decisions (locked)

- **All-Python.** One runtime (Stagehand has a Python SDK; Band SDK + Phoenix
  are Python-native).
- **Python 3.14** (Homebrew). The full stack installs cleanly on 3.14 — no wheel
  gaps. See `docs/TRIAGE_INTEGRATIONS.md` §6 for the language tradeoff rationale.
- **Packaging:** `pyproject.toml` (hatchling). Integration SDKs are LISTED in
  `[project.dependencies]` but were only relevant from Phase 2 on.

## How to run

```bash
.venv/bin/pip install -e ".[dev]"   # venv already exists at repo root (gitignored)
.venv/bin/pytest                    # run tests
cp .env.example .env                # then fill in keys (.env is gitignored)
```

- Config loader: `from triage.config import load_config` → returns frozen
  `Config` (with three `BandIdentity` objects) or raises `MissingConfigError`
  listing every missing var. Empty strings count as missing.
- **Use the repo `.venv`** — run Python/pytest via `.venv/bin/...`.

## Status

- **Phase 1 (repo scaffold): COMPLETE.** Commits `7866f05`, `ec9ff4e`, `d697d3c`
  on `main`. Package skeleton, packaging, complete `.env.example` + gitignored
  `.env`, and a fail-loud config loader with 6 passing tests. No agent logic or
  integration code yet.
- **Phase 2 (shared Band module): NEXT.** Implement `triage/shared/band.py`
  against `band-sdk`. Per the integration doc: prove the three-way handshake
  (all three agents join a room, post, and receive via @mention) BEFORE any real
  agent logic. Need from the user: Band SDK + Stagehand Python doc links, and
  real Band credentials in `.env`. Worktrees become useful here for parallel
  ParserAgent/HypothesisAgent work.

## Build order (full roadmap, from the overview)

1. Buggy target app (deliberately buggy to-do app → Vercel, with a GitHub issue) ·
2. Issue parsing · 3. Browserbase+Stagehand executor (the hard part) ·
4. Capture layer (screenshots, console errors, bug-detection) · 5. Band
coordination (3 agents, @mention, retry loop) · 6. Arize tracing · 7. Claude
synthesis · 8. Minimal frontend.

## Conventions used this far

- Per-task commits with scoped messages; secrets/tooling gitignored
  (`.env`, `.claude/`, `.agents/`, `.impeccable/`, `skills-lock.json`, `.superpowers/`, `.venv/`).
- TDD for real logic (config loader was RED→GREEN).
- Arize skills are available in this environment (`arize-instrumentation`, etc.)
  and should be used for the tracing phase.
