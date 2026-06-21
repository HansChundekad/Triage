# Phoenix → Arize AX Trace-Backend Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repoint TRIAGE's trace backend from open-source Phoenix to Arize AX (`app.arize.com`) — write path, read path, and evaluators — so the Arize sponsor judges see traces/spans/evals where they expect, while keeping Phoenix working behind a single backend selector as a fallback.

**Architecture:** A single config selector (`trace_backend`, default `ax`) drives both the write path (`tracing/setup.py` → `arize.otel.register`) and the read path (`memory/history.py` → `backends/ax.py` via `arize` SDK `spans.export_to_df`). Eval results from the in-code judges are written to AX as first-class `eval.*` evaluations via `spans.update_evaluations`, keyed by span-ids captured **in-process** at span creation. The OpenInference span structure, the inner loop, Band, and the local LLM-judge engine (`phoenix.evals`) are untouched.

**Tech Stack:** Python 3.11+ (dev 3.14), `arize-otel==0.13.0`, `arize==8.35.0`, `arize-ax-cli==0.25.0` (verification), OpenTelemetry/OpenInference, pandas, pytest.

## Global Constraints

- Do **not** modify: `triage/shared/band.py`, inner loop (`triage/repro_agent/loop.py`, `echo.py`, `triage/hypothesis_agent/reasoning.py`), Phase 6 retry loop, or any agent decision logic.
- `bug.detected` must stay honest — the fail→succeed flip is real, never faked (rule 8).
- Agent names exact: `ParserAgent`/`ReproAgent`/`HypothesisAgent`. Every Band `send_message` keeps ≥1 `@mention`.
- Never commit secrets: real `ARIZE_API_KEY`/`ARIZE_SPACE_ID` live in `.env` (gitignored); `.env.example` gets placeholders only.
- Project name on all spans stays `"triage-bug-repro"`.
- Tests run via `.venv/bin/pytest`. Per-task commits, scoped messages, `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Phoenix must remain a working fallback via `TRIAGE_TRACE_BACKEND=phoenix`.
- If AX auth/ingestion fails (401/403/persistent ingest error): STOP, report, fall back to tag `pre-ax-migration`.

---

## Complete Phoenix-reference inventory (every reference + the change at each)

| # | File | Phoenix reference | Change | Task |
|---|------|-------------------|--------|------|
| 1 | `triage/config.py` | `PHOENIX_API_KEY` required; `PHOENIX_COLLECTOR_ENDPOINT` default; `phoenix_*` fields | Add `arize_api_key`, `arize_space_id`, `trace_backend` fields; require ARIZE vars when backend=ax; make PHOENIX vars optional (required only when backend=phoenix) | T0 |
| 2 | `.env.example` | `--- Arize Phoenix ---` block | Add `--- Arize AX (primary) ---` block (`ARIZE_API_KEY`, `ARIZE_SPACE_ID`, `TRIAGE_TRACE_BACKEND=ax`); keep Phoenix block labelled "fallback" | T0 |
| 3 | `triage/tracing/setup.py` | `from phoenix.otel import register`; sets `PHOENIX_API_KEY`/`PHOENIX_COLLECTOR_ENDPOINT` env | Branch on `trace_backend`: `ax` → `arize.otel.register(space_id, api_key, project_name, auto_instrument=True, batch=False)`; `phoenix` → existing behavior | T1 |
| 4 | `triage/tracing/__init__.py` | docstring "Arize Phoenix tracing substrate" | Reword to "Arize AX tracing substrate (Phoenix fallback)" | T1 |
| 5 | `triage/memory/history.py` | `TRACE_BACKEND = "phoenix"` | Flip default to `"ax"`; dispatch prefers `getattr(cfg, "trace_backend", TRACE_BACKEND)` | T3 |
| 6 | `triage/memory/backends/ax.py` | `NotImplementedError` stub | Implement `fetch_prior_run_history` via `arize` SDK `spans.export_to_df` + pure `parse_prior_attempts` for the AX export shape | T3 |
| 7 | `triage/memory/backends/__init__.py` | docstring: "`ax` is a stub for the migration agent" | Reword: both backends implemented; selected by `trace_backend` | T3 |
| 8 | `triage/memory/types.py` | docstring mentions "(future) Arize AX" | Reword "(future)" → "Arize AX" (active). No code change | T3 |
| 9 | `triage/memory/__init__.py` | docstring "(Phoenix today, Arize AX after the migration)" | Reword to "(Arize AX; Phoenix fallback)". No code change | T3 |
| 10 | `triage/eval/run_eval.py` | `_phoenix_span_lookup` (queries phoenix.client); `_log_to_spans` (phoenix.client `log_span_annotations_dataframe`); DRIFT NOTE docstring | Replace span-logging with AX `spans.update_evaluations`; replace default `_phoenix_span_lookup` with the in-process capture (no query-back). `score_attempts`/judges (`phoenix.evals`) UNCHANGED — local engine | T5,T6 |
| 11 | `triage/eval/judges.py` | `from phoenix.evals import ...`, `from phoenix.evals.llm import LLM` | **No change** — local LLM-judge engine, not a backend (D4) | — |
| 12 | `triage/eval/__init__.py` | docstring "Phoenix evaluator (Phase 7B)" | Reword "Phoenix evaluator" → "evaluator" (engine-neutral) | T6 |
| 13 | `triage/tracing/run_context.py` | (no Phoenix ref) | Add in-process span-id capture: `attempt_span` records `{number: span_id_hex}`; expose `span_ids` dict (D3) | T5 |
| 14 | `scripts/phase7_traced_run.py` | `setup_tracing(cfg)`; `run_eval(...)` without span_lookup | Thread `run.span_ids` into `run_eval(..., span_lookup=run.span_ids)` | T5 |
| 15 | `scripts/phase7_eval.py` | docstring "existing Phoenix project"; calls `run_eval` (which will use `_phoenix_span_lookup` default) | Best-effort: update docstring; pass an AX span-lookup (export-based) or note it requires the harness path. Non-load-bearing | T8 |
| 16 | `backend/run_manager.py:241` | comment "Decoupled from Phoenix span-logging" | Reword "Phoenix" → "Arize AX". No logic change (booth path is backend-decoupled, D5) | T8 |
| 17 | `docs/TRIAGE_INTEGRATIONS.md` §4 | "Arize Phoenix" section | Add AX setup (register/endpoint/auth, export, update_evaluations); mark Phoenix fallback | T8 |
| 18 | `docs/STATUS.md` | "Arize Phoenix" tracing narrative; `.env` requirements | Update to AX primary + Phoenix fallback; new env vars | T8 |
| 19 | `pyproject.toml` | deps `arize-phoenix*` | Add `arize-otel`, `arize`; keep `arize-phoenix*` (fallback + local `phoenix.evals` judge engine) | T8 |
| 20 | Tests: `test_config.py`, `test_tracing_setup.py`, `test_memory_history.py` | assert Phoenix defaults | Update for ARIZE vars + `trace_backend=ax` default + arize register branch | T0,T1,T3 |
| 21 | New tests: `test_memory_backend_ax.py`, eval-logging tests | — | Pure-parser tests for AX export shape; in-process span-id capture; update_evaluations dataframe builder | T3,T5,T6 |

---

## File structure

- **Modified:** `triage/config.py`, `triage/tracing/setup.py`, `triage/tracing/run_context.py`, `triage/tracing/__init__.py`, `triage/memory/history.py`, `triage/memory/backends/ax.py`, `triage/memory/backends/__init__.py`, `triage/memory/types.py`, `triage/memory/__init__.py`, `triage/eval/run_eval.py`, `triage/eval/__init__.py`, `scripts/phase7_traced_run.py`, `scripts/phase7_eval.py`, `backend/run_manager.py`, `.env.example`, `pyproject.toml`, `docs/TRIAGE_INTEGRATIONS.md`, `docs/STATUS.md`.
- **New tests:** `tests/test_memory_backend_ax.py`, `tests/test_eval_ax_logging.py`.
- **Modified tests:** `tests/test_config.py`, `tests/test_tracing_setup.py`, `tests/test_memory_history.py`.

---

### Task T0: Config + env — surface AX credentials and the backend selector

**Files:**
- Modify: `triage/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config.arize_api_key: str`, `Config.arize_space_id: str`, `Config.trace_backend: str` (`"ax"` default), `Config.arize_project_name: str` (`"triage-bug-repro"`). `phoenix_api_key`/`phoenix_collector_endpoint` kept but optional.

- [ ] **Step 1: Write failing tests** in `tests/test_config.py`: with `TRIAGE_TRACE_BACKEND` unset and ARIZE_* set, `load_config().trace_backend == "ax"` and `arize_api_key`/`arize_space_id` populated; with backend `ax`, missing `ARIZE_API_KEY`/`ARIZE_SPACE_ID` raises `MissingConfigError`; with `TRIAGE_TRACE_BACKEND=phoenix`, missing `PHOENIX_API_KEY` raises and ARIZE vars not required. Update the existing `REQUIRED` list so the "all required" test sets ARIZE vars instead of `PHOENIX_API_KEY`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_config.py -q` → FAIL.
- [ ] **Step 3: Implement** in `config.py`: add `arize_api_key`, `arize_space_id`, `arize_project_name`, `trace_backend` to `Config`; read `TRIAGE_TRACE_BACKEND` (default `"ax"`); compute required vars dynamically — base set (Anthropic/Browserbase/Band×6/TRIAGE_APP_URL/TRIAGE_GITHUB_ISSUE_URL) plus, when `trace_backend=="ax"`, `ARIZE_API_KEY` + `ARIZE_SPACE_ID`; when `"phoenix"`, `PHOENIX_API_KEY`. `arize_project_name` defaults to `"triage-bug-repro"` (env `ARIZE_PROJECT_NAME`). Keep `phoenix_*` fields (default endpoint unchanged).
- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_config.py -q` → PASS.
- [ ] **Step 5: Update `.env.example`** — add an `--- Arize AX (primary trace backend) ---` block with `ARIZE_API_KEY=`, `ARIZE_SPACE_ID=`, `ARIZE_PROJECT_NAME=triage-bug-repro`, `TRIAGE_TRACE_BACKEND=ax`, with comments (AX key is `ak-...` from app.arize.com → Settings → API Keys; space ID is the base64 `U3BhY2U6...`). Re-label the Phoenix block "fallback only (`TRIAGE_TRACE_BACKEND=phoenix`)".
- [ ] **Step 6: Set real values in `.env`** (gitignored): `ARIZE_API_KEY`, `ARIZE_SPACE_ID`, `TRIAGE_TRACE_BACKEND=ax`. Confirm `.venv/bin/python -c "from triage.config import load_config; c=load_config(); print(c.trace_backend, bool(c.arize_api_key), bool(c.arize_space_id))"` prints `ax True True`.
- [ ] **Step 7: Commit** `feat(ax): add ARIZE_* config + TRIAGE_TRACE_BACKEND selector (default ax)`.

---

### Task T1: Write path — `setup_tracing` registers the AX tracer

**Files:**
- Modify: `triage/tracing/setup.py`, `triage/tracing/__init__.py`
- Test: `tests/test_tracing_setup.py`

**Interfaces:**
- Consumes: `Config.trace_backend`, `.arize_space_id`, `.arize_api_key`, `.arize_project_name`, `.phoenix_*`.
- Produces: `setup_tracing(cfg, *, _register=None)` returns a tracer with `start_as_current_span`; idempotent.

- [ ] **Step 1: Rewrite tests** in `tests/test_tracing_setup.py`: a `_Cfg` with `trace_backend="ax"`, `arize_space_id="S"`, `arize_api_key="ak-x"`, `arize_project_name="triage-bug-repro"`. Assert the injected `_register` is called **once** with `space_id="S", api_key="ak-x", project_name="triage-bug-repro", auto_instrument=True, batch=False`; idempotent (second call doesn't re-register); returns a usable tracer. Add a second test: `trace_backend="phoenix"` calls register with `project_name="triage-bug-repro", auto_instrument=True` and sets the `PHOENIX_*` env vars (existing behavior).
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_tracing_setup.py -q` → FAIL.
- [ ] **Step 3: Implement** `setup.py`: keep the `_registered` idempotency + `trace.get_tracer("triage")` return. Branch on `getattr(cfg, "trace_backend", "ax")`:
  - `"ax"`: `register = _register or (lambda **kw: __import__("arize.otel", fromlist=["register"]).register(**kw))`; call `register(space_id=cfg.arize_space_id, api_key=cfg.arize_api_key, project_name=cfg.arize_project_name, auto_instrument=True, batch=False)`. Do **not** set PHOENIX env.
  - `"phoenix"`: existing path (set `PHOENIX_API_KEY`/`PHOENIX_COLLECTOR_ENDPOINT`; `phoenix.otel.register(project_name=_PROJECT_NAME, auto_instrument=True)`).
  (Use a clean local import for `arize.otel.register`, mirroring the existing lazy phoenix import.)
- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_tracing_setup.py -q` → PASS.
- [ ] **Step 5: Reword** `triage/tracing/__init__.py` docstring to "Arize AX tracing substrate (Phase 7A; Phoenix fallback). Optional + no-op by default."
- [ ] **Step 6: Commit** `feat(ax): setup_tracing registers arize.otel tracer (batch=False); phoenix fallback`.

---

### Task T2: VERIFY write path — one real traced run lands in AX (Step 2 gate)

**Files:** none (verification only). **Not TDD** — this is the live ingestion gate.

- [ ] **Step 1:** Ensure `.env` has real AX creds + `TRIAGE_TRACE_BACKEND=ax`. Configure the `ax` CLI for verification: `export ARIZE_API_KEY=...; export ARIZE_SPACE=<space-id>; .venv/bin/ax profiles create --api-key $ARIZE_API_KEY` (or `update`). Confirm `.venv/bin/ax profiles show`.
- [ ] **Step 2:** Run one traced repro: `.venv/bin/python scripts/phase7_traced_run.py --force-retry`. Capture the printed run dir and (added in T5) the run's `trace_id`/span-ids. Confirm the run completes (terminal true) and prints no tracing errors.
- [ ] **Step 3:** Verify ingestion via **trace-id (primary store, immediate)** — not a time-range query (avoids R-LAG): `.venv/bin/ax spans export triage-bug-repro --trace-id <TRACE_ID> --output-dir .arize-tmp-traces`. Confirm the export contains the `triage_run` root, two `repro_attempt` spans, `browser_execution`/Claude child spans, and attributes `attempt.number`, `bug.detected`, `github.issue_url`.
- [ ] **Step 4:** Record the **exact AX export attribute shape** (flat dotted vs nested) from the JSON — this is the input contract for the T3 parser. Save a sample span JSON to the spec/notes.
- [ ] **Step 5 (GATE):** If spans appear with child structure + attributes → proceed. If 401/403 or no spans after a trace-id lookup → **STOP**, report the precise failure (auth vs ingest vs export), and recommend the `pre-ax-migration` fallback. Do not proceed to read/eval until write is confirmed.

---

### Task T3: Read path — implement the AX backend + flip the seam

**Files:**
- Modify: `triage/memory/backends/ax.py`, `triage/memory/history.py`, `triage/memory/backends/__init__.py`, `triage/memory/types.py`, `triage/memory/__init__.py`
- Test: `tests/test_memory_backend_ax.py` (new), `tests/test_memory_history.py`

**Interfaces:**
- Consumes: real AX export shape captured in T2-Step4; `Config.arize_api_key`, `.arize_space_id`, `.arize_project_name`.
- Produces: `backends/ax.py:fetch_prior_run_history(cfg, *, issue_url, limit=5) -> list[PriorAttempt]`; pure `parse_prior_attempts(rows, *, issue_url, limit) -> list[PriorAttempt]`. `history.TRACE_BACKEND = "ax"`; dispatch honors `getattr(cfg, "trace_backend", TRACE_BACKEND)`.

- [ ] **Step 1: Write failing pure-parser tests** in `tests/test_memory_backend_ax.py` using a small fixture matching the **real** AX export shape from T2-Step4 (rows for a `triage_run` root carrying `github.issue_url` + two `repro_attempt` rows carrying `attempt.number` + `bug.detected`, sharing a `context.trace_id`). Assert: filters by `issue_url`; `reproduced` derived from honest `bug.detected`; within-run ordering by `start_time`; keeps the `limit` most-recent runs; returns `list[PriorAttempt]` identical in contract to the Phoenix adapter. Include an empty-input → `[]` case.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_memory_backend_ax.py -q` → FAIL.
- [ ] **Step 3: Implement** `backends/ax.py`: a pure `parse_prior_attempts` over the AX shape (mirror the Phoenix adapter's logic but read AX's attribute layout — flat-dotted accessor if T2 showed flat keys, else nested), and a live `fetch_prior_run_history` that builds `ArizeClient(api_key=cfg.arize_api_key)`, calls `client.spans.export_to_df(space_id=cfg.arize_space_id, project_name=cfg.arize_project_name, start_time=<now-31d>, end_time=<now>, where="name IN ('triage_run','repro_attempt')")`, converts to rows, and calls `parse_prior_attempts`. May raise (network/auth/lag→empty) — the seam's caller guards it.
- [ ] **Step 4: Run** `.venv/bin/pytest tests/test_memory_backend_ax.py -q` → PASS.
- [ ] **Step 5: Update the seam** `history.py`: `TRACE_BACKEND = "ax"`; dispatch `backend = getattr(cfg, "trace_backend", TRACE_BACKEND)`. Update `tests/test_memory_history.py`: default is now `ax` and delegates to `backends.ax.fetch_prior_run_history` (monkeypatched); a `phoenix`-selected case still delegates to the Phoenix adapter; unknown backend still raises `ValueError`.
- [ ] **Step 6: Run** `.venv/bin/pytest tests/test_memory_history.py tests/test_memory_backend_ax.py tests/test_memory_backend_phoenix.py -q` → PASS.
- [ ] **Step 7: Reword docstrings** in `backends/__init__.py`, `types.py`, `memory/__init__.py` (AX active; Phoenix fallback).
- [ ] **Step 8: Commit** `feat(ax): implement AX trace-query read backend + flip seam default to ax`.

