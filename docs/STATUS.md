# TRIAGE — Build Status & Phase 7.5 Handoff

_Last updated: 2026-06-21 · Phase 7 complete (Arize tracing + per-attempt evaluators + Claude synthesis + frontend, report contract reconciled). Next: **Phase 7.5 — the outer loop**._

> For the agent starting **Phase 7.5**. Read this, `TRIAGE_OVERVIEW.md`, and `TRIAGE_INTEGRATIONS.md` before touching code. The inner loop is proven and **must not regress** — 7.5 builds *on top of* it.

---

## ⛑️ FALLBACK FIRST — `pre-7.5-stable`

There is an annotated tag **`pre-7.5-stable`** on `017d850` (current `main` HEAD). It is the last known-good commit: inner loop proven, 120 tests green, tracing clean.

**If 7.5 destabilizes the loop and you run out of time:**
```bash
git reset --hard pre-7.5-stable      # back to a demoable inner loop
```
The inner loop alone clears the bounty bar. Do not delete this tag. Keep 7.5 work on `main`, tightly scoped, with a cut-path — if it isn't working, cut it and demo the inner loop.

---

## TL;DR

The **inner loop is closed and observable**. Three real agents coordinate in one Band room over @mentions: ParserAgent (GitHub issue → steps), ReproAgent (drives a real Browserbase browser), HypothesisAgent (diagnoses, routes `confirm`/`redirect_repro`/`redirect_parser`). On a redirect, ReproAgent spins a **fresh** Browserbase session and retries, bounded by a hard cap. The whole run is wrapped in **Arize Phoenix** spans; per-attempt **evaluators** score it; Claude **synthesizes** a report the frontend renders.

