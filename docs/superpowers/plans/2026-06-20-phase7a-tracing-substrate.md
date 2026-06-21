# Phase 7A — Tracing Substrate + Span Instrumentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the real Phase-6 retry loop in Arize Phoenix spans so the fail→adjust→succeed progression reads as one legible trace tree, with honest `bug.detected` per attempt and a per-run artifact store that feeds the evaluator (7B) and synthesis (7C).

**Architecture:** A new `triage/tracing/` package provides `setup_tracing()` (Phoenix `register`), a `RunTrace` that holds the root span context and hands out explicitly-parented child spans (the only way to nest spans created in separate async Band callbacks), and a `RunArtifacts` per-run directory. Agent callbacks gain **optional** `run_trace`/`artifacts` params that default to no-op objects, so existing tests and `phase6_live_run.py` are untouched. A new `scripts/phase7_traced_run.py` composes the three real callbacks under one root span.

**Tech Stack:** Python 3.11+ (dev 3.14), `arize-phoenix`, `openinference-instrumentation-anthropic`, `opentelemetry-sdk`, `pytest`, OpenTelemetry `InMemorySpanExporter` for tests.

## Global Constraints

- Use the repo venv `.venv/` for all commands. This fresh worktree has none — Task 0 creates it.
- Install/test: `.venv/bin/pip install -e ".[dev]"` · `.venv/bin/pytest`.
- Target Python 3.11+ (dev on 3.14); all-Python.
- TDD for real logic — failing test first. Per-task commits, scoped messages.
- **Never** modify `triage/shared/band.py` (hash-pinned) or `ReproResultPayload`.
- **Never** modify agent *decision logic* — only add instrumentation (spans/attributes/artifact writes) and **optional, default-None** parameters.
- `bug.detected` must be honest — set only from `detect_bug`/`result.success`; never hard-coded.
- Agent names exact: `ParserAgent` / `ReproAgent` / `HypothesisAgent`.
- The 84 existing tests must stay green after every task.
- Phoenix project name: `triage-bug-repro`. Tracer name: `triage`.
- Verify any SDK detail against the installed package before relying on it; flag drift in the commit body.

---

### Task 0: Environment + dependency floor

**Files:**
- Modify: `pyproject.toml:10-23` (pin Phoenix dep versions once installed)
- Create: `.venv/` (not committed)

- [ ] **Step 1: Create the venv and install the project**

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

- [ ] **Step 2: Run the existing suite to confirm the baseline**

