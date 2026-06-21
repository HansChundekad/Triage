# Phase 7 — Arize Phoenix: tracing + evaluator + Claude synthesis

_Design spec · 2026-06-20 · worktree `phase7-arize` · branch `phase7-arize`_

> **Status:** approved design, pre-implementation. Next step after user review: `writing-plans`.

---

## 1. Goal & judging context

Phase 7 wraps the **real, already-closed retry loop** (Phase 6) in Arize Phoenix so the
fail→adjust→succeed progression is visible, scored, and synthesized into a report the
frontend renders. Three deliverables:

1. **Tracing** with per-step child spans — a trace a judge reads as a visual story.
2. **A Phoenix evaluator** — LLM-as-judge + a code check, scored **per attempt**, with
   results logged **onto the spans** so the improvement shows on-screen.
3. **Claude synthesis** — captured run artifacts → a structured `ReproReport` for the frontend.

**Who judges this and how:** Arize judges in person at their booth, clicking through our
**Phoenix Cloud environment** (`app.phoenix.arize.com`). The Phoenix environment itself is
the deliverable. They want three things visible: traces, an evaluator, and evidence we used
it to improve the app. Build for a technical judge clicking through and asking questions.

**Non-negotiables carried from the repo (CLAUDE.md / STATUS.md / INTEGRATIONS §4):**

- Trace the **real** retry loop on main — do not mock it.
- `bug.detected` must be **honest** — the fail→succeed flip has to be real (it already is:
  Phase 6 `--force-retry` flips `False→True` for real reasons).
- **Do not modify** `triage/shared/band.py` or agent *logic* beyond adding instrumentation.
- Verify SDK details against live docs before integration code; flag drift (done — §2).

---

## 2. Verified APIs & drift (live docs, 2026-06-20)

Verified against current Phoenix docs/PyPI before designing. Flags:

| # | Finding | Decision |
|---|---|---|
| 1 | Integrations doc calls Arize "§4"; the user prompt said "§3" (§3 is Band). | Used §4. |
| 2 | `phoenix.evals` rewrote its API. Current **3.1.0** uses `create_classifier(...)` + `LLM(...)` + `evaluate_dataframe(...)`. The legacy `llm_classify`/`rails` pattern implied by INTEGRATIONS §4 is **old**. | Build on the **modern** API. |
| 3 | Logging evals to spans changed. Modern: `phoenix.client.Client().spans.log_span_annotations_dataframe(df, annotation_name=..., annotator_kind="LLM")`, env-driven. Legacy `px.Client().log_evaluations(SpanEvaluations(...))` still exists but is the old path. | Use the **modern** `phoenix.client` path. |
| 4 | `register(project_name=..., auto_instrument=True)` confirmed. Anthropic spans require **`openinference-instrumentation-anthropic`** installed (auto_instrument loads installed instrumentors; it is not free). | Add the dep. |
| 5 | The REST eval-logging client reads `PHOENIX_BASE_URL` + `PHOENIX_API_KEY`; OTLP trace export reads `PHOENIX_COLLECTOR_ENDPOINT`. Both point at `app.phoenix.arize.com`. | Set both env vars. |

**To pin at implementation time** (docs underspecified — install the package and introspect
**before** relying on it; flag if reality differs):

- Exact column names returned by `evaluate_dataframe` (expected: label, score, explanation).
- Whether `openinference-instrumentation-anthropic` cleanly captures our `messages.create(...)`
  calls that use `output_config` (structured output) + `thinking={"type":"adaptive"}`.
- Whether `phoenix.evals` ships an Anthropic adapter for `LLM(...)`. If not, fall back to
  the LiteLLM adapter pointing at Anthropic (`anthropic/claude-sonnet-4-6`). **Flag the choice.**

Sources: arize-phoenix-evals (PyPI); Phoenix Evals Reference (readthedocs); Phoenix "Log
Evaluation Results" docs; Phoenix Python tracing quickstart.

---

## 3. The hard problem this design solves

The trace tree we want — `repro_attempt` parent → per-Stagehand-action children, with the
Hypothesis Claude call and the retry progression all under **one legible root** — spans
**multiple async Band callbacks across three agents**. The per-step children inside
`run_repro` nest cleanly (one synchronous call stack). But `diagnose()` and `extract_steps()`
fire in **separate** message callbacks, so OpenTelemetry's implicit current-span context will
**not** link them into one tree.

**Solution:** a run-level `RunTrace` object holds the root span and its OTEL context; every
callback creates its spans with an **explicit parent context** read from `RunTrace` (not the
implicit current span). This is instrumentation only — it does **not** thread span IDs through
Band payloads and does **not** touch `shared/band.py` or agent logic.

**Scope boundary (flagged):** cross-**process** trace propagation (W3C `traceparent` over Band)
is **out of scope**. The real demo run is **single-process** (`scripts/phase7_traced_run.py`
composes all three real callbacks, exactly like `phase6_live_run.py`), so a single in-process
root context is honest — it is how the demo actually runs, not a shortcut around a real loop.

---

## 4. Architecture

