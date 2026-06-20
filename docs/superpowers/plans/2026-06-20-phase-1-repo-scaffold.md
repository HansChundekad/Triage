# TRIAGE Phase 1 — Repo Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay a clean, all-Python repo foundation for TRIAGE whose folder layout makes the three-agent architecture obvious, with dependency management, a complete env template, and a fail-loud config loader — and nothing else.

**Architecture:** A single importable package `triage/` holds one subpackage per agent (`parser_agent`, `repro_agent`, `hypothesis_agent`), a `shared/` subpackage with a stubbed Band module for Phase 2, and a real `config.py`. Sibling top-level `frontend/`, `docs/`, and `tests/` directories round it out. The only working code in this phase is the config loader (built test-first); everything else is labeled, empty scaffolding.

**Tech Stack:** Python 3.11+ (running on 3.14 locally), `pyproject.toml` with the `hatchling` build backend, `python-dotenv` for env loading, `pytest` for tests. Integration SDKs are *listed* but neither installed nor imported in this phase.

## Global Constraints

- **Language:** All-Python. One runtime (assumption flagged to user; confirmed before execution).
- **Scope:** Phase 1 is scaffold only. NO agent logic, NO integration code, NO Browserbase/Band/Arize/Claude API calls. The config loader is the only behavior.
- **Do not import integration SDKs** anywhere in this phase. List them in `pyproject.toml` only.
- **Install in Phase 1 only:** `python-dotenv`, `pytest`. All other dependencies install in the phase that first uses them.
- **Agent naming is exact:** folders and docs use `ParserAgent` / `ReproAgent` / `HypothesisAgent`. Never generic ("Agent", "Bot", "Assistant").
- **Browser concentration:** all future browser work lives in `repro_agent/` only. The scaffold must make this obvious; no browser-related placeholder appears in any other agent folder.
- **Three distinct Band identities:** env vars namespaced `BAND_PARSER_*`, `BAND_REPRO_*`, `BAND_HYPOTHESIS_*`; config models them as three separate identity objects.
- **Secrets never committed:** real `.env` is gitignored; only `.env.example` is tracked.
- **Clean first commit:** Claude Code tooling dirs (`.claude/`, `.agents/`, `.impeccable/`, `skills-lock.json`) are gitignored so the initial commit is purely the TRIAGE project.

---

## File Structure

```
/Users/hanschundekad/Triage/
├── pyproject.toml              # deps list (mostly uninstalled) + build + pytest config
├── .gitignore                 # secrets, python junk, tooling dirs
├── .env.example               # complete template of every required var (tracked)
├── .env                       # real secrets (gitignored, empty placeholder)
├── README.md                  # short project + phase stub
├── docs/
│   ├── TRIAGE_OVERVIEW.md      # moved from repo root (source of truth)
│   ├── TRIAGE_INTEGRATIONS.md  # moved from repo root (connectivity reference)
│   └── superpowers/plans/2026-06-20-phase-1-repo-scaffold.md  # this plan
├── triage/
│   ├── __init__.py
│   ├── config.py              # THE real code: fail-loud env loader
│   ├── parser_agent/
│   │   ├── __init__.py        # ParserAgent — empty
│   │   └── README.md          # one-line responsibility
│   ├── repro_agent/
│   │   ├── __init__.py        # ReproAgent — empty
│   │   └── README.md          # responsibility + "ALL browser work lives here"
│   ├── hypothesis_agent/
│   │   ├── __init__.py        # HypothesisAgent — empty
│   │   └── README.md          # one-line responsibility
│   └── shared/
│       ├── __init__.py
│       └── band.py            # Phase 2 stub — NotImplementedError, no SDK import
├── frontend/
│   └── README.md              # placeholder for Phase 8 frontend
└── tests/
    ├── __init__.py
    └── test_config.py         # config loader tests
```

**Responsibilities:**
- `triage/config.py` — the only module with logic. Reads env, validates required vars, fails loud listing every missing one, returns a frozen `Config`.
- `triage/shared/band.py` — placeholder marker for the Phase 2 Band module. Contains a docstring and a function that raises `NotImplementedError`. Imports no SDK.
- Each agent `__init__.py` — empty package marker with a module docstring naming the agent exactly.
- Each agent `README.md` — one or two lines stating that agent's role, copied from the architecture.

---

## Task 1: Project skeleton, packaging, and gitignore