Run: `.venv/bin/pytest -q`
Expected: PASS (the Phase-6 baseline — count matches STATUS.md's "84 tests pass").

- [ ] **Step 3: Confirm the Phoenix/OTEL imports resolve and pin versions**

```bash
.venv/bin/python -c "import phoenix; from phoenix.otel import register; import opentelemetry.sdk; import openinference.instrumentation.anthropic; print(phoenix.__version__)"
.venv/bin/pip show arize-phoenix opentelemetry-sdk openinference-instrumentation-anthropic | grep -E "^(Name|Version)"
```

Expected: prints a version, no ImportError. Copy the resolved versions into `pyproject.toml` (e.g. `arize-phoenix>=11`), replacing the bare names on lines 20-22. **If any import fails, flag it and stop** — do not invent a module path.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(phase7a): pin Phoenix/OTEL dep versions, set up worktree venv"
```

---

### Task 1: `setup_tracing()` — Phoenix tracer registration

**Files:**
- Create: `triage/tracing/__init__.py`
- Create: `triage/tracing/setup.py`
- Test: `tests/test_tracing_setup.py`

**Interfaces:**
- Consumes: `triage.config.Config` (`phoenix_api_key`, `phoenix_collector_endpoint`).
- Produces: `setup_tracing(cfg, *, _register=None) -> opentelemetry.trace.Tracer`. Sets
  `PHOENIX_API_KEY` / `PHOENIX_COLLECTOR_ENDPOINT` in `os.environ` from `cfg`, calls
  `phoenix.otel.register(project_name="triage-bug-repro", auto_instrument=True)` exactly once
  (idempotent via a module flag), returns `trace.get_tracer("triage")`. `_register` is an
  injection seam for tests (defaults to the real `phoenix.otel.register`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tracing_setup.py
import os
from triage.tracing.setup import setup_tracing


class _Cfg:
    phoenix_api_key = "pk-test"
    phoenix_collector_endpoint = "https://app.phoenix.arize.com"


def test_setup_tracing_registers_once_and_sets_env():
    calls = []

    def fake_register(**kwargs):
        calls.append(kwargs)
        return object()

    tracer = setup_tracing(_Cfg(), _register=fake_register)
    # called once with the project name + auto_instrument
    assert calls == [{"project_name": "triage-bug-repro", "auto_instrument": True}]
    assert os.environ["PHOENIX_API_KEY"] == "pk-test"
    assert os.environ["PHOENIX_COLLECTOR_ENDPOINT"] == "https://app.phoenix.arize.com"
    # idempotent: second call does NOT register again
    setup_tracing(_Cfg(), _register=fake_register)
    assert len(calls) == 1
    # returns something usable as a tracer (has start_as_current_span)
    assert hasattr(tracer, "start_as_current_span")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_tracing_setup.py -v`
Expected: FAIL — `ModuleNotFoundError: triage.tracing.setup`.

- [ ] **Step 3: Write minimal implementation**

```python
# triage/tracing/__init__.py
"""Arize Phoenix tracing substrate (Phase 7A). Optional + no-op by default."""
```

```python
# triage/tracing/setup.py
"""Phoenix tracer registration — idempotent, env-driven, injectable for tests."""
from __future__ import annotations

import os

from opentelemetry import trace

_PROJECT_NAME = "triage-bug-repro"
_registered = False


def setup_tracing(cfg, *, _register=None):
    """Register the Phoenix tracer once and return a tracer named 'triage'.

    Sets PHOENIX_API_KEY / PHOENIX_COLLECTOR_ENDPOINT from cfg before registering.
    `_register` is injected in tests; defaults to phoenix.otel.register.
    """
    global _registered
    os.environ["PHOENIX_API_KEY"] = cfg.phoenix_api_key
    os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = cfg.phoenix_collector_endpoint

    if not _registered:
        register = _register
        if register is None:
            from phoenix.otel import register as register  # noqa: PLC0414
        register(project_name=_PROJECT_NAME, auto_instrument=True)
        _registered = True

    return trace.get_tracer("triage")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_tracing_setup.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add triage/tracing/__init__.py triage/tracing/setup.py tests/test_tracing_setup.py
git commit -m "feat(phase7a): setup_tracing() — idempotent Phoenix register"
```

---

### Task 2: `RunTrace` + `NullRunTrace` — explicit-parent span tree

**Files:**
- Create: `triage/tracing/run_context.py`
- Test: `tests/test_run_trace.py`

**Interfaces:**
- Consumes: a tracer from Task 1; `opentelemetry.trace` / `opentelemetry.context`.
- Produces:
  - `RunTrace(tracer, *, issue_url="", app_url="")` — context manager. On enter, starts the
    root `triage_run` span and stores its `Context`. Exposes:
    - `attempt_span(number: int) -> ContextManager[Span]` — `repro_attempt` child of root,
      pre-set `attempt.number`.
    - `child_span(name: str, parent: Span) -> ContextManager[Span]` — child of an explicit
      parent span (used for `browser_execution`, `bug_detection`, `stagehand_action`).
    - `claude_span(name: str, *, attempt_number: int | None = None) -> ContextManager[Span]` —
      child of root, tagged with `attempt.number` when given (for Parser/Hypothesis calls).
  - `NullRunTrace()` — same interface, every context manager yields `None` and does nothing.
  - Module helper `set_span_ok(span, ok: bool)` used everywhere to set OTEL status honestly.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_trace.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from triage.tracing.run_context import RunTrace, NullRunTrace


def _tracer_and_exporter():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("triage-test"), exporter


def test_run_trace_builds_nested_tree():
    tracer, exporter = _tracer_and_exporter()
    with RunTrace(tracer, issue_url="http://issue", app_url="http://app") as run:
        with run.attempt_span(1) as attempt:
            with run.child_span("browser_execution", attempt) as be:
                with run.child_span("stagehand_action", be) as step:
                    step.set_attribute("step.index", 1)
        with run.claude_span("hypothesis_generation", attempt_number=1):
            pass

    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert {"triage_run", "repro_attempt", "browser_execution",
            "stagehand_action", "hypothesis_generation"} <= set(spans)
    root = spans["triage_run"]
    # repro_attempt's parent is the root span
    assert spans["repro_attempt"].parent.span_id == root.context.span_id
    # stagehand_action nests under browser_execution
    assert spans["stagehand_action"].parent.span_id == spans["browser_execution"].context.span_id
    # claude span parented under root, tagged with the attempt number
    assert spans["hypothesis_generation"].parent.span_id == root.context.span_id
    assert spans["hypothesis_generation"].attributes["attempt.number"] == 1
    assert spans["repro_attempt"].attributes["attempt.number"] == 1
    assert root.attributes["github.issue_url"] == "http://issue"


def test_null_run_trace_is_safe_noop():
    run = NullRunTrace()
    with run as r:
        with r.attempt_span(1) as a:
            with r.child_span("x", a) as c:
                assert c is None
        with r.claude_span("y", attempt_number=2) as c:
            assert c is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_run_trace.py -v`
Expected: FAIL — `ModuleNotFoundError: triage.tracing.run_context`.

- [ ] **Step 3: Write minimal implementation**

```python
# triage/tracing/run_context.py
"""RunTrace — a run-level root span that hands out explicitly-parented children.

Spans created inside separate async Band callbacks cannot rely on OTEL's implicit
current-span context to nest. RunTrace stores the root span's Context and parents
every child explicitly, producing one legible tree across callbacks.
"""
from __future__ import annotations

from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


def set_span_ok(span, ok: bool) -> None:
    """Set OTEL status honestly from a boolean outcome (no-op if span is None)."""
    if span is None:
        return
    span.set_status(Status(StatusCode.OK if ok else StatusCode.ERROR))


class RunTrace:
    """Holds the root `triage_run` span and parents children under it explicitly."""

    def __init__(self, tracer, *, issue_url: str = "", app_url: str = ""):
        self._tracer = tracer
        self._issue_url = issue_url
        self._app_url = app_url
        self._root = None
        self._root_ctx = None

    def __enter__(self) -> "RunTrace":
        self._root = self._tracer.start_span("triage_run")
        if self._issue_url:
            self._root.set_attribute("github.issue_url", self._issue_url)
        if self._app_url:
            self._root.set_attribute("app.url", self._app_url)
        self._root_ctx = trace.set_span_in_context(self._root)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc is not None:
            self._root.record_exception(exc)
            set_span_ok(self._root, False)
        self._root.end()

    @contextmanager
    def attempt_span(self, number: int):
        span = self._tracer.start_span("repro_attempt", context=self._root_ctx)
        span.set_attribute("attempt.number", number)
        try:
            yield span
        finally:
            span.end()

    @contextmanager
    def child_span(self, name: str, parent):
        ctx = trace.set_span_in_context(parent)
        span = self._tracer.start_span(name, context=ctx)
        try:
            yield span
        finally:
            span.end()

    @contextmanager
    def claude_span(self, name: str, *, attempt_number: int | None = None):
        span = self._tracer.start_span(name, context=self._root_ctx)
        if attempt_number is not None:
            span.set_attribute("attempt.number", attempt_number)
        try:
            yield span
        finally:
            span.end()


class NullRunTrace:
    """No-op RunTrace for the untraced/test path. Same interface."""

    def __enter__(self) -> "NullRunTrace":
        return self

    def __exit__(self, *a) -> None:
        return None

    @contextmanager
    def attempt_span(self, number: int):
        yield None

    @contextmanager
    def child_span(self, name: str, parent):
        yield None

    @contextmanager
    def claude_span(self, name: str, *, attempt_number: int | None = None):
        yield None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_run_trace.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add triage/tracing/run_context.py tests/test_run_trace.py
git commit -m "feat(phase7a): RunTrace explicit-parent span tree + NullRunTrace"
```

---

### Task 3: `RunArtifacts` + `NullRunArtifacts` — per-run store

**Files:**
- Create: `triage/tracing/artifacts.py`
- Test: `tests/test_run_artifacts.py`

**Interfaces:**
- Consumes: nothing (stdlib only — `pathlib`, `json`, `base64`, `datetime`).
- Produces:
  - `RunArtifacts(root_dir: str | os.PathLike)` — creates `root_dir/<timestamp>/` with a
    `screenshots/` subdir. Methods:
    - `save_screenshot(attempt: int, step: int, png_b64: str) -> str` — decodes base64, writes
      `screenshots/attempt{attempt}_step{step}.png`, returns the **relative** path (the span's
      `screenshot.ref`).
    - `record_attempt(record: dict) -> None` — appends to `attempts.json` (a JSON list).
    - `write_report(report: dict) -> str` — writes `report.json`, returns its path.
    - `run_dir` property — the absolute run directory.
    - `load_attempts() -> list[dict]` — reads `attempts.json` back (used by 7C synthesis).
  - `NullRunArtifacts()` — same interface; `save_screenshot` returns `""`, others no-op,
    `load_attempts` returns `[]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_artifacts.py
import base64
import json
from pathlib import Path

from triage.tracing.artifacts import RunArtifacts, NullRunArtifacts


def test_run_artifacts_persists_screenshot_and_records(tmp_path):
    art = RunArtifacts(tmp_path)
    png = base64.b64encode(b"\x89PNG fake bytes").decode()
    ref = art.save_screenshot(attempt=1, step=2, png_b64=png)
    assert ref == "screenshots/attempt1_step2.png"
    assert (Path(art.run_dir) / ref).read_bytes() == b"\x89PNG fake bytes"

    art.record_attempt({"attempt": 1, "bug_detected": False})
    art.record_attempt({"attempt": 2, "bug_detected": True})
    assert [a["bug_detected"] for a in art.load_attempts()] == [False, True]

    path = art.write_report({"verdict": "reproduced"})
    assert json.loads(Path(path).read_text())["verdict"] == "reproduced"


def test_null_run_artifacts_is_safe_noop():
    art = NullRunArtifacts()
    assert art.save_screenshot(1, 1, "ignored") == ""
    art.record_attempt({"x": 1})
    assert art.load_attempts() == []
    art.write_report({"y": 2})  # no raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_run_artifacts.py -v`
Expected: FAIL — `ModuleNotFoundError: triage.tracing.artifacts`.

- [ ] **Step 3: Write minimal implementation**

```python
# triage/tracing/artifacts.py
"""RunArtifacts — per-run store bridging captured evidence to eval (7B) + synthesis (7C).

ReproResultPayload cannot carry screenshots and shared/band.py is untouched, so the
captured PNGs + per-attempt evidence are persisted here instead.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class RunArtifacts:
    def __init__(self, root_dir: str | os.PathLike):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        self._dir = Path(root_dir) / stamp
        (self._dir / "screenshots").mkdir(parents=True, exist_ok=True)
        self._attempts_path = self._dir / "attempts.json"

    @property
    def run_dir(self) -> str:
        return str(self._dir)

    def save_screenshot(self, attempt: int, step: int, png_b64: str) -> str:
        rel = f"screenshots/attempt{attempt}_step{step}.png"
        (self._dir / rel).write_bytes(base64.b64decode(png_b64))
        return rel

    def record_attempt(self, record: dict) -> None:
        data = self.load_attempts()
        data.append(record)
        self._attempts_path.write_text(json.dumps(data, indent=2))

    def load_attempts(self) -> list[dict]:
        if not self._attempts_path.exists():
            return []
        return json.loads(self._attempts_path.read_text())

    def write_report(self, report: dict) -> str:
        path = self._dir / "report.json"
        path.write_text(json.dumps(report, indent=2))
        return str(path)


class NullRunArtifacts:
    run_dir = ""

    def save_screenshot(self, attempt: int, step: int, png_b64: str) -> str:
        return ""

    def record_attempt(self, record: dict) -> None:
        return None

    def load_attempts(self) -> list[dict]:
        return []

    def write_report(self, report: dict) -> str:
        return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_run_artifacts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add triage/tracing/artifacts.py tests/test_run_artifacts.py
git commit -m "feat(phase7a): RunArtifacts per-run store (screenshots + attempts + report)"
```

---

### Task 4: Instrument `run_repro` — per-step `stagehand_action` spans + screenshots

**Files:**
- Modify: `triage/repro_agent/browser.py:74-231` (add optional params + span/artifact calls)
- Test: `tests/test_repro_browser_tracing.py`

**Interfaces:**
- Consumes: `RunTrace.child_span`, `RunArtifacts.save_screenshot`, `set_span_ok` (Task 2/3).
- Produces: `run_repro(cfg, steps, tweak=None, *, run_trace=None, artifacts=None, attempt=1,
  browser_execution_span=None)` — new keyword-only params, all defaulting to no-op/None so
  every existing caller and test is unchanged. When `run_trace` is a real `RunTrace`, each step
  iteration opens a `stagehand_action` child of `browser_execution_span` with attributes
  `step.index`, `step.text`, `action.success`, `screenshot.ref`, and `console.error` (the last
  captured matching error, or ""). Returns the unchanged `ReproResultPayload`.

> **Note on testing without a live browser:** the existing `tests/test_repro_browser.py` tests
> `detect_bug` (pure) only — `run_repro` itself is not unit-tested against a live session. This
> task adds a test that drives `run_repro` with **monkeypatched** `AsyncStagehand` +
> `async_playwright` fakes so the span/artifact wiring is verified offline. Study the real
> `run_repro` body (browser.py:93-231) to mirror the exact attribute access the fakes must
> satisfy (`session.id`, `session.data.cdp_url`, `obs.data.result`, `act_result.data.result.success`,
> `act_result.data.result.message`, `extract_resp.data.result`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_repro_browser_tracing.py
import asyncio
import base64
import types

import pytest

import triage.repro_agent.browser as browser
from triage.tracing.run_context import RunTrace
from tests._tracing_helpers import tracer_and_exporter  # added in Step 3 helper note


class _Cfg:
    browserbase_api_key = "bb"
    anthropic_api_key = "an"
    app_url = "http://app.test"


def _fake_stagehand_and_playwright(monkeypatch, body_text, console_text):
    """Patch AsyncStagehand + async_playwright with minimal async fakes."""
    png = base64.b64encode(b"PNG").decode()

    class _Result:
        def __init__(self, **kw): self.__dict__.update(kw)

    class _Data:
        def __init__(self, result): self.data = types.SimpleNamespace(result=result)

    class _Session:
        id = "sess-123"
        data = types.SimpleNamespace(cdp_url="ws://cdp")
        async def navigate(self, url): return None
        async def observe(self, instruction): return _Data([{"e": 1}])
        async def act(self, input):
            return _Data(_Result(success=True, message="clicked"))
        async def extract(self, instruction, schema):
            return _Data({"body_text": body_text})
        async def end(self): return None

    class _Sessions:
        async def start(self, **kw): return _Session()

    class _Client:
        sessions = _Sessions()
        async def close(self): return None

    class _Page:
        def on(self, event, cb):
            if event == "console" and console_text:
                cb(types.SimpleNamespace(type="error", text=console_text))
        async def screenshot(self): return b"PNG"

    class _Ctx: pages = [_Page()]
    class _Browser:
        contexts = [_Ctx()]
        async def close(self): return None
    class _Chromium:
        async def connect_over_cdp(self, url): return _Browser()
    class _PW:
        chromium = _Chromium()
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None

    monkeypatch.setattr(browser, "AsyncStagehand", lambda **kw: _Client(), raising=False)
    monkeypatch.setattr(browser, "async_playwright", lambda: _PW(), raising=False)
    # browser.py imports these names *inside* run_repro; patch the source modules:
    import stagehand, playwright.async_api as pw_api
    monkeypatch.setattr(stagehand, "AsyncStagehand", lambda **kw: _Client())
    monkeypatch.setattr(pw_api, "async_playwright", lambda: _PW())
    return png


def test_run_repro_emits_one_stagehand_span_per_step(monkeypatch):
    _fake_stagehand_and_playwright(
        monkeypatch, body_text="", console_text="Cannot read properties of undefined")
    tracer, exporter = tracer_and_exporter()

    async def go():
        with RunTrace(tracer) as run:
            with run.attempt_span(1) as attempt:
                with run.child_span("browser_execution", attempt) as be:
                    return await browser.run_repro(
                        _Cfg(), ["click delete", "confirm delete"],
                        run_trace=run, attempt=1, browser_execution_span=be)

    result = asyncio.run(go())
    assert result.success is True  # blank body + matching console error
    steps = [s for s in exporter.get_finished_spans() if s.name == "stagehand_action"]
    assert len(steps) == 2
    assert steps[0].attributes["step.index"] == 1
    assert steps[0].attributes["action.success"] is True
    assert "Cannot read properties of undefined" in steps[1].attributes["console.error"]
```

- [ ] **Step 2: Create the shared test helper, then run to verify it fails**

```python
# tests/_tracing_helpers.py
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def tracer_and_exporter():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("triage-test"), exporter
```

Run: `.venv/bin/pytest tests/test_repro_browser_tracing.py -v`
Expected: FAIL — `run_repro()` got an unexpected keyword argument `run_trace`.

- [ ] **Step 3: Add instrumentation to `run_repro`**

Modify `triage/repro_agent/browser.py`. Change the signature (line 74) and the per-step loop
(lines 144-185). Add keyword-only params and wrap each step. The browser logic is unchanged —
only span open/close, attribute sets, and a screenshot save are added:

```python
# signature (was line 74)
async def run_repro(
    cfg: "Config",
    steps: list[str],
    tweak: str | None = None,
    *,
    run_trace=None,
    artifacts=None,
    attempt: int = 1,
    browser_execution_span=None,
) -> ReproResultPayload:
    ...
    # near the top of the body, after the existing local-var setup:
    from triage.tracing.run_context import NullRunTrace, set_span_ok
    from triage.tracing.artifacts import NullRunArtifacts
    run_trace = run_trace if run_trace is not None else NullRunTrace()
    artifacts = artifacts if artifacts is not None else NullRunArtifacts()
```

Inside the `for index, step in enumerate(steps, start=1):` loop, wrap the existing
observe→act→screenshot body in a span and record the screenshot + console error:

```python
            for index, step in enumerate(steps, start=1):
                with run_trace.child_span("stagehand_action", browser_execution_span) as step_span:
                    step_label = f"step {index}: {step[:48]}"
                    act_instr = step if not tweak else f"{step}. Adjustment for this retry: {tweak}"
                    # ... EXISTING observe/act/evidence lines unchanged ...

                    screenshot_ref = ""
                    try:
                        screenshot_bytes = await page.screenshot()
                        b64 = base64.b64encode(screenshot_bytes).decode()
                        screenshots.append(b64)
                        screenshot_ref = artifacts.save_screenshot(attempt, index, b64)
                        evidence.append(
                            f"Screenshot after '{step_label}': captured ({len(screenshot_bytes)} bytes)")
                    except Exception as exc:  # noqa: BLE001
                        evidence.append(f"Screenshot after '{step_label}': FAILED — {exc}")

                    if step_span is not None:
                        last_err = next((e for e in reversed(console_errors)
                                         if CRASH_SUBSTRING in e), console_errors[-1] if console_errors else "")
                        step_span.set_attribute("step.index", index)
                        step_span.set_attribute("step.text", step)
                        step_span.set_attribute("action.success", bool(act_ok))
                        step_span.set_attribute("screenshot.ref", screenshot_ref)
                        step_span.set_attribute("console.error", last_err)
                        set_span_ok(step_span, bool(act_ok))
```

> Keep every existing `evidence.append`, `logger`, and detection line. Only the `with`
> wrapper, `screenshot_ref`, and the `step_span` attribute block are new.

- [ ] **Step 4: Run the new test + the existing browser test**

Run: `.venv/bin/pytest tests/test_repro_browser_tracing.py tests/test_repro_browser.py -v`
Expected: PASS (new tracing test) and PASS (existing `detect_bug` tests untouched).

- [ ] **Step 5: Commit**

```bash
git add triage/repro_agent/browser.py tests/test_repro_browser_tracing.py tests/_tracing_helpers.py
git commit -m "feat(phase7a): per-step stagehand_action spans + screenshot refs in run_repro"
```

---

### Task 5: Instrument `_run_attempt` — `repro_attempt` span + honest `bug.detected` + attempt record

**Files:**
- Modify: `triage/repro_agent/echo.py:46-143` (`make_repro_callback` + `_run_attempt`)
- Test: `tests/test_repro_echo_tracing.py`

**Interfaces:**
- Consumes: `RunTrace.attempt_span`/`child_span`, `RunArtifacts.record_attempt`, `set_span_ok`,
  and the instrumented `run_repro` (Task 4).
- Produces: `make_repro_callback(cfg, state=None, *, run_trace=None, artifacts=None)` — new
  keyword-only params default to no-op objects. `_run_attempt` opens `repro_attempt` (via
  `run_trace.attempt_span`) wrapping a `browser_execution` child, passes that child span +
  `attempt`/`artifacts` into `run_repro`, sets `bug.detected` from `result.success`, sets
  `browserbase.session_url`, and calls `artifacts.record_attempt(...)`. **No routing logic
  changes.**

- [ ] **Step 1: Write the failing test**

```python
# tests/test_repro_echo_tracing.py
import asyncio
import types

import triage.repro_agent.echo as echo
from triage.repro_agent.loop import ReproLoopState
from triage.shared.band import ReproResultPayload
from triage.tracing.run_context import RunTrace
from triage.tracing.artifacts import RunArtifacts
from tests._tracing_helpers import tracer_and_exporter


class _Ids:
    agent_id = "x"


class _Cfg:
    band_parser = _Ids(); band_hypothesis = _Ids(); app_url = "http://app"
    github_issue_url = "http://issue"


class _Agent:
    def __init__(self): self.events = []; self.messages = []
    async def send_event(self, *a, **k): self.events.append(a)
    async def send_message(self, recipients, text): self.messages.append((recipients, text))


def test_run_attempt_emits_repro_attempt_span_with_honest_flag(monkeypatch, tmp_path):
    async def fake_run_repro(cfg, steps, tweak=None, **kw):
        return ReproResultPayload(success=True, evidence=["e"],
                                  console_errors=["Cannot read..."],
                                  session_url="https://www.browserbase.com/sessions/abc")
    monkeypatch.setattr(echo, "run_repro", fake_run_repro)

    tracer, exporter = tracer_and_exporter()
    art = RunArtifacts(tmp_path)
    state = ReproLoopState(); state.steps = ["click delete"]; state.attempts = 0

    async def go():
        with RunTrace(tracer) as run:
            await echo._run_attempt(_Cfg(), state, _Agent(), tweak=None,
                                    run_trace=run, artifacts=art)

    asyncio.run(go())
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert "repro_attempt" in spans
    assert spans["repro_attempt"].attributes["bug.detected"] is True
    assert spans["repro_attempt"].attributes["attempt.number"] == 1
    assert "browserbase.session_url" in spans["repro_attempt"].attributes
    assert art.load_attempts()[0]["bug_detected"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_repro_echo_tracing.py -v`
Expected: FAIL — `_run_attempt()` got an unexpected keyword argument `run_trace`.

- [ ] **Step 3: Thread tracing through `make_repro_callback` and `_run_attempt`**

In `triage/repro_agent/echo.py`:

```python
def make_repro_callback(cfg, state=None, *, run_trace=None, artifacts=None):
    from triage.tracing.run_context import NullRunTrace
    from triage.tracing.artifacts import NullRunArtifacts
    state = state if state is not None else ReproLoopState()
    run_trace = run_trace if run_trace is not None else NullRunTrace()
    artifacts = artifacts if artifacts is not None else NullRunArtifacts()

    async def on_message(payload, agent) -> None:
        ...  # UNCHANGED routing; replace the three _run_attempt(...) calls with:
        # await _run_attempt(cfg, state, agent, tweak=None, run_trace=run_trace, artifacts=artifacts)
        # await _run_attempt(cfg, state, agent, tweak=tweak, run_trace=run_trace, artifacts=artifacts)
    return on_message
```

Rewrite `_run_attempt` to wrap the browser call (keep all existing event/message sends):

```python
async def _run_attempt(cfg, state, agent, tweak, *, run_trace=None, artifacts=None) -> None:
    from triage.tracing.run_context import NullRunTrace, set_span_ok
    from triage.tracing.artifacts import NullRunArtifacts
    run_trace = run_trace if run_trace is not None else NullRunTrace()
    artifacts = artifacts if artifacts is not None else NullRunArtifacts()

    state.attempts += 1
    await agent.send_event(
        f"Starting Browserbase repro attempt {state.attempts}/{state.max_attempts}"
        + (f" (tweak: {tweak})" if tweak else ""), "task")

    with run_trace.attempt_span(state.attempts) as attempt_span:
        if attempt_span is not None:
            attempt_span.set_attribute("github.issue_url", cfg.github_issue_url)
            attempt_span.set_attribute("app.url", cfg.app_url)
        try:
            with run_trace.child_span("browser_execution", attempt_span) as be:
                result = await run_repro(
                    cfg, state.steps, tweak=tweak, run_trace=run_trace,
                    artifacts=artifacts, attempt=state.attempts,
                    browser_execution_span=be)
        except Exception as exc:  # noqa: BLE001
            logger.error("[ReproAgent] browser execution failed: %s", exc)
            await agent.send_event(f"Browser execution error: {exc}", "error")
            result = ReproResultPayload(success=False, evidence=[f"Execution error: {exc}"],
                                        console_errors=[], session_url="")

        if attempt_span is not None:
            attempt_span.set_attribute("bug.detected", bool(result.success))
            attempt_span.set_attribute("browserbase.session_url", result.session_url)
            set_span_ok(attempt_span, bool(result.success))

    if result.session_url:
        state.session_urls.append(result.session_url)
    artifacts.record_attempt({
        "attempt": state.attempts, "steps": list(state.steps),
        "evidence": result.evidence, "console_errors": result.console_errors,
        "session_url": result.session_url, "bug_detected": bool(result.success),
    })
    await agent.send_event(
        f"Attempt {state.attempts} complete — bug_detected={result.success}, "
        f"{len(result.console_errors)} console error(s)", "task")
    text = format_result_message(result)
    await agent.send_message(["HypothesisAgent"], text)
    print(f"[ReproAgent] >> attempt {state.attempts} result @HypothesisAgent sent.")
```

> The three `await _run_attempt(...)` call sites inside `on_message` must pass the new
> keyword args. Routing/terminal logic is byte-for-byte unchanged.

- [ ] **Step 4: Run the new test + existing echo/loop tests**

Run: `.venv/bin/pytest tests/test_repro_echo_tracing.py tests/test_repro_echo.py tests/test_repro_loop.py -v`
Expected: PASS (new) and PASS (existing — no-op defaults preserve behavior).

- [ ] **Step 5: Commit**

```bash
git add triage/repro_agent/echo.py tests/test_repro_echo_tracing.py
git commit -m "feat(phase7a): repro_attempt span — honest bug.detected + attempt record"
```

---

### Task 6: Wrap Parser/Hypothesis Claude calls in spans

**Files:**
- Modify: `triage/parser_agent/agent.py` (call site of `extract_steps`)
- Modify: `triage/hypothesis_agent/agent.py` (call site of `diagnose`)
- Test: `tests/test_claude_call_spans.py`

**Interfaces:**
- Consumes: `RunTrace.claude_span` (Task 2). Both agent callback factories gain an optional
  keyword `run_trace=None` (default `NullRunTrace`). The actual Claude call is wrapped in
  `with run_trace.claude_span("parser_extract_steps" | "hypothesis_generation", attempt_number=...)`.
- Produces: `make_on_message(..., run_trace=None)` (parser) and
  `make_diagnosis_callback(..., run_trace=None)` (hypothesis). No reasoning logic changes.

> **Read first:** open both `triage/parser_agent/agent.py` and `triage/hypothesis_agent/agent.py`
> to find the exact factory signatures and where `extract_steps(...)` / `diagnose(...)` are
> awaited. Wrap only the call; do not alter prompt building, routing, or message formatting.
> `auto_instrument=True` already produces a child Anthropic span inside this wrapper, so the
> wrapper just provides the correct parent + the `attempt.number` tag.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_claude_call_spans.py
import asyncio
import types

from triage.tracing.run_context import RunTrace
from tests._tracing_helpers import tracer_and_exporter
from triage.hypothesis_agent.agent import make_diagnosis_callback


def test_diagnose_call_is_wrapped_in_span(monkeypatch):
    # Fake anthropic client whose messages.create returns a confirm diagnosis.
    import triage.hypothesis_agent.reasoning as reasoning

    class _Block: type = "text"; text = '{"decision":"confirm","root_cause":"x","redirect_instruction":""}'
    class _Resp: content = [_Block()]
    class _Msgs:
        def create(self, **kw): return _Resp()
    class _Client: messages = _Msgs()

    tracer, exporter = tracer_and_exporter()
    cb = make_diagnosis_callback(_Client(), repro_agent_id="repro-1", run_trace=None)
    # With NullRunTrace (run_trace=None) this still runs; now test the real one:
    cb2 = make_diagnosis_callback(_Client(), repro_agent_id="repro-1")

    payload = types.SimpleNamespace(sender_id="repro-1", sender_name="ReproAgent",
                                    content="verdict: BUG REPRODUCED")

    class _Agent:
        async def send_message(self, *a, **k): pass
        async def send_event(self, *a, **k): pass

    async def go(callback):
        with RunTrace(tracer):
            await callback(payload, _Agent())

    # Re-create the callback bound to the real run_trace inside go():
    def make_with(run):
        return make_diagnosis_callback(_Client(), repro_agent_id="repro-1", run_trace=run)

    async def go2():
        with RunTrace(tracer) as run:
            await make_with(run)(payload, _Agent())

    asyncio.run(go2())
    names = [s.name for s in exporter.get_finished_spans()]
    assert "hypothesis_generation" in names
```

> Adjust `make_diagnosis_callback`'s real signature to match what you find in the file. The
> assertion that matters: a `hypothesis_generation` span is emitted when a real `RunTrace` is
> threaded in.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_claude_call_spans.py -v`
Expected: FAIL — `make_diagnosis_callback()` got an unexpected keyword argument `run_trace`.

- [ ] **Step 3: Add the `run_trace` param + wrap the calls**

In `triage/hypothesis_agent/agent.py`, add `run_trace=None` to `make_diagnosis_callback`,
default it to `NullRunTrace()`, and wrap the `diagnose(...)` call (typically run via
`asyncio.to_thread`) :

```python
    from triage.tracing.run_context import NullRunTrace
    run_trace = run_trace if run_trace is not None else NullRunTrace()
    ...
    with run_trace.claude_span("hypothesis_generation"):
        diagnosis = await asyncio.to_thread(diagnose, payload.content, client)
```

In `triage/parser_agent/agent.py`, add `run_trace=None` to `make_on_message` (and
`post_initial_steps` if it calls `extract_steps`), default to `NullRunTrace()`, and wrap:

```python
    with run_trace.claude_span("parser_extract_steps"):
        steps_payload = await extract_steps(issue, client=anthropic_client, redirect=redirect)
```

- [ ] **Step 4: Run the new test + existing parser/hypothesis agent tests**

Run: `.venv/bin/pytest tests/test_claude_call_spans.py tests/test_parser_agent.py tests/test_hypothesis_agent.py -v`
Expected: PASS (new) and PASS (existing — `run_trace` defaults to no-op).

- [ ] **Step 5: Commit**

```bash
git add triage/parser_agent/agent.py triage/hypothesis_agent/agent.py tests/test_claude_call_spans.py
git commit -m "feat(phase7a): wrap Parser/Hypothesis Claude calls in run-trace spans"
```

---

### Task 7: `scripts/phase7_traced_run.py` — the traced demo runner

**Files:**
- Create: `scripts/phase7_traced_run.py`
- (No unit test — this is an integration entrypoint; verified by the live smoke in Step 4.)

**Interfaces:**
- Consumes: `setup_tracing`, `RunTrace`, `RunArtifacts`, and the now-instrumented callbacks
  (`make_repro_callback(..., run_trace=, artifacts=)`, `make_on_message(..., run_trace=)`,
  `make_diagnosis_callback(..., run_trace=)`).
- Produces: a single-process run that registers Phoenix, opens the root `triage_run` span,
  threads the shared `RunTrace`/`RunArtifacts` into all three real callbacks, runs the real
  loop to terminal, and leaves a hook (`# 7B eval / 7C synthesis go here`) for inline
  evaluation + synthesis. Supports `--force-retry` (same semantics as phase6).

- [ ] **Step 1: Write the runner (copy phase6 structure, add tracing)**

```python
#!/usr/bin/env python
"""Phase 7 traced run — the real Phase-6 retry loop under one Arize root span.

Single-process by design (§3 of the design spec): all three real callbacks share
one RunTrace root context, so the trace tree nests across async Band callbacks.
Mirrors scripts/phase6_live_run.py; --force-retry drives a real fail->succeed.
"""
from __future__ import annotations

import asyncio
import sys
import time

import anthropic
import httpx
from dotenv import load_dotenv

load_dotenv()

from triage.config import load_config
from triage.hypothesis_agent.agent import make_diagnosis_callback
from triage.parser_agent.agent import format_steps_message, make_on_message, post_initial_steps
from triage.parser_agent.github import fetch_issue
from triage.repro_agent.echo import make_repro_callback
from triage.repro_agent.loop import ReproLoopState
from triage.shared.band import BandAgent, ReproStepsPayload
from triage.tracing.setup import setup_tracing
from triage.tracing.run_context import RunTrace
from triage.tracing.artifacts import RunArtifacts

WALL_CLOCK_TIMEOUT = 600
STABILISE = 2.0
_FORCED_BROKEN_STEPS = [
    "Click the Delete button on the first task in the list",
    "Click the 'Yes, delete' confirmation button to confirm the deletion",
    "Click the Delete button on the next remaining task in the list",
    "Click the 'Yes, delete' confirmation button to confirm the deletion",
]


async def main(force_retry: bool = False) -> int:
    cfg = load_config()
    tracer = setup_tracing(cfg)

    parser_anthropic = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)
    hypothesis_anthropic = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    http_client = httpx.AsyncClient()
    issue_cache: dict = {"issue": None}
    repro_state = ReproLoopState()

    with RunTrace(tracer, issue_url=cfg.github_issue_url, app_url=cfg.app_url) as run:
        artifacts = RunArtifacts("./.triage_runs")
        print(f"[phase7] run dir: {artifacts.run_dir}")

        repro = BandAgent(name="ReproAgent", agent_id=cfg.band_repro.agent_id,
                          api_key=cfg.band_repro.api_key,
                          on_message=make_repro_callback(cfg, repro_state,
                                                         run_trace=run, artifacts=artifacts))
        parser = BandAgent(name="ParserAgent", agent_id=cfg.band_parser.agent_id,
                           api_key=cfg.band_parser.api_key,
                           on_message=make_on_message(cfg, anthropic_client=parser_anthropic,
                                                      http_client=http_client,
                                                      issue_cache=issue_cache, run_trace=run))
        hypothesis = BandAgent(name="HypothesisAgent", agent_id=cfg.band_hypothesis.agent_id,
                               api_key=cfg.band_hypothesis.api_key,
                               on_message=make_diagnosis_callback(hypothesis_anthropic,
                                                                  cfg.band_repro.agent_id,
                                                                  run_trace=run))

        room_id = await repro.connect(room_id=cfg.band_room_id)
        if cfg.band_room_id is None:
            await repro.add_participant("ParserAgent")
            await repro.add_participant("HypothesisAgent")
        await parser.connect(room_id=room_id)
        await hypothesis.connect(room_id=room_id)
        await asyncio.sleep(STABILISE)

        if force_retry:
            issue_cache["issue"] = await fetch_issue(cfg.github_issue_url, http_client=http_client)
            broken = ReproStepsPayload(issue_url=cfg.github_issue_url, steps=_FORCED_BROKEN_STEPS)
            await parser.send_message(["ReproAgent"], format_steps_message(broken))
        else:
            await post_initial_steps(cfg, anthropic_client=parser_anthropic,
                                     http_client=http_client, agent=parser, issue_cache=issue_cache)

        deadline = time.monotonic() + WALL_CLOCK_TIMEOUT
        while not repro_state.terminal and time.monotonic() < deadline:
            await asyncio.sleep(1)

        # --- 7B inline evaluator + 7C synthesis hook (wired by those plans) ---
        # from triage.eval.run_eval import run_eval; run_eval(cfg, repro_state, artifacts)
        # from triage.synthesis.synthesize import synthesize_run; synthesize_run(cfg, artifacts, ...)

        print("\n=== RUN SUMMARY ===")
        print(f"terminal: {repro_state.terminal}  attempts: {repro_state.attempts}/{repro_state.max_attempts}")
        for i, url in enumerate(repro_state.session_urls, 1):
            print(f"  attempt {i}: {url}")

        await parser.disconnect()
        await hypothesis.disconnect()
        await repro.disconnect()
        await http_client.aclose()
        return 0 if repro_state.terminal else 1


if __name__ == "__main__":
    force = "--force-retry" in sys.argv[1:]
    try:
        sys.exit(asyncio.run(main(force_retry=force)))
    except KeyboardInterrupt:
        print("\n[phase7_traced_run] interrupted.")
        sys.exit(0)
```

> If `post_initial_steps` / `make_on_message` keyword names differ from the above, match the
> real signatures (Task 6 added `run_trace`). Do not change their other arguments.

- [ ] **Step 2: Byte-check it imports**

Run: `.venv/bin/python -c "import ast; ast.parse(open('scripts/phase7_traced_run.py').read()); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Run the full suite (regression gate)**

Run: `.venv/bin/pytest -q`
Expected: PASS — all prior tests plus the new tracing tests; no regressions.

- [ ] **Step 4: Live smoke (manual — requires real keys + network)**

Run: `.venv/bin/python scripts/phase7_traced_run.py --force-retry`
Expected: reaches a terminal state; in Phoenix (`app.phoenix.arize.com`, project
`triage-bug-repro`) a single `triage_run` trace shows `parser_extract_steps` → `repro_attempt`
(#1, `bug.detected=false`) → `hypothesis_generation` → re-parse → `repro_attempt` (#2,
`bug.detected=true`) → `hypothesis_generation`. `./.triage_runs/<ts>/attempts.json` + screenshots
exist. **Confirm the fail→succeed flip is honest (False→True from detection, not hard-coded).**

- [ ] **Step 5: Commit**

```bash
git add scripts/phase7_traced_run.py
git commit -m "feat(phase7a): phase7_traced_run.py — real loop under one Arize root span"
```

---

## Self-Review (Plan 7A)

- **Spec coverage:** §4.0 substrate → Tasks 1-3; §4.1 instrumentation → Tasks 4-6; runner → Task 7;
  honest `bug.detected` → Task 5; deps/env (tracing half) → Task 0. Evaluator (§4.2) and synthesis
  (§4.3) are **separate plans** (7B, 7C) that consume Task 3's `RunArtifacts` + Task 5's span names.
- **Placeholder scan:** none — all steps carry concrete code/commands. The `# 7B/7C hook` comment in
  Task 7 is an intentional seam those plans fill, not a TODO in this plan's scope.
- **Type consistency:** `run_trace`/`artifacts` keyword names, `attempt_span`/`child_span`/`claude_span`,
  `save_screenshot`/`record_attempt`/`load_attempts`/`write_report`, span names (`triage_run`,
  `repro_attempt`, `browser_execution`, `stagehand_action`, `bug_detection`, `parser_extract_steps`,
  `hypothesis_generation`) are consistent across Tasks 1-7.