---

### Task T4: VERIFY read path — live read-back returns real prior-run history

**Files:** none (verification only).

- [ ] **Step 1:** `.venv/bin/python -c "from triage.config import load_config; from triage.memory.history import fetch_prior_run_history; print(fetch_prior_run_history(load_config(), issue_url=load_config().github_issue_url, limit=5))"`. Expect a `list[PriorAttempt]` (possibly empty if all traces are <~12 h old — R-LAG).
- [ ] **Step 2:** If empty due to lag, spot-check the parser against the T2 trace by trace-id (`ax spans export ... --trace-id`) fed through `parse_prior_attempts` to prove the parse contract on real data; report the lag honestly.
- [ ] **Step 3:** `.venv/bin/python -c "from triage.config import load_config; from triage.memory import load_learned_context; print(load_learned_context(load_config()))"` with `TRIAGE_OUTER_LOOP=1` → returns a hint string or `None` (guarded). Confirm no crash, no hang.

---

### Task T5: Eval correlation — capture span-ids in-process and thread them to `run_eval`

**Files:**
- Modify: `triage/tracing/run_context.py`, `scripts/phase7_traced_run.py`
- Test: `tests/test_eval_ax_logging.py` (new — capture portion)

**Interfaces:**
- Produces: `RunTrace.span_ids: dict[int, str]` populated by `attempt_span(number)` with `{number: format(span_context.span_id, "016x")}`; `NullRunTrace.span_ids = {}`. Harness passes `span_lookup=run.span_ids` to `run_eval`.