**Files:**
- Create: `/Users/hanschundekad/Triage/pyproject.toml`
- Create: `/Users/hanschundekad/Triage/.gitignore`
- Create: `/Users/hanschundekad/Triage/README.md`
- Create: `/Users/hanschundekad/Triage/triage/__init__.py`
- Create: `/Users/hanschundekad/Triage/triage/parser_agent/__init__.py`
- Create: `/Users/hanschundekad/Triage/triage/parser_agent/README.md`
- Create: `/Users/hanschundekad/Triage/triage/repro_agent/__init__.py`
- Create: `/Users/hanschundekad/Triage/triage/repro_agent/README.md`
- Create: `/Users/hanschundekad/Triage/triage/hypothesis_agent/__init__.py`
- Create: `/Users/hanschundekad/Triage/triage/hypothesis_agent/README.md`
- Create: `/Users/hanschundekad/Triage/triage/shared/__init__.py`
- Create: `/Users/hanschundekad/Triage/triage/shared/band.py`
- Create: `/Users/hanschundekad/Triage/frontend/README.md`
- Create: `/Users/hanschundekad/Triage/tests/__init__.py`
- Move: `TRIAGE_OVERVIEW.md` → `docs/TRIAGE_OVERVIEW.md`
- Move: `TRIAGE_INTEGRATIONS.md` → `docs/TRIAGE_INTEGRATIONS.md`

