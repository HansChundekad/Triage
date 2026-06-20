# TRIAGE — What's been done so far

_Last updated: 2026-06-20 · end of Phase 1_

## Where we are

**Phase 1 (repo scaffold) is complete.** No agent logic or integration code yet —
just a clean, all-Python foundation that runs and is tested.

## What exists now

```
triage/
  config.py            # fail-loud env loader (the only real logic so far)
  parser_agent/        # ParserAgent — empty, labeled
  repro_agent/         # ReproAgent — empty, labeled ("all browser work lives here")
  hypothesis_agent/    # HypothesisAgent — empty, labeled
  shared/band.py       # Band module STUB (connect() raises NotImplementedError)
frontend/README.md     # placeholder
docs/                  # TRIAGE_OVERVIEW.md, TRIAGE_INTEGRATIONS.md, the plan, this file
tests/test_config.py   # 6 tests, all passing
pyproject.toml  .env.example  .gitignore  README.md
```

## What works

- `.venv/bin/pip install -e ".[dev]"` — installs cleanly, including all the
  later-phase SDKs (band-sdk, stagehand, arize-phoenix, anthropic) on Python 3.14.
- `.venv/bin/pytest` — 6/6 passing.
- Config loader: `from triage.config import load_config`. Returns a frozen
  `Config` (with three `BandIdentity` objects) or raises `MissingConfigError`
  listing every missing var. Empty strings count as missing.
- `.env.example` lists all 13 vars (3 namespaced Band identities, Browserbase,
  Phoenix, Anthropic, app URL + issue URL). Real `.env` is gitignored and ready
  to fill in.

## Commits (on `main`)

- `7866f05` — package skeleton, packaging, gitignore, README, docs moved
- `ec9ff4e` — `.env.example` + gitignored `.env`
- `d697d3c` — config loader + tests (TDD)

## Decisions made

- **All-Python**, one runtime.
- **Python 3.14** confirmed working — the wheel-availability risk is moot.
- Per-task commits; secrets and tooling dirs gitignored.

## What's next — Phase 2 (shared Band module)

Implement `triage/shared/band.py` against `band-sdk`. Per the integration doc:
**prove the three-way handshake first** (all three agents join a room, post, and
receive via @mention) before building any real agent logic.

Needed from the user: Band SDK + Stagehand Python doc links, and real Band
credentials in `.env`.

## Full roadmap (from docs/TRIAGE_OVERVIEW.md)

1. Buggy target app · 2. Issue parsing · 3. Browserbase+Stagehand executor ·
4. Capture layer · 5. Band coordination · 6. Arize tracing ·
7. Claude synthesis · 8. Minimal frontend.