**Phase 7.5 is the OUTER loop:** feed the Arize evaluation of attempt _N_ back into the retry decision for attempt _N+1_ — so the system reads its own scored history and adjusts. Today the loop adjusts from the *raw repro evidence* (HypothesisAgent's diagnosis); 7.5 makes it also adjust from the *eval scores* that Arize holds. This is the "closing the outer loop" piece and the **riskiest remaining work** because it touches the proven loop.

---

## What's proven RIGHT NOW (the bulletproof core)

- **Forced fail→succeed runs clean.** `scripts/phase7_traced_run.py --force-retry`: attempt 1 (delete-only on empty list) → `BUG NOT REPRODUCED` → HypothesisAgent `redirect_parser` ("add tasks first") → ParserAgent revises → attempt 2 → `BUG REPRODUCED` (blank body + `TypeError ... reading 'name'`). Two distinct Browserbase sessions, honest `bug_detected` **false → true**.
- **Two differently-scored traces in Arize.** Per-attempt `repro_fidelity` differs (attempt 1 low / not_reproduced, attempt 2 high / reproduced) and lands on the two `repro_attempt` spans. Phoenix export is clean (0 errors) now that auth is fixed.
- **Canonical report renders end-to-end.** `backend/run_manager.py` (the booth path) serves the canonical `ReproReport`; the frontend `ReportCard` renders verdict, per-step ok/fail/crash, root-cause mechanism, eval scores, and Browserbase replay links. Verified live + via a real-data screenshot render.
- **Honest eval on both paths.** Root-cause judge scores the *real* diagnosis (verified 0.0→1.0 after the harness fix).
- **120 tests pass:** `.venv/bin/pytest`. 15 frontend tests + `tsc` clean: `cd frontend && npm test && npx tsc -b`.

⚠️ **One caveat for a pristine demo:** the most recent Arize trace pair was produced *before* the harness root-cause fix (`14425e3`), so its `root_cause_correctness` annotation reads 0.0 (the `repro_fidelity` contrast is honest). The fix is committed; **one fresh `--force-retry` run** will produce a trace pair where *both* evals are honest. Do that run before the booth if you want the Arize view spotless.

---

## Commits since Phase 6 (all on `main`)

| Commit | What |
|---|---|
| `9729b57` | Merge **phase7-arize**: Phoenix tracing, per-attempt evaluators, Claude synthesis |
| `91f0fc9` | Merge **phase7-frontend**: issue input, live log, report card + backend SSE |
| `f006098` | Reconcile frontend to the canonical Arize `ReproReport` (single source of truth) — backend wired to `synthesize_run`; placeholder report deleted |
| `14425e3` | Honest harness root-cause score (capture real diagnosis, not `""`) + sequential attempt numbering + `.env.example` Phoenix doc |
| `017d850` | gitignore `.triage_runs/` + `*.tsbuildinfo` ← **`pre-7.5-stable`** |

---

## Repo shape — what Phase 7 added

```
triage/
  tracing/
    setup.py            # setup_tracing(cfg) → phoenix.otel.register (env-driven, idempotent)
    run_context.py      # RunTrace + child/attempt spans; NullRunTrace no-op default
    artifacts.py        # RunArtifacts — per-run attempts.json + screenshots + report.json
  eval/
    judges.py           # LLM-as-judge classifiers (Anthropic) + pure input builders
    run_eval.py         # build_eval_dataframe, score_attempts, run_eval, _phoenix_span_lookup,
                        #   _log_to_spans  ← WRITES eval annotations onto repro_attempt spans
    code_checks.py      # honesty_check (deterministic dual-signal)
    ground_truth.py     # PLANTED_BUG.root_cause — root-cause judge reference
  synthesis/
    schema.py           # ReproReport dataclasses + REPORT_JSON_SCHEMA + validate_report
    synthesize.py       # build_synthesis_prompt, assemble_report, synthesize_run (Claude)
backend/
  server.py             # FastAPI: POST /api/runs, GET /api/runs/{id}/stream (SSE), snapshot
  run_manager.py        # RunRegistry._drive — composes the 3 agents (like phase6), taps Band
                        #   traffic into an SSE queue, then build_report_dict → ReproReport
frontend/               # Vite/React: UrlInput, LiveLog, BrowserView, ReportCard; types.ts = ReproReport
scripts/
  phase7_traced_run.py  # traced fail→succeed harness; --force-retry; attach_diagnosis_capture
  phase6_live_run.py    # Phase 6 harness (untouched)
```

The inner-loop modules (`parser_agent/`, `repro_agent/`, `hypothesis_agent/`, `shared/band.py`) are **unchanged in logic** — Phase 7 only threaded optional `run_trace=`/`artifacts=` params that default to no-ops.

---

## The TWO eval paths — read this before building 7.5

There are **two** ways eval scores are produced, and they behave differently. 7.5 hooks into the **read-back**, which doesn't exist yet.

1. **`backend/run_manager.py` (booth path).** Computes scores with the judges **only** (`build_eval_dataframe` + `score_attempts`), deliberately **decoupled from Phoenix span-logging** so the report still gets scores when Phoenix is down. It does **not** write to or read from Arize.
2. **`triage/eval/run_eval.py` (harness path).** `score_attempts` **and** `_log_to_spans` → it **writes** per-attempt annotations (`repro_fidelity`, `root_cause_correctness`, `honesty`) onto the live `repro_attempt` spans, correlating by the `attempt.number` span attribute via `_phoenix_span_lookup`. This is the **producer of the Arize eval data** 7.5 will read back.

**7.5's job:** after attempt _N_ is scored and logged to Arize, **read those annotations back** (query Phoenix for the prior `repro_attempt` span's scores, same lookup machinery) and feed them into the next retry — e.g. HypothesisAgent's redirect/tweak, or a gate that says "fidelity still low → adjust strategy / give up." The write-side infra exists; you are adding the **read-side + the decision**.

---

## Non-obvious things the 7.5 agent MUST know