### 4.0 Shared substrate — new package `triage/tracing/`

> New package. **Not** `triage/shared/band.py` (untouched). All optional/no-op by default so
> existing tests and `phase6_live_run.py` are unaffected.

- **`setup.py` → `setup_tracing(cfg) -> TracerProvider`**
  Calls `phoenix.otel.register(project_name="triage-bug-repro", auto_instrument=True)` after
  ensuring `PHOENIX_COLLECTOR_ENDPOINT` / `PHOENIX_API_KEY` are set from `cfg`. Idempotent
  (guards against double registration). Returns the provider + a `trace.get_tracer("triage")`.

- **`run_context.py` → `RunTrace`**
  Holds the root `triage_run` span and its `opentelemetry.context.Context`. Methods:
  - `attempt_span(number) -> ContextManager[Span]` — child of root, named `repro_attempt`.
  - `child_span(name, parent) -> ContextManager[Span]` — explicit-parent child (e.g.
    `browser_execution`, `bug_detection`, `stagehand_action`).
  - `claude_span(name, attempt_number=None) -> ContextManager[Span]` — parents an
    auto-instrumented Claude call under root, tagged with `attempt.number` for visual ordering.
  - A **`NullRunTrace`** with the same interface whose context managers are no-ops, used when
    tracing is disabled (default for unit tests and phase6).

- **`artifacts.py` → `RunArtifacts`**
  A per-run directory (`./.triage_runs/<timestamp>/`). Stores:
  - `screenshots/attempt{N}_step{M}.png` — written from the base64 PNGs `run_repro` already
    captures (currently discarded). The span's `screenshot.ref` is the relative path.
  - `attempts.json` — append-only list of `{attempt, steps, evidence, console_errors,
    session_url, bug_detected, body_snippet}`. This is the **bridge to synthesis** (since
    `ReproResultPayload` cannot carry screenshots and shared is untouched).
  - `report.json` — written by synthesis (§4.3).
  Also a `NullRunArtifacts` no-op for the untraced/test path.

### 4.1 Component ① — Tracing & instrumentation

New runner **`scripts/phase7_traced_run.py`** (mirrors `phase6_live_run.py`, leaves it intact):

1. `setup_tracing(cfg)`, open root `triage_run` span → build `RunTrace` + `RunArtifacts`.
2. Compose the three **real** callbacks, threading `run_trace`/`artifacts` via new **optional**
   params (`make_repro_callback(cfg, state, run_trace=None, artifacts=None)`, etc.). Default
   `None` → `NullRunTrace`/`NullRunArtifacts`, so phase6 and tests are unchanged.
3. Run the real loop to a terminal state, then **run the evaluator inline** (§4.2) and
   **synthesis** (§4.3) before closing the root span.

Instrumentation added (logic untouched — only spans/attributes/artifact writes):

- **`echo._run_attempt`** → `run_trace.attempt_span(state.attempts)`:
  attributes `attempt.number`, `github.issue_url`, `app.url`, `browserbase.session_url`,
  and **`bug.detected` set straight from `result.success`** (honest by construction). Wraps
  `browser_execution` (the `run_repro` call) and a `bug_detection` child. Writes the attempt
  record to `RunArtifacts`.
- **`browser.run_repro`** → one `stagehand_action` child span **per step** (parented under the
  attempt's `browser_execution`): `step.index`, `step.text`, `action.success`,
  `screenshot.ref`, `console.error` (the captured string when present). The crash step shows
  `action.success=...`, the blank body, and the `Cannot read properties of undefined` console
  error — the "step1 OK → step4 CRASH" visual. Screenshots persisted via `RunArtifacts`.
- **Parser `extract_steps`** and **Hypothesis `diagnose`** → wrapped in `run_trace.claude_span(...)`
  so the auto-instrumented Claude span nests under root with `attempt.number`. Tree reads:
  `parse → attempt#1 → hypothesis(redirect) → reparse → attempt#2 → hypothesis(confirm) → synthesis`.

Honest flip: `bug.detected` comes only from `detect_bug` (dual-signal). Nothing faked.

### 4.2 Component ② — Phoenix evaluator (`triage/eval/`)

Run **inline at the end of `phase7_traced_run.py`**, scored **per attempt**.

- **`ground_truth.py`** — the planted-bug fixture (single source of truth for the judges):
  expected user-visible symptom (blank screen on deleting the last task), expected console
  fingerprint (`Cannot read properties of undefined`), and a plain-English root-cause
  statement (reads `items[0]`/length after the array is emptied by the final delete). Used by
  the root-cause judge as ground truth; deliberately **not** shown to the agents.

- **`judges.py`** — two `create_classifier` LLM judges:
  - **repro_fidelity**: inputs = issue text + the attempt's evidence (verdict, console errors,
    body snippet). Choices `{reproduced: 1.0, inconclusive: 0.5, not_reproduced: 0.0}`.
    Question: did *this attempt* genuinely reproduce the **reported** bug (not just any error)?
  - **root_cause_correctness**: inputs = issue + `ground_truth` root cause + the Hypothesis
    `root_cause`. Choices `{correct: 1.0, partially_correct: 0.5, incorrect: 0.0}`.
  - Judge LLM: prefer the `phoenix.evals` Anthropic adapter (`claude-sonnet-4-6`); if the
    package lacks one, use the LiteLLM adapter → Anthropic. **Decision flagged at build time.**

