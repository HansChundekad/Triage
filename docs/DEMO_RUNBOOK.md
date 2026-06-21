# TRIAGE — Demo Runbook

Everything for the booth. Test-script demo, native surfaces, no in-app UI.

---

## 0. Pre-demo checklist (do once, before judges arrive)

- [ ] Terminal open at `/Users/hanschundekad/Triage`.
- [ ] Browser logged into **browserbase.com**.
- [ ] **Band web app** open at app.band.ai → room **`741d69f0-006d-436a-9d45-cc43b88cbc75`** (pinned; all 3 agents are participants). All demo runs stream into this one room.
- [ ] **Arize AX** open (project `triage-bug-repro`). Have the deep link (§4) ready.
- [ ] (Optional) `cd frontend && npm run dev` running, for the report-card surface.
- [ ] **Pre-seed the outer loop:** do one `./scripts/demo.sh` run ~10+ min before showing the "Arize makes it smarter" story, so AX has the history indexed. (Memory already returns a real hint from 4 prior runs — verified — so this is belt-and-suspenders.)

Sanity check the memory feed is live:
```bash
TRIAGE_OUTER_LOOP=1 .venv/bin/python -c "from dotenv import load_dotenv; load_dotenv(); from triage.config import load_config; from triage.memory import load_learned_context; print(load_learned_context(load_config()))"
```
Expect a `Prior-run memory: across N past run(s)…` line.

---

## 1. Commands

| # | Purpose | Command |
|---|---|---|
| **A** | **Main demo** — deterministic fail→succeed (hero) | `./scripts/demo.sh` |
| **B** | **"Arize makes it smarter"** — reads memory, first-try success | `TRIAGE_OUTER_LOOP=1 .venv/bin/python scripts/phase7_traced_run.py` |
| **C** | **Report card** surface | `cd frontend && npm run dev` → open URL → click **Demo** |

Both A and B use the hardcoded GitHub issue (`…/StrideAI/issues/1`). No UI input.

---

## 2. Run of show (Demo A — the hero)

1. **Run `./scripts/demo.sh`.** Say: *"A real GitHub bug report is handed to three coordinating agents."*
2. **💬 Band room** (or terminal `💬` stream): ParserAgent → ReproAgent → "attempt 1 failed" → HypothesisAgent diagnoses → `redirect_parser` → ParserAgent re-parses → retry. *"Three distinct agents coordinating over @mentions in a real room."*
3. **🌐 Browserbase**: two tabs auto-open — attempt 1 (browser blanks/fails), attempt 2 (browser succeeds). *"It drives a real cloud browser, not a mock."*
4. **Terminal RUN SUMMARY**: `verdict: REPRODUCED ✅`, honest `bug.detected flip: False → True`, both session URLs.
5. **📋 Report card** (frontend Demo button): synthesized root cause — verdict, per-step ok/fail/crash, mechanism, eval scores.
6. **📊 Arize** (§3–4): walk the trace.

Run takes ~1–3 min.

---

## 3. What's in the Arize trace (the walkthrough)

- **One `triage_run` → two `repro_attempt` spans** (the inner-loop retry, captured).
- Expand each → `browser_execution` → `stagehand_action` per step (4 on attempt 1, 8 on attempt 2).
- **Evaluations: `repro_fidelity` = not_reproduced (0)** on attempt 1 vs **reproduced (1)** on attempt 2 — LLM-judge scores, honestly different. Plus `root_cause_correctness`, `honesty`.

---

## 4. Arize deep link (use this — the trace LIST lags)

The list/time-range view is backed by a lagging index; `selectedTraceId` loads from the primary store and resolves immediately. After a run, copy the new `trace_id` from the terminal RUN SUMMARY and paste it into `selectedTraceId=`:

```
https://app.arize.com/organizations/QWNjb3VudE9yZ2FuaXphdGlvbjo0NDcyMzorREpl/spaces/U3BhY2U6NDcyNzY6OWkzSg==/projects/TW9kZWw6ODQ3NTgzNzc4Mjp0TUZO?selectedTraceId=<TRACE_ID>&queryFilterA=&selectedTab=llmTracing&timeZoneA=America%2FLos_Angeles&startA=1782000000000&endA=1782086400000&envA=tracing&modelType=generative_llm
```