**Interfaces:**
- Produces: an installable package `triage` (so `from triage.config import load_config` resolves after `pip install -e .`). The subpackages `triage.parser_agent`, `triage.repro_agent`, `triage.hypothesis_agent`, `triage.shared` exist as import targets. No public functions yet except the Phase 2 stub `triage.shared.band.connect()` which raises `NotImplementedError`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "triage"
version = "0.1.0"
description = "Autonomous bug-reproduction agent — UC Berkeley AI Hackathon 2026"
requires-python = ">=3.11"
dependencies = [
    # --- Installed in Phase 1 (config loader + tests need these) ---
    "python-dotenv>=1.0",
    # --- Listed for later phases; NOT imported yet. Versions verified
    #     against live docs in the phase that first uses each. ---
    "anthropic",                                  # Claude reasoning (all agents)
    "httpx",                                      # GitHub issue fetch (ParserAgent)
    "band-sdk",                                   # Band coordination (Phase: Band)
    "stagehand",                                  # Browserbase driver (ReproAgent)
    "arize-phoenix",                              # tracing (Phase: Arize)
    "openinference-instrumentation-anthropic",    # auto-instrument Claude calls
    "opentelemetry-sdk",                          # manual retry spans
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.hatch.build.targets.wheel]
packages = ["triage"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
# Secrets
.env
.env.local

# Python
__pycache__/
*.py[cod]
*.egg-info/
.eggs/
build/
dist/
.venv/
venv/
.pytest_cache/

# OS / editor
.DS_Store
*.swp

# Claude Code tooling (keep first commit clean)
.claude/
.agents/
.impeccable/
skills-lock.json
```

- [ ] **Step 3: Create `README.md`**

```markdown
# TRIAGE

Autonomous bug-reproduction agent. A developer pastes a GitHub issue; TRIAGE
opens a real cloud browser, clicks through a live app to trigger the bug,
captures the crash, diagnoses the root cause, and writes a structured report.

Built for the UC Berkeley AI Hackathon 2026.

## Architecture (three agents, one Band room)

- **ParserAgent** (`triage/parser_agent/`) — GitHub issue → structured repro steps.
- **ReproAgent** (`triage/repro_agent/`) — drives a real Browserbase browser. **All** browser work lives here.
- **HypothesisAgent** (`triage/hypothesis_agent/`) — diagnoses root cause, can redirect ReproAgent to retry.

Integrations: Browserbase (cloud browser), Band (multi-agent coordination),
Arize Phoenix (retry-loop tracing), Claude (reasoning).

See `docs/TRIAGE_OVERVIEW.md` (source of truth) and `docs/TRIAGE_INTEGRATIONS.md`.

## Status

Phase 1 — repo scaffold. No agent logic or integration code yet.

## Setup

```bash
pip install -e ".[dev]"   # installs python-dotenv + pytest only in Phase 1
cp .env.example .env      # then fill in your keys
pytest                    # runs the config-loader tests
```
```

- [ ] **Step 4: Create the package and agent markers**

`triage/__init__.py`:
```python
"""TRIAGE — autonomous bug-reproduction agent."""
```

`triage/parser_agent/__init__.py`:
```python
"""ParserAgent — turns a GitHub issue into structured repro steps.

Phase 1 scaffold: no logic yet.
"""
```

`triage/repro_agent/__init__.py`:
```python
"""ReproAgent — drives a real Browserbase cloud browser to reproduce the bug.

ALL browser work in TRIAGE lives in this package and nowhere else.
Phase 1 scaffold: no logic yet.
"""
```

`triage/hypothesis_agent/__init__.py`:
```python
"""HypothesisAgent — diagnoses root cause and can redirect ReproAgent to retry.

Phase 1 scaffold: no logic yet.
"""
```

`triage/shared/__init__.py`:
```python
"""Shared modules used by all three agents (e.g. the Band coordination layer)."""
```

- [ ] **Step 5: Create the Band stub** (`triage/shared/band.py`)

```python
"""Band coordination layer — SHARED across ParserAgent, ReproAgent, HypothesisAgent.

Phase 2 will implement this against the Band SDK (`band-sdk`). It is the message
bus where the three agents coordinate via @mentions. Intentionally a stub now —
do NOT import the Band SDK here until Phase 2.
"""


def connect(*args, **kwargs):
    """Placeholder for the Phase 2 Band connection. Not implemented yet."""
    raise NotImplementedError("Band module is implemented in Phase 2.")
```

- [ ] **Step 6: Create agent README stubs**

`triage/parser_agent/README.md`:
```markdown
# ParserAgent

Fetches a GitHub issue, uses Claude to turn vague prose into structured repro
steps (including unstated preconditions), and posts them into the Band room
@mentioning the ReproAgent. A failed repro can route back here for re-parsing.

Phase 1: scaffold only.
```

`triage/repro_agent/README.md`:
```markdown
# ReproAgent

The hero. Spins up a real Browserbase cloud browser and executes each repro step
as a natural-language Stagehand action, screenshotting every step and capturing
console errors, then reports evidence into the Band room @mentioning the
HypothesisAgent. Creates a fresh browser session per retry.

**ALL browser work in TRIAGE lives here — never spread Stagehand calls to other agents.**

Phase 1: scaffold only.
```

`triage/hypothesis_agent/README.md`:
```markdown
# HypothesisAgent

Reads the evidence ReproAgent reports, diagnoses the root cause, and @mentions
back a diagnosis. Can redirect ("@ReproAgent retry with a slower delete") — the
redirect that turns a straight line into a real coordination loop.

Phase 1: scaffold only.
```

- [ ] **Step 7: Create placeholders for frontend and tests**

`frontend/README.md`:
```markdown
# Frontend (placeholder)

Phase 8: a minimal web page to paste a GitHub issue URL, watch a live log, and
read the final report card. Not built yet.
```

`tests/__init__.py`:
```python
```
(empty file)

- [ ] **Step 8: Move the reference docs into `docs/`**

```bash
cd /Users/hanschundekad/Triage
mkdir -p docs
git mv TRIAGE_OVERVIEW.md docs/TRIAGE_OVERVIEW.md 2>/dev/null || mv TRIAGE_OVERVIEW.md docs/TRIAGE_OVERVIEW.md
git mv TRIAGE_INTEGRATIONS.md docs/TRIAGE_INTEGRATIONS.md 2>/dev/null || mv TRIAGE_INTEGRATIONS.md docs/TRIAGE_INTEGRATIONS.md
```
(Files are untracked pre-first-commit, so the `mv` fallback runs.)

- [ ] **Step 9: Install Phase 1 deps and verify the package imports**

Run:
```bash
cd /Users/hanschundekad/Triage
pip install -e ".[dev]"
python -c "import triage, triage.parser_agent, triage.repro_agent, triage.hypothesis_agent, triage.shared; print('packages import OK')"
```
Expected: ends with `packages import OK` and no traceback.

> If `pip install -e .` fails because a *later-phase* SDK has no Python 3.14 wheel, that's expected risk noted in Global Constraints. Mitigation: temporarily comment out the not-yet-needed deps in `pyproject.toml` (keep only `python-dotenv` + the `dev` extra), re-run, and leave a note to restore them in the phase that installs each. Do not import any of them regardless.

---

## Task 2: Environment template and gitignored `.env`

**Files:**
- Create: `/Users/hanschundekad/Triage/.env.example`
- Create: `/Users/hanschundekad/Triage/.env`

**Interfaces:**
- Produces: the canonical list of env var names the config loader in Task 3 will read. The names defined here MUST match exactly what `triage/config.py` reads: `ANTHROPIC_API_KEY`, `BROWSERBASE_API_KEY`, `BROWSERBASE_PROJECT_ID`, `BAND_PARSER_API_KEY`, `BAND_PARSER_AGENT_ID`, `BAND_REPRO_API_KEY`, `BAND_REPRO_AGENT_ID`, `BAND_HYPOTHESIS_API_KEY`, `BAND_HYPOTHESIS_AGENT_ID`, `PHOENIX_API_KEY`, `PHOENIX_COLLECTOR_ENDPOINT` (optional, defaulted), `TRIAGE_APP_URL`, `TRIAGE_GITHUB_ISSUE_URL`.

- [ ] **Step 1: Create `.env.example`**

```dotenv
# ============================================================
# TRIAGE environment — copy to .env and fill in real values.
# .env is gitignored; .env.example is committed.
# ============================================================

# --- Claude (Anthropic) — reasoning brain across all agents ---
ANTHROPIC_API_KEY=

# --- Browserbase — real cloud browser (ReproAgent only) ---
BROWSERBASE_API_KEY=
BROWSERBASE_PROJECT_ID=

# --- Band — THREE distinct agent identities. Keep them separate so one
#     agent can never authenticate as another. ---
BAND_PARSER_API_KEY=
BAND_PARSER_AGENT_ID=
BAND_REPRO_API_KEY=
BAND_REPRO_AGENT_ID=
BAND_HYPOTHESIS_API_KEY=
BAND_HYPOTHESIS_AGENT_ID=

# --- Arize Phoenix — retry-loop tracing ---
PHOENIX_API_KEY=
# Optional. Defaults to https://app.phoenix.arize.com if left unset.
PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com

# --- Target under test ---
TRIAGE_APP_URL=
TRIAGE_GITHUB_ISSUE_URL=
```

- [ ] **Step 2: Create empty `.env` for real secrets**

Copy the template so the user has a file to fill in (it is gitignored):
```bash
cd /Users/hanschundekad/Triage
cp .env.example .env
```

- [ ] **Step 3: Verify `.env` is ignored by git**

Run:
```bash
cd /Users/hanschundekad/Triage
git check-ignore .env && echo "IGNORED OK"
```
Expected: prints `.env` then `IGNORED OK`.

---

## Task 3: Fail-loud config loader (TDD)

**Files:**
- Create: `/Users/hanschundekad/Triage/triage/config.py`
- Test: `/Users/hanschundekad/Triage/tests/test_config.py`

**Interfaces:**
- Consumes: env var names defined in Task 2.
- Produces:
  - `class MissingConfigError(RuntimeError)` — raised when required vars are absent.
  - `@dataclass(frozen=True) class BandIdentity` with fields `api_key: str`, `agent_id: str`.
  - `@dataclass(frozen=True) class Config` with fields: `anthropic_api_key: str`, `browserbase_api_key: str`, `browserbase_project_id: str`, `band_parser: BandIdentity`, `band_repro: BandIdentity`, `band_hypothesis: BandIdentity`, `phoenix_api_key: str`, `phoenix_collector_endpoint: str`, `app_url: str`, `github_issue_url: str`.
  - `def load_config(load_env: bool = True) -> Config` — when `load_env` is True, calls `dotenv.load_dotenv()` first; reads from `os.environ`; collects ALL missing required vars and raises `MissingConfigError` naming every one; applies the `PHOENIX_COLLECTOR_ENDPOINT` default.

- [ ] **Step 1: Write the failing tests** (`tests/test_config.py`)

```python
import pytest

from triage.config import BandIdentity, Config, MissingConfigError, load_config

REQUIRED = [
    "ANTHROPIC_API_KEY",
    "BROWSERBASE_API_KEY",
    "BROWSERBASE_PROJECT_ID",
    "BAND_PARSER_API_KEY",
    "BAND_PARSER_AGENT_ID",
    "BAND_REPRO_API_KEY",
    "BAND_REPRO_AGENT_ID",
    "BAND_HYPOTHESIS_API_KEY",
    "BAND_HYPOTHESIS_AGENT_ID",
    "PHOENIX_API_KEY",
    "TRIAGE_APP_URL",
    "TRIAGE_GITHUB_ISSUE_URL",
]


def _set_all(monkeypatch):
    for name in REQUIRED:
        monkeypatch.setenv(name, f"value-for-{name}")


def test_missing_all_required_lists_every_var(monkeypatch):
    for name in REQUIRED + ["PHOENIX_COLLECTOR_ENDPOINT"]:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(MissingConfigError) as exc:
        load_config(load_env=False)
    message = str(exc.value)
    for name in REQUIRED:
        assert name in message


def test_missing_single_var_names_it(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("BROWSERBASE_PROJECT_ID", raising=False)
    with pytest.raises(MissingConfigError) as exc:
        load_config(load_env=False)
    assert "BROWSERBASE_PROJECT_ID" in str(exc.value)


def test_all_present_returns_config(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
    cfg = load_config(load_env=False)
    assert isinstance(cfg, Config)
    assert cfg.anthropic_api_key == "value-for-ANTHROPIC_API_KEY"
    assert isinstance(cfg.band_repro, BandIdentity)
    assert cfg.band_repro.api_key == "value-for-BAND_REPRO_API_KEY"
    assert cfg.band_repro.agent_id == "value-for-BAND_REPRO_AGENT_ID"


def test_phoenix_endpoint_defaults_when_unset(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
    cfg = load_config(load_env=False)
    assert cfg.phoenix_collector_endpoint == "https://app.phoenix.arize.com"


def test_phoenix_endpoint_override(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
    cfg = load_config(load_env=False)
    assert cfg.phoenix_collector_endpoint == "http://localhost:6006"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /Users/hanschundekad/Triage
pytest tests/test_config.py -v
```
Expected: collection/import error — `ModuleNotFoundError: No module named 'triage.config'` (config.py not created yet).

- [ ] **Step 3: Write the config loader** (`triage/config.py`)

```python
"""Fail-loud configuration loader for TRIAGE.

Reads all required settings from the environment and raises a single, clear
error listing every missing variable — so a misconfiguration fails immediately
with a readable message instead of deep inside an agent at runtime.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

_PHOENIX_ENDPOINT_DEFAULT = "https://app.phoenix.arize.com"


class MissingConfigError(RuntimeError):
    """Raised when one or more required environment variables are absent."""


@dataclass(frozen=True)
class BandIdentity:
    """One of the three distinct Band agent identities."""

    api_key: str
    agent_id: str


@dataclass(frozen=True)
class Config:
    """Fully-resolved TRIAGE configuration."""

    anthropic_api_key: str
    browserbase_api_key: str
    browserbase_project_id: str
    band_parser: BandIdentity
    band_repro: BandIdentity
    band_hypothesis: BandIdentity
    phoenix_api_key: str
    phoenix_collector_endpoint: str
    app_url: str
    github_issue_url: str


_REQUIRED = (
    "ANTHROPIC_API_KEY",
    "BROWSERBASE_API_KEY",
    "BROWSERBASE_PROJECT_ID",
    "BAND_PARSER_API_KEY",
    "BAND_PARSER_AGENT_ID",
    "BAND_REPRO_API_KEY",
    "BAND_REPRO_AGENT_ID",
    "BAND_HYPOTHESIS_API_KEY",
    "BAND_HYPOTHESIS_AGENT_ID",
    "PHOENIX_API_KEY",
    "TRIAGE_APP_URL",
    "TRIAGE_GITHUB_ISSUE_URL",
)


def load_config(load_env: bool = True) -> Config:
    """Load and validate TRIAGE configuration from the environment.

    Args:
        load_env: when True, load a local ``.env`` file before reading
            ``os.environ``. Tests pass False to read only the patched env.

    Raises:
        MissingConfigError: if any required variable is unset or empty,
            naming every missing variable at once.
    """
    if load_env:
        load_dotenv()

    missing = [name for name in _REQUIRED if not os.environ.get(name)]
    if missing:
        raise MissingConfigError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill these in."
        )

    env = os.environ
    return Config(
        anthropic_api_key=env["ANTHROPIC_API_KEY"],
        browserbase_api_key=env["BROWSERBASE_API_KEY"],
        browserbase_project_id=env["BROWSERBASE_PROJECT_ID"],
        band_parser=BandIdentity(
            api_key=env["BAND_PARSER_API_KEY"],
            agent_id=env["BAND_PARSER_AGENT_ID"],
        ),
        band_repro=BandIdentity(
            api_key=env["BAND_REPRO_API_KEY"],
            agent_id=env["BAND_REPRO_AGENT_ID"],
        ),
        band_hypothesis=BandIdentity(
            api_key=env["BAND_HYPOTHESIS_API_KEY"],
            agent_id=env["BAND_HYPOTHESIS_AGENT_ID"],
        ),
        phoenix_api_key=env["PHOENIX_API_KEY"],
        phoenix_collector_endpoint=env.get(
            "PHOENIX_COLLECTOR_ENDPOINT", _PHOENIX_ENDPOINT_DEFAULT
        ),
        app_url=env["TRIAGE_APP_URL"],
        github_issue_url=env["TRIAGE_GITHUB_ISSUE_URL"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /Users/hanschundekad/Triage
pytest tests/test_config.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Verify the loader fails loud against a real empty `.env`**

Run (the committed `.env` from Task 2 is all-empty, so this should fail clearly):
```bash
cd /Users/hanschundekad/Triage
python -c "from triage.config import load_config; load_config()" ; echo "exit=$?"
```
Expected: a `MissingConfigError` traceback listing the empty vars, and a non-zero exit code.

---

## Task 4: Clean first commit

**Files:** none created; this commits everything from Tasks 1–3.

**Interfaces:** none.

- [ ] **Step 1: Confirm tooling dirs and secrets are excluded**

Run:
```bash
cd /Users/hanschundekad/Triage
git add -A
git status --short
```
Expected: staged TRIAGE files only. `.env`, `.claude/`, `.agents/`, `.impeccable/`, `skills-lock.json` must NOT appear. If any do, stop and fix `.gitignore`.

- [ ] **Step 2: Make the initial commit**

```bash
cd /Users/hanschundekad/Triage
git commit -m "$(cat <<'EOF'
chore: scaffold TRIAGE repo (Phase 1)

All-Python foundation: one package per agent (ParserAgent/ReproAgent/
HypothesisAgent), shared Band stub for Phase 2, frontend + docs placeholders,
pyproject dependency manifest, complete .env.example, and a fail-loud config
loader with tests. No agent logic or integration code yet.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Verify the commit is clean**

Run:
```bash
cd /Users/hanschundekad/Triage
git log --oneline -1 && git ls-files | sort
```
Expected: one commit; tracked files list contains the TRIAGE scaffold and `.env.example` but NOT `.env` or any tooling dir.

---

## Self-Review

**Spec coverage:**
- Folder per agent → Task 1 (`parser_agent`, `repro_agent`, `hypothesis_agent`). ✓
- Shared module folder, Band stubbed not implemented → Task 1 Step 5 (`shared/band.py` raises `NotImplementedError`, no SDK import). ✓
- Frontend placeholder → Task 1 Step 7. ✓
- Place for integration docs → Task 1 Step 8 (`docs/`). ✓
- Dependency management with named packages, not imported → Task 1 Step 1 (`pyproject.toml`). ✓
- Complete `.env.example` with namespaced Band identities + all listed vars → Task 2 Step 1. ✓
- Real gitignored `.env` → Task 2 Step 2 + `.gitignore` Task 1 Step 2. ✓
- Config loader fails loud on missing → Task 3. ✓
- `.gitignore`, README stub, git clean first commit → Task 1 + Task 4. ✓
- All browser work obvious in ReproAgent only → repro_agent docstring + README; no browser placeholder elsewhere. ✓
- Exact agent names → used throughout. ✓
- Three distinct Band identities → `BandIdentity` ×3 + namespaced env. ✓
- All-Python assumption flagged → Global Constraints. ✓

**Placeholder scan:** No "TBD"/"add error handling"/"write tests for the above" — all code is concrete. ✓

**Type consistency:** `load_config(load_env: bool)`, `Config`, `BandIdentity(api_key, agent_id)`, `MissingConfigError` names match between the test (Task 3 Step 1), the implementation (Step 3), and the Interfaces blocks. Env var names match between `.env.example` (Task 2) and `_REQUIRED` (Task 3). ✓