- **`code_checks.py`** — deterministic honesty eval (pure function, no LLM):
  `honest = bug_detected == (blank_body AND console_match)`. Defends rule #8 directly and gives
  the "we also run code-based evals" story. Score `1.0`/`0.0` + explanation.

- **`run_eval.py`** —
  1. Pull the run's `repro_attempt` spans from Phoenix (`phoenix.client`), one row per attempt.
  2. Build the judge input dataframe; `evaluate_dataframe([repro_fidelity, root_cause_correctness])`.
  3. Run `code_checks` per attempt.
  4. `client.spans.log_span_annotations_dataframe(df_keyed_by_span_id, annotation_name=...,
     annotator_kind="LLM"/"CODE")` so scores attach **to each attempt span**.
  Result in the UI: attempt 1 `repro_fidelity=not_reproduced(0.0)` → attempt 2
  `reproduced(1.0)`. The on-screen flip is the **"used Arize to measure improvement"** artifact.

  Also exposed as standalone `scripts/phase7_eval.py` to re-score an existing project run.

### 4.3 Component ③ — Claude synthesis (`triage/synthesis/`)

- **`schema.py`** — the frontend contract. `ReproReport` dataclass + a published **JSON Schema**
  file (`docs/superpowers/specs/phase7-report.schema.json`) the parallel frontend codes against:

  ```jsonc
  {
    "issue":       { "url": "...", "title": "...", "summary": "..." },
    "verdict":     "reproduced | not_reproduced",
    "repro_steps": [ { "n": 1, "action": "...", "status": "ok|fail|crash", "screenshot_ref": "..." } ],
    "root_cause":  { "hypothesis": "...", "mechanism": "...", "confidence": "high|medium|low" },
    "evidence":    { "console_error": "...", "blank_screen": true, "body_snippet": "..." },
    "attempts":    [ { "number": 1, "session_replay_url": "...", "bug_detected": false } ],
    "eval_scores": { "repro_fidelity": 1.0, "root_cause_correctness": 1.0 },   // optional
    "generated_at": "ISO-8601"
  }
  ```

- **`synthesize.py`** — Claude structured output (same `output_config` json_schema +
  `thinking=adaptive` pattern as parser/hypothesis; Anthropic client injected for testability)
  over `RunArtifacts` (steps, evidence, screenshot refs, console error, replay URLs, hypothesis
  root cause) → a validated `ReproReport`, written to `report.json`. Wrapped in a `synthesis` span.

---

## 5. Testing (TDD per CLAUDE.md — failing test first)

- **Tracing**: `InMemorySpanExporter` — assert the tree nests (`triage_run` → `repro_attempt`
  → `browser_execution` → `stagehand_action`×N), and that `bug.detected` is set from
  `detect_bug` (inject a fake browser; no live session). `RunTrace`/`NullRunTrace` parity test.
- **Evaluator**: pure-function test for `code_checks` honesty; judge **input-builder** tests with
  the LLM mocked; ground-truth fixture shape test. One optional live judge smoke (not in CI).
- **Synthesis**: `ReproReport` schema validation; `synthesize()` with a fake Claude client
  returning canned JSON → valid report; round-trips against the published JSON Schema.
- **Regression**: the 84 existing tests stay green (all new params default to no-op).

---

## 6. Delegation (Sonnet subagents — never Haiku, per project memory)

Dependency-ordered:

1. **A — substrate + tracing instrumentation** (foundational; B and C depend on `RunArtifacts`
   + span names). Built first.
2. **B — evaluator** and **C — synthesis** run as **two parallel Sonnet subagents** once A lands.

I personally own: live-API verification (done; remaining pins in §2), the cross-agent nesting
(§3), the frontend report schema (§4.3), dependency/install decisions, and the review gates.

---

## 7. Dependencies & env

- pyproject adds: `arize-phoenix`, `arize-phoenix-evals`, `arize-phoenix-client`,
  `openinference-instrumentation-anthropic`, `opentelemetry-sdk`.
  (Confirm exact package split at install — `phoenix.client` may live in `arize-phoenix-client`
  or `arize-phoenix`; pin once installed.)
- `.env.example` + `triage/config.py` gain `PHOENIX_BASE_URL` (REST eval client), alongside the
  existing `PHOENIX_API_KEY` / `PHOENIX_COLLECTOR_ENDPOINT`. Update the config test in the same
  change (CLAUDE.md convention). `PHOENIX_BASE_URL` defaults to `app.phoenix.arize.com`.

---

## 8. Out of scope (explicit)

- Cross-**process** trace propagation over Band (demo is single-process — §3).
- Any change to `triage/shared/band.py`, `ReproResultPayload`, or agent decision logic.
- A second planted bug. Frontend rendering (consumes `report.json` / the JSON Schema).