This morning's verified hero trace (`selectedTraceId=9973ee54ef1d0fdfad58cb63fb4bdb80`) is good to show as-is.

Verify any trace from the CLI (2 spans + 2 distinct evals):
```bash
export ARIZE_SPACE="$(.venv/bin/python -c 'from dotenv import load_dotenv; load_dotenv(); from triage.config import load_config; print(load_config().arize_space_id)')"
.venv/bin/ax spans export triage-bug-repro --space "$ARIZE_SPACE" --trace-id <TRACE_ID> --stdout
```

---

## 5. The "Arize improves the loop" story (Demo B)

**Two loops — say this distinction out loud, it's the differentiator:**
- **Inner loop (one run):** fail → diagnose → redirect → retry → succeed. Arize *records* it.
- **Outer loop (across runs):** eval scores + diagnoses live in Arize. Next run of the same bug, the system **reads its own scored history back out of Arize**, distills a lesson, and starts smarter. Arize is **memory**, not a log sink.

**Show it:**
1. Run `TRIAGE_OUTER_LOOP=1 .venv/bin/python scripts/phase7_traced_run.py`.
2. The Band room immediately shows **`🧠 Prior-run memory: across N past runs… establish preconditions before the failing action`** — derived from real Arize traces.
3. That hint shapes attempt 1 → reproduces **first try** (one `repro_attempt`, no retry).

**The pitch:** *"Same bug. Last time it took a retry to learn the precondition. This time it read that lesson out of Arize and got it first try."*

The **always-true artifact is the `🧠` memory line** (verified to load in ~3.7s from 4 prior runs). Anchor on that — it's Arize feeding the loop, visible regardless of how attempt 1 lands.

---

## 6. Honesty notes (don't get caught out)

- **Demo A is deliberately staged to fail first.** `--force-retry` feeds ParserAgent intentionally-incomplete steps to *guarantee* a visible retry. The **diagnosis and bug detection are real** (rule 8) — only the first-attempt steps are crippled. Say exactly that if asked: a staging device to make the retry legible, not a faked result.
- **Demo B uses the real parser + real Arize read** — not forced, so slightly less deterministic than A. Anchor on the `🧠` memory line, which always shows.

---

## 7. Smart-talking points

- **Honest eval:** "`bug.detected` flips for real; the judge scores `repro_fidelity` 0→1 *because* the browser actually went blank→reproduced."
- **Native surfaces, deliberately not embedded:** "Browserbase, Band, and Arize on their own platforms — more verifiable for you than an iframe we control."
- **Three real, distinct agent identities** over @mentions — not one model role-playing three.
- **Arize as a feedback loop**, not a logger — the outer-loop memory is the moat.
- **Telemetry depth (deep cut):** "A redirect re-parse made both attempts collide on `attempt.number`, so only one got scored — we re-keyed spans on a run-unique id so both score independently." Show the two-span/two-score trace.
- **Fail-soft everywhere:** eval/synthesis/memory are guarded — a flaky judge or lagging index degrades to the proven inner loop; never wedges a run.

---

## 8. Troubleshooting / fallback

| Symptom | Fix |
|---|---|
| New trace not in AX **list** | Index lag — open by `selectedTraceId` (§4). It's there. |
| Browserbase tab didn't auto-open | URL still prints in terminal; or keep the Browserbase **Sessions** list open and click the running session. |
| Band room looks stale | Scroll to the **bottom** (runs accumulate in the pinned room). Or watch the terminal `💬` stream. |
| Live session flakes at booth | Use a prior clean run's trace + replay URLs as the fallback recording. |
| Run B doesn't reproduce first try | The `🧠` memory line still shows — pivot to that (it's the real point). |

---

## 9. Health (as of this runbook)

- `.venv/bin/pytest` → **172 passed**.
- Frontend: `cd frontend && npx tsc -b` clean, `npm test` → 15 passed.
- Demo A verified live end-to-end: fail→succeed, AX trace `9973ee54…` has 2 `repro_attempt` spans + 2 distinct eval scores.
- Outer-loop memory verified: returns a real hint from 4 prior AX runs in ~3.7s.
- **Open:** Task 4 (3–4 back-to-back determinism runs) — run 1 clean; not yet repeated.
