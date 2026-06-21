# Spec — Trace Backend Migration: Arize Phoenix → Arize AX

_Date: 2026-06-21 · Author: migration agent · Status: approved-by-default (user delegated autonomous execution)_

## Problem

TRIAGE instrumented tracing against **open-source Phoenix** (`app.phoenix.arize.com`,
`from phoenix.otel import register`). The Arize sponsor judges on **Arize AX**
(`app.arize.com`) — the commercial SaaS surface. Traces, spans, and evaluators must
land in **AX** so the judge sees them where the booth skills and judging assume.

This is a **config/endpoint migration, not a logic rewrite.** Phoenix and AX share the
OpenTelemetry/OpenInference foundation, so span structure, the parent/child trace tree,
the retry-loop instrumentation, and the LLM-judge engine are OTel/OpenInference-standard
and survive the move. We repoint **where traces are written and read**, nothing more.

## Non-negotiables (from the user + CLAUDE.md + STATUS.md)

1. Rollback tag `pre-ax-migration` exists (cut at `08b254f`). Phoenix remains a working fallback.
2. Do **not** modify agent logic, `triage/shared/band.py`, the Phase 6 inner loop
   (`loop.py`/`echo.py`/`reasoning.py`), or the Phase 6 retry loop.
3. `bug.detected` honesty stays real (rule 8); the fail→succeed flip must not be faked.
4. SDK details verified against live docs/installed SDK **before** writing code (done — see below).
5. If AX ingestion/auth fails, **stop and report** — don't fake; fall back to the tag.

## Verified facts (live docs + installed SDK introspection — 2026-06-21)

Installed into repo `.venv`: `arize-otel==0.13.0`, `arize==8.35.0`, `arize-ax-cli==0.25.0`.

### Write path (spans)
```python
from arize.otel import register
tracer_provider = register(
    space_id=...,            # ARIZE_SPACE_ID
    api_key=...,             # ARIZE_API_KEY (ak-...)
    project_name="triage-bug-repro",
    endpoint=...,            # default Endpoint.ARIZE = "https://otlp.arize.com/v1" (gRPC)
    batch=True,              # default; we override to False (see Decision D2)
    set_global_tracer_provider=True,   # default; required so trace.get_tracer("triage") works
    auto_instrument=False,   # default; we pass True to auto-capture Anthropic spans
)
```
- `register()` signature confirmed by `inspect.signature` against the installed `arize-otel`.
- `auto_instrument=True` uses the installed `openinference-instrumentation-anthropic` (already a dep) — same mechanism Phoenix used. No explicit instrumentor call needed.
- Auth is sent as OTLP headers to `otlp.arize.com`; **no Phoenix env vars**.

### Read path (prior-run history)
```python
from arize import ArizeClient
client = ArizeClient(api_key=...)            # region defaults to US (api.arize.com)
df = client.spans.export_to_df(
    space_id=..., project_name="triage-bug-repro",
    start_time=..., end_time=..., where="<SQL-like filter>",
)
```
- In-process, explicit creds, returns a `pandas.DataFrame` — structurally parallel to the
  Phoenix adapter (`phoenix.client ... get_spans_dataframe`). Keeps the pure parser pattern.
- **AX export column shape may differ from Phoenix** (Phoenix nests attrs as dicts under
  `attributes.<x>`; AX may use flat dotted keys like `attributes.bug.detected`). The exact
  shape is **verified empirically against a real export** before writing the parser (Task R1).

### Eval write path (evaluators onto existing spans)
```python
client.spans.update_evaluations(
    space_id=..., project_name="triage-bug-repro",
    dataframe=...,   # context.span_id + eval.<name>.label/.score/.explanation columns
)   # -> WriteSpanEvaluationResponse, via Arrow Flight
```
- This writes first-class **`eval.<name>.*`** columns (the "Evaluations" surface in the AX
  UI — exactly what "see your evaluator" judging wants), keyed by `context.span_id`.
- Chosen over `client.spans.annotate()` because `annotate()` **404s if a span isn't found
  in the lookup window** — and AX's query index lags (see Risk R-LAG), so freshly-created
  spans can't be annotated immediately. `update_evaluations` is a Flight **write** keyed by
  span_id and does not depend on the lagging read index.

## Design decisions

- **D1 — One backend selector drives both write and read.** New config `trace_backend`
  (env `TRIAGE_TRACE_BACKEND`, default `"ax"`). `tracing/setup.py` (write) and
  `memory/history.py` (read) both honor it. Setting `TRIAGE_TRACE_BACKEND=phoenix` restores
  the old working Phoenix path — "Phoenix as fallback behind the same seam" (cheap, satisfied).
- **D2 — `batch=False` (SimpleSpanProcessor).** Phoenix used immediate-export semantics; the
  harness/booth scripts never call `force_flush`/`shutdown`. `batch=False` keeps spans
  exporting synchronously on `span.end()`, so **no exit-flush change is needed** and behavior
  matches Phoenix. (Avoids the classic "CLI exits before BatchSpanProcessor flushes" trap.)
- **D3 — In-process span-id capture for eval logging.** The Phoenix path queried span_ids
  back by `attempt.number` (`_phoenix_span_lookup`). AX cannot be queried back for fresh
  spans (R-LAG), so `RunTrace.attempt_span` records `{attempt_number: span_id_hex}` at span
  creation and the harness threads it into `run_eval(..., span_lookup=...)` (the param
  **already exists** — tests already inject it). Semantics match the old lookup (number→sid,
  last-wins on collision); we do **not** "fix" the known attempt.number collision (out of
  scope, protects the proven loop).
- **D4 — The LLM-judge engine stays on `phoenix.evals`.** `triage/eval/judges.py` and
  `score_attempts` use `phoenix.evals` (`create_classifier`, `evaluate_dataframe`, `LLM`) — a
  **local** judge library that never talks to Phoenix Cloud. It is not a trace backend, so it
  is **untouched**. Only the span *logging* (`_log_to_spans` / `_phoenix_span_lookup`) repoints.
- **D5 — Booth path (`run_manager.py`) is already Arize-decoupled** (judges only, no backend
  read/write). Only a stale "Phoenix" doc-comment changes there. Booth A/B behavior unchanged.

## Risks (flagged per the user's instruction)

- **R-LAG — AX query-index lag (6–12 h for time-range, 1–2 h for eval index).** Documented in
  the arize-trace/arize-evaluator skills. Implications:
  - **Write verification (Step 2)** uses **`--trace-id` lookup** (primary store, immediate) —
    not a time-range query — so it confirms ingestion without waiting on the index.
  - **Read-back (Step 3)** filters by issue over a time window → very recent runs (<~12 h) may
    not appear yet. This is acceptable for "prior-run" memory (prior runs are older) and is the
    same class of latency STATUS already calls out for Phoenix annotation read-back. Verified
    by exercising the live query + a trace-id spot-check; reported honestly if the window is empty.
  - **Eval write (Step 4)** uses `update_evaluations` (Flight write by span_id) precisely to
    avoid the index dependency that breaks `annotate()`.
- **R-AUTH — if `register`/export/update_evaluations returns 401/403**, STOP and report
  (user's explicit gate). The `pre-ax-migration` tag is the fallback.

## Out of scope

- Configuring AX **platform** evaluators/tasks (`ax evaluators create`...) — our judges run
  in-code; we log their results to spans. (Could be a later enhancement.)
- Fixing the `attempt.number` collision; any inner-loop/Band change.
- `scripts/phase7_eval.py` (offline re-score utility) — best-effort updated, not load-bearing.