- [ ] **Step 1: Write failing test** in `tests/test_eval_ax_logging.py`: a fake tracer whose started span exposes `get_span_context().span_id` (an int); drive `RunTrace.attempt_span(1)` and assert `run.span_ids == {1: "<016x hex>"}`. Assert `NullRunTrace().span_ids == {}`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_eval_ax_logging.py -q` → FAIL.
- [ ] **Step 3: Implement** in `run_context.py`: `RunTrace.__init__` sets `self.span_ids = {}`; in `attempt_span`, after `set_attribute("attempt.number", number)`, record `self.span_ids[number] = format(span.get_span_context().span_id, "016x")`. Add `span_ids = {}` (class attr) to `NullRunTrace`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Thread into harness** `scripts/phase7_traced_run.py`: change the `run_eval(cfg, repro_state, artifacts, hypothesis_root_cause=diagnosis["text"])` call to also pass `span_lookup=run.span_ids`.
- [ ] **Step 6: Run** `.venv/bin/pytest tests/test_eval_ax_logging.py -q` → PASS. Commit `feat(ax): capture repro_attempt span-ids in-process for eval correlation`.

---

### Task T6: Eval write — log evaluations to AX via `update_evaluations`

**Files:**
- Modify: `triage/eval/run_eval.py`, `triage/eval/__init__.py`
- Test: `tests/test_eval_ax_logging.py`

**Interfaces:**
- Consumes: `scored` DataFrame (cols `attempt_number`, `repro_fidelity_label/score`, `root_cause_label/score`, `honesty_label/score/explanation`), `span_lookup: dict[int,str]`, `Config.arize_*`.
- Produces: `build_eval_records(scored, span_lookup) -> pd.DataFrame` (pure; cols `context.span_id`, `eval.repro_fidelity.label/.score`, `eval.root_cause_correctness.label/.score`, `eval.honesty.label/.score/.explanation`); `_log_to_ax(cfg, eval_df)` calls `ArizeClient(api_key=...).spans.update_evaluations(space_id=..., project_name=..., dataframe=eval_df)`. `run_eval` keeps its `span_lookup=None` injection point but the default no longer queries the backend — it uses the passed-in dict (no query-back).

- [ ] **Step 1: Write failing pure test** in `tests/test_eval_ax_logging.py` for `build_eval_records`: given a 2-row `scored` df + `span_lookup={1:"aaa",2:"bbb"}`, assert the output df has one row per attempt with `context.span_id` set and the three `eval.*` label/score columns populated; a row whose attempt_number is absent from `span_lookup` is dropped.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** in `run_eval.py`: add `build_eval_records` (pure, builds the `eval.*` dataframe). Replace `_log_to_spans`/`_phoenix_span_lookup` usage: when `trace_backend=="ax"`, `run_eval` builds records from the passed `span_lookup` and calls `_log_to_ax(cfg, df)`; keep a `phoenix` branch delegating to the existing `_log_to_spans` for fallback. Guard `_log_to_ax` so a failure is non-fatal (the harness already wraps `run_eval` in try/except, but keep the SDK call defensive). Update the module DRIFT-NOTE docstring to describe the AX `update_evaluations` shape.
- [ ] **Step 4: Run** the pure test → PASS.
- [ ] **Step 5: Reword** `triage/eval/__init__.py` docstring ("evaluator (Phase 7B): LLM judges + code honesty check, per attempt" — drop "Phoenix").
- [ ] **Step 6: Run** `.venv/bin/pytest tests/test_eval_run_eval.py tests/test_eval_ax_logging.py -q` → PASS. Commit `feat(ax): log evaluators to AX via spans.update_evaluations (eval.* columns)`.

---

### Task T7: VERIFY evaluators — `eval.*` land on the AX spans

**Files:** none (verification only).

- [ ] **Step 1:** Run `.venv/bin/python scripts/phase7_traced_run.py --force-retry`. Confirm the printed eval table shows two differently-scored attempts (attempt 1 low/not_reproduced, attempt 2 high/reproduced) and no eval-step error.
- [ ] **Step 2:** Verify in AX by trace-id (primary store): `.venv/bin/ax spans export triage-bug-repro --trace-id <TRACE_ID> --output-dir .arize-tmp-traces`, then grep the JSON for `eval.repro_fidelity`, `eval.root_cause_correctness`, `eval.honesty` on the two `repro_attempt` spans. (Eval index visibility in the UI may lag 1–2 h — R-LAG — but the write response and span_id attachment confirm success.)
- [ ] **Step 3 (GATE):** Confirm `update_evaluations` returned a success response (no 401/403). If the eval write fails on fresh spans, retry with a short backoff; if it persistently fails, report and note the `eval_scores` still render in the report via the booth/judge path (R-LAG documented). Do not fake scores.

---

### Task T8: Docs, deps, residual references, full suite

**Files:**
- Modify: `pyproject.toml`, `docs/TRIAGE_INTEGRATIONS.md`, `docs/STATUS.md`, `backend/run_manager.py`, `scripts/phase7_eval.py`

- [ ] **Step 1:** `pyproject.toml` — add `arize-otel`, `arize` to dependencies; keep `arize-phoenix*` (Phoenix fallback + the local `phoenix.evals` judge engine). Confirm `.venv/bin/pip install -e ".[dev]"` resolves.
- [ ] **Step 2:** `backend/run_manager.py:241` — reword the comment "Decoupled from Phoenix span-logging" → "Decoupled from Arize AX span-logging".
- [ ] **Step 3:** `scripts/phase7_eval.py` — update docstring (AX, not Phoenix); since it lacks in-process span-ids, either pass an AX export-based lookup or document that live eval-logging requires the harness path. Keep non-fatal.
- [ ] **Step 4:** `docs/TRIAGE_INTEGRATIONS.md` §4 — replace/augment the Phoenix section with AX: `arize.otel.register` snippet, `otlp.arize.com` endpoint, `ARIZE_*` auth, `spans.export_to_df` read, `spans.update_evaluations` eval write, the `ax` CLI verification commands, and the R-LAG note. Mark Phoenix "fallback".
- [ ] **Step 5:** `docs/STATUS.md` — update the tracing narrative to "Arize AX primary (Phoenix fallback behind `TRIAGE_TRACE_BACKEND`)"; update the `.env` requirements list (`ARIZE_API_KEY`, `ARIZE_SPACE_ID`, `TRIAGE_TRACE_BACKEND`); note the migration commit range and that 7.5's read-back now reads AX.
- [ ] **Step 6:** Run the **full** suite `.venv/bin/pytest -q` → all green. Run `cd frontend && npm test && npx tsc -b` (unchanged; sanity).
- [ ] **Step 7: Commit** `docs(ax): integrations + status + deps for Phoenix→AX migration`.

---

## Self-review

- **Spec coverage:** write path (T1/T2), read path (T3/T4), evaluators (T6/T7), config/env (T0), Phoenix-fallback seam (T0/T1/T3/T6), docs (T8) — all spec sections mapped. Every row of the Phoenix-reference inventory maps to a task.
- **Verification gates:** T2 (write), T4 (read), T7 (evals) are explicit STOP-and-report gates honoring the user's "if AX fails, stop" rule.
- **Type consistency:** `span_ids: dict[int,str]` produced in T5, consumed as `span_lookup` in T6; `parse_prior_attempts -> list[PriorAttempt]` matches the `PriorAttempt` contract used by the seam and `distill_hint`; `build_eval_records -> DataFrame` with `context.span_id` + `eval.*` matches `update_evaluations`'s expected columns.
- **Order:** write → verify → read → evaluators, exactly as instructed.