1. **The fail→succeed is FORCED.** The real ParserAgent now infers the "add a task first" precondition on the first try, so a *natural* fail→succeed rarely happens. Always demo/test the outer loop with `--force-retry` (it injects delete-only steps that fail first). `run_manager` (the live booth backend) uses the real parser and **cannot force a retry** — decide early whether 7.5's outer loop lives in the harness, in `run_manager`, or both.
2. **Attempt-number correlation is booby-trapped.** `ReproLoopState.reset()` fires on a `redirect_parser` re-parse and **resets the attempt counter to 0**. So across a `redirect_parser`, two real attempts can both record `attempt.number = 1`. `synthesis.assemble_report` re-numbers sequentially for the report, but the **Arize spans still carry the duplicated `attempt.number`**. If 7.5 keys read-back on `attempt.number`, your span lookup can collide. Use a run-unique key (run id + monotonic counter), not `attempt.number` alone.
3. **Phoenix annotation read-back has latency.** Spans export immediately (SimpleSpanProcessor), but Phoenix's **annotation indexing can lag** — a score you just logged may not be queryable for a beat. A tight synchronous read-back-in-the-loop can race. Plan for poll-with-timeout or pass scores in-process rather than round-tripping Arize on the hot path (in-process is safer for the demo; the Arize round-trip is the "honest outer loop" story — weigh it).
4. **Phoenix auth is fixed but fragile.** Needs a **Phoenix Cloud JWT key** (`eyJ…`, NOT an Arize `ak-…` key) and a **space-scoped endpoint** `https://app.phoenix.arize.com/s/hanschundekad`. Both are in `.env` now; the gotcha is documented in `.env.example`. If read-back 401s, re-check these.
5. **`bug.detected` honesty is non-negotiable** (rule 8). The outer loop must keep the false→true flip real — never score or branch on a faked detection.
6. **Eval judges + synthesis cost real Anthropic calls and are guarded.** Both the harness and `run_manager` wrap eval/synthesis in `try/except` so they "never wedge the demo." Keep 7.5 guarded the same way: a read-back failure must degrade to the current inner-loop behavior, not hang or crash.
7. **Don't touch `triage/shared/band.py` or the inner-loop logic** (`loop.py`, `echo.py` routing, `reasoning.py` decision). If 7.5 seems to need a change there, stop and reconsider — that's the line that protects `pre-7.5-stable`.

---

## How to run / verify

```bash
# inner loop + tracing + eval + synthesis (the proven core); forces fail→succeed
.venv/bin/python scripts/phase7_traced_run.py --force-retry

# booth path end-to-end (real parser, single live run) — backend serves the report over SSE
.venv/bin/python -m uvicorn backend.server:app   # then POST a GitHub issue URL to /api/runs

# tests
.venv/bin/pytest                       # 120 Python
cd frontend && npm test && npx tsc -b  # 15 frontend + typecheck
```

Required `.env` (all present locally; keep `.env.example` in sync): Band ×3 identities, `ANTHROPIC_API_KEY`, `BROWSERBASE_*`, `TRIAGE_GITHUB_ISSUE_URL`, `TRIAGE_APP_URL`, `PHOENIX_API_KEY` (JWT), `PHOENIX_COLLECTOR_ENDPOINT` (`…/s/hanschundekad`).

---

## Hard rules (carry forward — unchanged)

1. Agent names: `ParserAgent`, `ReproAgent`, `HypothesisAgent` only.
2. Every `send_message` needs ≥1 `@mention`. `send_message` = directed talk; `send_event` = logs; never mixed.
3. All browser/Stagehand work stays in `triage/repro_agent/`.
4. New Browserbase session per retry — never reuse `session_id`.
5. Verify SDK details against live docs before integration code; flag drift.
6. `bug.detected` must be honest — the fail→succeed flip must be real.
7. Do **not** modify `triage/shared/band.py`.
8. **Do not start 7.5 on a shaky core.** Confirm a clean `--force-retry` run + two differently-scored traces first (see the caveat above). If shaky, harden before building.
