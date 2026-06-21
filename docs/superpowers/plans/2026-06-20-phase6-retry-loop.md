# Phase 6 — Close the Retry Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make TRIAGE's coordination real — ReproAgent consumes ParserAgent's live steps, and a `redirect_repro` from HypothesisAgent spins a *fresh* Browserbase session and retries, with a hard cap that guarantees the loop always terminates.

**Architecture:** All loop *decision* logic (parse steps, classify an incoming message, track attempts, decide terminal) lives in a new pure module `triage/repro_agent/loop.py` — no browser, no Band, no network, fully unit-testable. `browser.py` (Browserbase/Stagehand) gains a `steps`/`tweak` parameter but stays the only place browser work happens. `echo.py` (Band glue) wires the two together via a stateful callback factory, mirroring the existing `make_diagnosis_callback` pattern in `hypothesis_agent/agent.py`. The shared Band module `triage/shared/band.py` is **not touched**.

**Tech Stack:** Python 3.11+ (dev on 3.14), `stagehand` v3.21.0 + `playwright` (CDP) for the browser, `band-sdk` via the shared `BandAgent`, `pytest` for TDD.

## Global Constraints

Copied verbatim from the Phase 6 brief and the non-negotiable rules:

- All browser/Stagehand work lives in **ReproAgent only**.
- **New Browserbase session per attempt — never reuse `sessionId`.** (`run_repro` already creates a new session every call; each retry is a fresh `run_repro` call.)
- **Do not modify the shared Band module** (`triage/shared/band.py`). If it looks like it needs changing — STOP and report.
- Every cross-agent Band message must **@mention** a recipient. Redirects route via @mention.
- Band **events** = logs (failed attempt, progress); Band **messages** = directed @mention talk (results, give-up).
- Agent names exact: `ParserAgent` / `ReproAgent` / `HypothesisAgent`.
- Keep each attempt's session replay URL (Phase 7 embeds them and traces the progression).
- TDD for real logic — write the failing test first. Per-task commits, scoped messages.
- The retry loop must **NEVER spin indefinitely**, even if HypothesisAgent keeps redirecting.

---

## File Structure

- `triage/repro_agent/loop.py` *(new)* — pure loop logic. One responsibility: turn raw Band message text + sender identity + accumulated state into a decision. Exports `parse_steps`, `classify_message`, `is_confirm`, `extract_tweak`, `ReproLoopState`, `format_giveup_message`, and the tunable `MAX_REPRO_ATTEMPTS`. No imports from `browser.py`, `echo.py`, or `band` — keeps it trivially testable and import-cycle-free.
- `triage/repro_agent/browser.py` *(modify)* — `run_repro(cfg, steps, tweak=None)`; delete hardcoded `_STEPS`; per-step execution now driven by the passed natural-language steps.
- `triage/repro_agent/echo.py` *(modify)* — replace the single `handle_parser_message` function with a stateful `make_repro_callback(cfg, state=None)` factory + `_run_attempt(...)` helper; wire it into `run()`.
- `tests/test_repro_loop.py` *(new)* — unit tests for every pure function in `loop.py`.
- `tests/test_repro_echo.py` *(modify)* — rewrite handler tests against the new factory/state model.
- `tests/test_repro_browser.py` *(unchanged)* — `detect_bug` tests still valid.

### Cross-agent text contract (read before coding Task 2)

ReproAgent only ever receives Band messages it is **@mentioned** in. From HypothesisAgent that means exactly two shapes (see `hypothesis_agent/agent.py::format_diagnosis_message`, which we do **not** change):

- **confirm:** `"{handle} confirmed, matches the report. Root cause: {root_cause}. Repro valid."`
- **redirect_repro:** `"{handle} {redirect_instruction} (suspected cause: {root_cause})"`

(`redirect_parser` is @mentioned at ParserAgent, so it never reaches ReproAgent.)

Because Band messages carry **plain text only** (the structured `HypothesisPayload` is *not* on the wire), ReproAgent must classify confirm-vs-redirect from this text. `is_confirm` keys on the confirm markers above. This is a deliberate coupling to HypothesisAgent's wording — centralized in `loop.py` with a comment pointing back to `format_diagnosis_message`.

**Why this is still safe:** classification can be wrong without ever causing an infinite loop. A confirm misread as a redirect wastes at most the remaining capped attempts; a redirect misread as a confirm stops early. The attempt cap + terminal latch (Task 3) bound termination **independently of text-parsing correctness** — ReproAgent counts its own browser runs and refuses past the cap. That is the ultimate backstop.

---

## Task 1: Consume real Parser steps (Parser→Repro fully live)

Make ReproAgent parse ParserAgent's numbered-line block and drive the browser with those real steps instead of the hardcoded `_STEPS`. Redirect handling is still out of scope here (Hypothesis messages stay ignored, exactly as today). Deliverable: a clean live end-to-end run — real issue → real steps → real browser.

**Files:**
- Create: `triage/repro_agent/loop.py`
- Modify: `triage/repro_agent/browser.py:74-100` (delete `_STEPS`), `triage/repro_agent/browser.py:108-261` (`run_repro` signature + step loop)
- Modify: `triage/repro_agent/echo.py:43-80` (`handle_parser_message`)
- Test: `tests/test_repro_loop.py` (new), `tests/test_repro_echo.py` (update)

**Interfaces:**
- Produces: `parse_steps(content: str) -> list[str]` — extracts the natural-language step strings from a Parser message (lines matching `^\s*\d+\.\s+(.+)$`); returns `[]` when none found.
- Produces: `run_repro(cfg: Config, steps: list[str], tweak: str | None = None) -> ReproResultPayload` — drives the browser through `steps`; `tweak` (used in Task 2) appends retry guidance to each act instruction.
- Consumes: `ReproResultPayload` (unchanged), `format_result_message` (unchanged).

- [ ] **Step 1: Write the failing test for `parse_steps`**

Create `tests/test_repro_loop.py`:

```python
from triage.repro_agent.loop import parse_steps

# Mirrors ParserAgent.format_steps_message output exactly.
_PARSER_MSG = (
    "@ReproAgent repro steps for https://github.com/x/y/issues/1:\n"
    "1. Click the task text input field to focus it\n"
    "2. Type 'test task' into the input\n"
    "3. Click the Add button\n"
    "4. Click the Delete button, then confirm"
)


def test_parse_steps_extracts_numbered_lines():
    steps = parse_steps(_PARSER_MSG)
    assert steps == [
        "Click the task text input field to focus it",
        "Type 'test task' into the input",
        "Click the Add button",
        "Click the Delete button, then confirm",
    ]


def test_parse_steps_ignores_header_and_blanks():
    steps = parse_steps("@ReproAgent repro steps for url:\n\n1. only step\n")
    assert steps == ["only step"]


def test_parse_steps_returns_empty_when_no_numbered_lines():
    assert parse_steps("@ReproAgent please retry the delete more slowly") == []


def test_parse_steps_tolerates_leading_whitespace():
    assert parse_steps("   2.   indented step  ") == ["indented step"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_repro_loop.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'triage.repro_agent.loop'`

- [ ] **Step 3: Create `loop.py` with `parse_steps`**

Create `triage/repro_agent/loop.py`:

```python
"""ReproAgent retry-loop logic — pure, unit-testable, no browser/Band/network.

This module decides WHAT to do with an incoming Band message (parse steps,
retry, confirm, ignore) and tracks loop state. Browser work stays in
browser.py; Band I/O stays in echo.py. Keeping the decisions here means the
loop-safety guarantees are testable without a live session.
"""
from __future__ import annotations

import re

# One numbered step per line, e.g. "1. Click the Add button". Matches the
# block ParserAgent emits in format_steps_message (parser_agent/agent.py).
_STEP_LINE = re.compile(r"^\s*\d+\.\s+(.+?)\s*$")


def parse_steps(content: str) -> list[str]:
    """Extract natural-language repro steps from a ParserAgent message.

    Returns one string per numbered line, in order. Returns [] when the
    message has no numbered lines (e.g. a free-text redirect).
    """
    steps: list[str] = []
    for line in content.splitlines():
        match = _STEP_LINE.match(line)
        if match:
            steps.append(match.group(1).strip())
    return steps
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_repro_loop.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Change `run_repro` to take real steps; delete `_STEPS`**

In `triage/repro_agent/browser.py`, **delete** the entire `_STEPS` block (lines 69-100, the comment header through the closing `]`).

Change the signature (line 108) and the step loop (lines 174-199). New signature:

```python
async def run_repro(cfg: "Config", steps: list[str], tweak: str | None = None) -> ReproResultPayload:
    """Open a fresh Browserbase session, execute `steps`, return evidence.

    `steps` are natural-language instructions from ParserAgent (one Stagehand
    observe+act per step). `tweak`, when set, is retry guidance from
    HypothesisAgent appended to each act instruction (Task 2).

    A new Browserbase session is created every call — never reused (§2.4).
    """
```

Replace the `for step_label, observe_instr, act_instr in _STEPS:` loop header and its observe/act body (lines 175-199) with:

```python
            # --- 4. Execute repro steps: observe → act → screenshot ---
            for index, step in enumerate(steps, start=1):
                step_label = f"step {index}: {step[:48]}"
                act_instr = step if not tweak else f"{step}. Adjustment for this retry: {tweak}"
                logger.info("[ReproAgent] %s", step_label)

                obs = await session.observe(instruction=step)
                found = obs.data.result
                if not found:
                    msg = f"{step_label}: observe found no elements for: {step!r}"
                    logger.warning("[ReproAgent] %s", msg)
                    evidence.append(f"WARN — {msg}")
                else:
                    evidence.append(f"{step_label}: found {len(found)} element(s)")

                act_result = await session.act(input=act_instr)
                act_ok = act_result.data.result.success
                act_msg = act_result.data.result.message
                evidence.append(
                    f"{step_label} act: {'OK' if act_ok else 'FAIL'} — {act_msg}"
                )
                logger.info(
                    "[ReproAgent] act '%s': %s — %s",
                    step_label,
                    "OK" if act_ok else "FAIL",
                    act_msg,
                )
```

The screenshot block immediately after (the `await asyncio.sleep(0.5)` … screenshot `try/except`) stays, but update its label references from `step_label` (still valid) — no change needed since `step_label` is still in scope.

- [ ] **Step 6: Update the Task-1 handler to parse steps and pass them**

In `triage/repro_agent/echo.py`, update `handle_parser_message` (lines 43-80). Keep it a plain function for Task 1 (the factory refactor is Task 2). Add the import at top:

```python
from triage.repro_agent.loop import parse_steps
```

Replace the body of `handle_parser_message` from the `print("[ReproAgent] launching…")` line through the `run_repro(cfg)` call so steps are parsed and passed:

```python
    if _sender_is_hypothesis(sender):
        print("[ReproAgent] sender is HypothesisAgent — ignoring (retry logic is Task 2).")
        return

    steps = parse_steps(payload.content)
    if not steps:
        print("[ReproAgent] no numbered steps in message — ignoring.")
        return

    print(f"[ReproAgent] parsed {len(steps)} steps — launching real Browserbase session…")
    cfg = load_config()

    await agent.send_event("Starting Browserbase repro session", "task")

    try:
        result = await run_repro(cfg, steps)
    except Exception as exc:  # noqa: BLE001
        logger.error("[ReproAgent] browser execution failed: %s", exc)
        await agent.send_event(f"Browser execution error: {exc}", "error")
        result = ReproResultPayload(
            success=False,
            evidence=[f"Execution error: {exc}"],
            console_errors=[],
            session_url="",
        )
```

(The rest of the function — the "Repro complete" event, `format_result_message`, `send_message(["HypothesisAgent"], text)` — is unchanged.)

- [ ] **Step 7: Update `tests/test_repro_echo.py` for steps-passing**

The fixture message `_msg` already contains a numbered string but on one line; make it a real numbered block so `parse_steps` finds steps, and assert `run_repro` is called with the parsed steps. Replace `_msg` and add an assertion in `test_handler_sends_one_message_to_hypothesis`:

```python
def _msg(sender_name):
    return SimpleNamespace(
        sender_name=sender_name,
        sender_id="peer-id",
        chat_room_id="room-id",
        content=(
            "@ReproAgent repro steps for url:\n"
            "1. Open app\n2. Add todo\n3. Delete it\n4. Observe blank screen"
        ),
    )
```

In `test_handler_sends_one_message_to_hypothesis`, capture the call and assert steps were passed:

```python
def test_handler_sends_one_message_to_hypothesis():
    agent = _FakeAgent()
    fake_cfg = MagicMock()
    fake_run = AsyncMock(return_value=_fake_result())
    with (
        patch("triage.repro_agent.echo.load_config", return_value=fake_cfg),
        patch("triage.repro_agent.echo.run_repro", new=fake_run),
    ):
        asyncio.run(handle_parser_message(_msg("hanschundekad/parseragent"), agent))
    assert len(agent.messages) == 1
    mentions, text = agent.messages[0]
    assert mentions == ["HypothesisAgent"]
    assert "@hanschundekad/hypothesisagent" in text
    # steps were parsed from the numbered block and passed positionally
    called_steps = fake_run.call_args.args[1]
    assert called_steps == ["Open app", "Add todo", "Delete it", "Observe blank screen"]
    assert len(agent.events) == 2
```

`test_handler_ignores_hypothesis_sender` and `test_handler_browser_error_still_reports` keep working with the new `_msg` (the error test patches `run_repro` to raise — unaffected).

- [ ] **Step 8: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: PASS — all green (was 64; new `test_repro_loop.py` adds 4 → 68).

- [ ] **Step 9: Commit**

```bash
git add triage/repro_agent/loop.py triage/repro_agent/browser.py triage/repro_agent/echo.py tests/test_repro_loop.py tests/test_repro_echo.py
git commit -m "feat(repro): consume real Parser steps — replace hardcoded _STEPS

Task 1 of Phase 6. parse_steps() extracts ParserAgent's numbered-line
block; run_repro(cfg, steps, tweak=None) drives the browser with the
real steps. Parser->Repro path is now fully live.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 10: Live end-to-end verification (CHECKPOINT — show the user)**

Run the three agents against the live app and confirm: ParserAgent emits steps → ReproAgent parses them → real Browserbase session drives the *real* steps → result posts @HypothesisAgent. Capture the session replay URL. **Stop here and show the user a clean live run before starting Task 2.**

---

## Task 2: The retry loop (redirect_repro → fresh session → retry)

On a `redirect_repro` from HypothesisAgent, ReproAgent logs the failed attempt as an event, spins a **brand-new** Browserbase session (no reused `sessionId`), and re-runs the repro incorporating the redirect's tweak. Each attempt posts its real evidence @HypothesisAgent. State must persist across messages, so the handler becomes a factory closure holding `ReproLoopState` (the same pattern as `make_diagnosis_callback`).

A minimal cap guard ships **in this task** (the redirect branch refuses to retry once `attempts_exhausted`) so there is never an uncapped intermediate state. The full terminal UX (give-up message wording, confirm-latch, exhaustive safety tests, tunability) is Task 3, which we review before coding.

**Files:**
- Modify: `triage/repro_agent/loop.py` (add `MAX_REPRO_ATTEMPTS`, `classify_message`, `is_confirm`, `extract_tweak`, `ReproLoopState`)
- Modify: `triage/repro_agent/echo.py` (replace `handle_parser_message` with `make_repro_callback` + `_run_attempt`; wire `run()`)
- Test: `tests/test_repro_loop.py`, `tests/test_repro_echo.py`

**Interfaces:**
- Produces: `classify_message(sender_id, content, parser_id, hypothesis_id) -> Literal["steps","redirect","confirm","ignore"]`.
- Produces: `is_confirm(content: str) -> bool`; `extract_tweak(content: str) -> str`.
- Produces: `ReproLoopState` dataclass with fields `steps: list[str]`, `attempts: int`, `max_attempts: int` (default `MAX_REPRO_ATTEMPTS`), `terminal: bool`, `session_urls: list[str]`; property `attempts_exhausted: bool`; method `reset(steps)`.
- Produces: `make_repro_callback(cfg, state=None) -> Callable[[payload, agent], Coroutine]`.
- Consumes (Task 1): `parse_steps`, `run_repro(cfg, steps, tweak)`, `format_result_message`, `cfg.band_parser.agent_id`, `cfg.band_hypothesis.agent_id`.

- [ ] **Step 1: Write failing tests for the pure classifiers**

Append to `tests/test_repro_loop.py`:

```python
from triage.repro_agent.loop import (
    classify_message, is_confirm, extract_tweak, ReproLoopState, MAX_REPRO_ATTEMPTS,
)

_PARSER = "parser-id"
_HYPO = "hypo-id"
_CONFIRM = ("@hanschundekad/reproagent confirmed, matches the report. "
            "Root cause: reads items[0] after delete. Repro valid.")
_REDIRECT = ("@hanschundekad/reproagent retry with a slower delete "
             "(suspected cause: race on empty array)")


def test_is_confirm_true_on_confirm_text():
    assert is_confirm(_CONFIRM) is True


def test_is_confirm_false_on_redirect_text():
    assert is_confirm(_REDIRECT) is False


def test_extract_tweak_strips_handle_and_suspected_cause():
    assert extract_tweak(_REDIRECT) == "retry with a slower delete"


def test_classify_parser_steps():
    assert classify_message(_PARSER, "1. do x\n2. do y", _PARSER, _HYPO) == "steps"


def test_classify_parser_without_steps_is_ignore():
    assert classify_message(_PARSER, "hi there", _PARSER, _HYPO) == "ignore"


def test_classify_hypothesis_confirm():
    assert classify_message(_HYPO, _CONFIRM, _PARSER, _HYPO) == "confirm"


def test_classify_hypothesis_redirect():
    assert classify_message(_HYPO, _REDIRECT, _PARSER, _HYPO) == "redirect"


def test_classify_unknown_sender_is_ignore():
    assert classify_message("stranger", _REDIRECT, _PARSER, _HYPO) == "ignore"


def test_loop_state_reset_and_exhaustion():
    state = ReproLoopState()
    assert state.max_attempts == MAX_REPRO_ATTEMPTS
    state.reset(["a", "b"])
    assert state.steps == ["a", "b"] and state.attempts == 0 and state.terminal is False
    state.attempts = state.max_attempts
    assert state.attempts_exhausted is True
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_repro_loop.py -q`
Expected: FAIL — `ImportError: cannot import name 'classify_message'` (etc.)

- [ ] **Step 3: Implement the classifiers and state in `loop.py`**

Append to `triage/repro_agent/loop.py`:

```python
from dataclasses import dataclass, field
from typing import Literal

# --- Loop-safety knob -------------------------------------------------------
# Hard cap on total browser attempts per repro cycle (initial run + retries).
# THIS is the single dial to tune. 3 = initial attempt + up to 2 retries.
MAX_REPRO_ATTEMPTS = 3
# ---------------------------------------------------------------------------

MessageKind = Literal["steps", "redirect", "confirm", "ignore"]

# Confirm markers — must agree with hypothesis_agent/agent.py::
# format_diagnosis_message confirm branch. See "cross-agent text contract".
_CONFIRM_MARKERS = ("repro valid", "confirmed, matches the report")

# Strip a leading "@handle " and a trailing "(suspected cause: ...)" so the
# core redirect instruction remains.
_LEADING_HANDLE = re.compile(r"^\s*@\S+\s+")
_SUSPECTED_CAUSE = re.compile(r"\s*\(suspected cause:.*\)\s*$", re.IGNORECASE | re.DOTALL)


def is_confirm(content: str) -> bool:
    """True when a HypothesisAgent message is a repro-confirmation (terminal)."""
    low = content.lower()
    return any(marker in low for marker in _CONFIRM_MARKERS)


def extract_tweak(content: str) -> str:
    """Pull the retry instruction out of a HypothesisAgent redirect message."""
    text = _LEADING_HANDLE.sub("", content, count=1)
    text = _SUSPECTED_CAUSE.sub("", text)
    return text.strip()


def classify_message(
    sender_id: str | None,
    content: str,
    parser_id: str,
    hypothesis_id: str,
) -> MessageKind:
    """Decide how ReproAgent should treat an incoming Band message.

    By sender identity (robust — not name heuristics):
      ParserAgent + numbered steps -> "steps"   (start / restart a cycle)
      HypothesisAgent + confirm     -> "confirm" (terminal success)
      HypothesisAgent + otherwise   -> "redirect"(retry with tweak)
      anything else                 -> "ignore"
    """
    if sender_id == parser_id:
        return "steps" if parse_steps(content) else "ignore"
    if sender_id == hypothesis_id:
        return "confirm" if is_confirm(content) else "redirect"
    return "ignore"


@dataclass
class ReproLoopState:
    """Per-cycle retry state, held by the ReproAgent message callback."""

    steps: list[str] = field(default_factory=list)
    attempts: int = 0
    max_attempts: int = MAX_REPRO_ATTEMPTS
    terminal: bool = False
    session_urls: list[str] = field(default_factory=list)  # one per attempt (Phase 7)

    @property
    def attempts_exhausted(self) -> bool:
        return self.attempts >= self.max_attempts

    def reset(self, steps: list[str]) -> None:
        """Begin a fresh repro cycle (new Parser steps / re-parse)."""
        self.steps = steps
        self.attempts = 0
        self.terminal = False
        self.session_urls = []
```

- [ ] **Step 4: Run to verify pure tests pass**

Run: `.venv/bin/pytest tests/test_repro_loop.py -q`
Expected: PASS (all loop tests green)

- [ ] **Step 5: Write failing tests for the stateful callback**

Rewrite `tests/test_repro_echo.py`'s handler tests against the factory. Replace the three `test_handler_*` functions (keep `format_result_message` tests and `_FakeAgent`). Add a config stub and import:

```python
from types import SimpleNamespace
from triage.repro_agent.echo import make_repro_callback, format_result_message


def _cfg():
    return SimpleNamespace(
        band_parser=SimpleNamespace(agent_id="parser-id"),
        band_hypothesis=SimpleNamespace(agent_id="hypo-id"),
    )


def _parser_msg():
    return SimpleNamespace(
        sender_name="hanschundekad/parseragent", sender_id="parser-id",
        chat_room_id="room-id",
        content="@ReproAgent steps:\n1. Open app\n2. Add todo\n3. Delete it",
    )


def _redirect_msg():
    return SimpleNamespace(
        sender_name="hanschundekad/hypothesisagent", sender_id="hypo-id",
        chat_room_id="room-id",
        content="@hanschundekad/reproagent retry with a slower delete (suspected cause: race)",
    )


def test_parser_steps_trigger_one_attempt():
    agent = _FakeAgent()
    cb = make_repro_callback(_cfg())
    fake_run = AsyncMock(return_value=_fake_result())
    with patch("triage.repro_agent.echo.run_repro", new=fake_run):
        asyncio.run(cb(_parser_msg(), agent))
    assert fake_run.call_args.args[1] == ["Open app", "Add todo", "Delete it"]
    assert [m[0] for m in agent.messages] == [["HypothesisAgent"]]


def test_redirect_spawns_a_second_attempt_with_tweak():
    agent = _FakeAgent()
    cb = make_repro_callback(_cfg())
    fake_run = AsyncMock(return_value=_fake_result())
    with patch("triage.repro_agent.echo.run_repro", new=fake_run):
        asyncio.run(cb(_parser_msg(), agent))      # attempt 1
        asyncio.run(cb(_redirect_msg(), agent))    # attempt 2 (retry)
    assert fake_run.call_count == 2
    # second call carried the extracted tweak
    assert fake_run.call_args_list[1].kwargs.get("tweak") == "retry with a slower delete"
    # two results posted @HypothesisAgent (one per attempt)
    assert len(agent.messages) == 2


def test_redirect_before_any_steps_is_ignored():
    agent = _FakeAgent()
    cb = make_repro_callback(_cfg())
    fake_run = AsyncMock(return_value=_fake_result())
    with patch("triage.repro_agent.echo.run_repro", new=fake_run):
        asyncio.run(cb(_redirect_msg(), agent))
    # no steps yet -> nothing to retry; redirect with empty steps still guards
    assert fake_run.call_count <= 1  # tightened in Task 3
```

- [ ] **Step 6: Run to verify failure**

Run: `.venv/bin/pytest tests/test_repro_echo.py -q`
Expected: FAIL — `ImportError: cannot import name 'make_repro_callback'`

- [ ] **Step 7: Implement `make_repro_callback` + `_run_attempt` in `echo.py`**

In `triage/repro_agent/echo.py`, replace `handle_parser_message` (and the now-unused `_sender_is_hypothesis`) with the factory. Update imports:

```python
from triage.repro_agent.loop import (
    classify_message, parse_steps, extract_tweak, ReproLoopState,
)
```

Add:

```python
def make_repro_callback(cfg, state: ReproLoopState | None = None):
    """Build the stateful on_message callback (one ReproLoopState per process).

    Mirrors hypothesis_agent.make_diagnosis_callback: a closure so retry state
    survives across messages. Routes by classify_message; all browser work is
    delegated to _run_attempt -> run_repro (fresh session each call).
    """
    state = state if state is not None else ReproLoopState()

    async def on_message(payload, agent) -> None:
        sender = getattr(payload, "sender_name", None)
        sender_id = getattr(payload, "sender_id", None)
        print(f"\n[ReproAgent] << from {sender}: {payload.content[:120]!r}")

        kind = classify_message(
            sender_id, payload.content,
            cfg.band_parser.agent_id, cfg.band_hypothesis.agent_id,
        )

        if kind == "steps":
            state.reset(parse_steps(payload.content))
            print(f"[ReproAgent] parsed {len(state.steps)} steps — starting cycle.")
            await _run_attempt(cfg, state, agent, tweak=None)

        elif kind == "redirect":
            if not state.steps or state.attempts_exhausted:
                # No cycle in progress, or cap reached — Task 3 finalizes the
                # terminal give-up message here. Minimal safe stop for now.
                print("[ReproAgent] redirect ignored (no steps or cap reached).")
                return
            tweak = extract_tweak(payload.content)
            await agent.send_event(
                f"Attempt {state.attempts} did not reproduce; HypothesisAgent "
                f"redirected — retrying with tweak: {tweak!r}",
                "task",
            )
            await _run_attempt(cfg, state, agent, tweak=tweak)

        elif kind == "confirm":
            # Task 3 latches terminal here.
            print("[ReproAgent] HypothesisAgent confirmed — cycle complete.")

        else:
            print(f"[ReproAgent] ignoring message (kind={kind}).")

    return on_message


async def _run_attempt(cfg, state, agent, tweak) -> None:
    """Run one browser attempt (fresh session) and post the result."""
    state.attempts += 1
    await agent.send_event(
        f"Starting Browserbase repro attempt {state.attempts}/{state.max_attempts}"
        + (f" (tweak: {tweak})" if tweak else ""),
        "task",
    )
    try:
        result = await run_repro(cfg, state.steps, tweak=tweak)
    except Exception as exc:  # noqa: BLE001
        logger.error("[ReproAgent] browser execution failed: %s", exc)
        await agent.send_event(f"Browser execution error: {exc}", "error")
        result = ReproResultPayload(
            success=False, evidence=[f"Execution error: {exc}"],
            console_errors=[], session_url="",
        )
    if result.session_url:
        state.session_urls.append(result.session_url)  # keep replay URL (Phase 7)
    await agent.send_event(
        f"Attempt {state.attempts} complete — bug_detected={result.success}, "
        f"{len(result.console_errors)} console error(s)",
        "task",
    )
    text = format_result_message(result)
    await agent.send_message(["HypothesisAgent"], text)
    print(f"[ReproAgent] >> attempt {state.attempts} result @HypothesisAgent sent.")
```

Wire `run()` (replace the `on_message=` argument):

```python
        on_message=make_repro_callback(cfg),
```

- [ ] **Step 8: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: PASS — all green (loop + echo + browser).

- [ ] **Step 9: Commit**

```bash
git add triage/repro_agent/loop.py triage/repro_agent/echo.py tests/test_repro_loop.py tests/test_repro_echo.py
git commit -m "feat(repro): retry loop — redirect_repro spins fresh session + retries

Task 2 of Phase 6. classify_message routes Parser steps / Hypothesis
confirm / redirect by sender id. make_repro_callback holds ReproLoopState
so retries persist; each attempt is a fresh run_repro (new Browserbase
session) carrying the redirect tweak; evidence posts @HypothesisAgent.
Minimal cap guard present; full terminal UX is Task 3.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

> **Safety note:** Do NOT run Task 2 live against a HypothesisAgent that keeps redirecting until Task 3 lands — the give-up message and confirm-latch are finalized there. Task 2's tests drive a finite (single) redirect.

---

## Task 3: Loop safety (REVIEW THIS DESIGN WITH THE USER BEFORE CODING)

> This task is presented for review. Do not write code until the user approves the design below.

The mechanism exists after Task 2. Task 3 makes termination **provable and tunable**:

**Proposed design**

1. **The cap.** `MAX_REPRO_ATTEMPTS = 3` in `loop.py` — a single, commented module constant; `ReproLoopState.max_attempts` defaults to it. `attempts` counts every browser run (initial + retries). 3 ⇒ initial attempt + up to 2 retries. To tune: change one line.
2. **Two terminal states**, both latched by `state.terminal = True`:
   - **Confirmed:** HypothesisAgent sends a confirm → ReproAgent logs a `task` event ("Bug confirmed — loop complete"), sets `terminal`, sends no further messages.
   - **Could-not-reproduce:** a redirect arrives while `attempts_exhausted` → ReproAgent sets `terminal`, posts ONE final give-up message @HypothesisAgent ("could not reproduce after N attempts", with the per-attempt session replay URLs), and stops.
3. **The hard guarantee.** Once `state.terminal` is `True`, the callback ignores *every* subsequent message (logs and returns before any browser/Band action). Combined with the cap on `attempts`, the loop **cannot spin** — even if HypothesisAgent keeps redirecting, even if confirm-vs-redirect text classification is wrong. ReproAgent counts its own browser runs; nothing external can push it past the cap.
4. **Give-up addressing.** The final message @mentions HypothesisAgent (must @mention to be visible). HypothesisAgent may diagnose it and reply — but `terminal` is already set, so that reply is ignored. Bounded by one extra inbound message, never a loop.

**Design decisions to confirm with the user:**
- (a) Cap value **3** (initial + 2 retries) and the counting semantics above — right for the demo?
- (b) Cap lives as a **module constant** `MAX_REPRO_ATTEMPTS` (vs. `.env`/config). Constant = simplest single knob; config = tunable without code edit. Recommend constant for the hackathon.
- (c) Give-up message **@mentions HypothesisAgent** and includes the session replay URLs (vs. @mention nobody / broadcast). Recommend @HypothesisAgent.
- (d) New **Parser steps mid-cycle call `state.reset()`** — a re-parse (from a `redirect_parser`) starts a fresh capped cycle (attempts back to 0, terminal cleared). This intentionally supports the re-parse path; it means the ReproAgent cap bounds each *repro* cycle, not the higher-level Parser↔Hypothesis loop. Confirm this boundary is acceptable for Phase 6 (a global cross-agent cap is out of scope).

**Planned steps once approved (TDD):**

- [ ] **Step 1:** Failing tests in `tests/test_repro_echo.py`:
  - `test_confirm_latches_terminal_and_stops` — after a confirm, a following redirect does **not** call `run_repro`.
  - `test_cap_stops_after_max_attempts` — drive steps + (N) redirects; assert `run_repro` called exactly `MAX_REPRO_ATTEMPTS` times and exactly one give-up message is posted.
  - `test_terminal_ignores_all_further_messages` — after give-up, any message is a no-op (no new messages/events).
  - `test_giveup_message_lists_session_urls` — give-up text contains each attempt's replay URL.
- [ ] **Step 2:** Run → fail.
- [ ] **Step 3:** Add `format_giveup_message(state)` to `loop.py`; in `echo.py` add the `if state.terminal: return` guard at the top of the callback, set `terminal` on confirm, and on the exhausted-redirect branch set `terminal` + post `format_giveup_message`.
- [ ] **Step 4:** Run → pass; full suite green.
- [ ] **Step 5:** Live: drive a HypothesisAgent that redirects repeatedly; confirm ReproAgent stops at N with a clean give-up message and the room transcript ends. Tune `MAX_REPRO_ATTEMPTS` to 2, re-run, confirm it stops at 2.
- [ ] **Step 6:** Commit.

---

## Self-Review

**Spec coverage:**
- Task 1 (consume real Parser steps) → Task 1 ✔ (parse_steps + run_repro(steps) + live checkpoint).
- Task 2 (redirect → new session → retry with tweak, post evidence) → Task 2 ✔ (classify + factory state + `_run_attempt`; fresh `run_repro` per attempt = new session per §2.4; failed-attempt event; tweak applied).
- Task 3 (cap, terminal states, never spin, tunable) → Task 3 ✔ (design for review + TDD steps).
- Hard rules: browser-only-in-ReproAgent ✔ (browser.py untouched in role); new session per attempt ✔; band.py untouched ✔ (no edits planned — flagged to STOP if needed); @mention routing ✔; events vs messages ✔; replay URLs kept in `state.session_urls` ✔.

**Placeholder scan:** No TBD/"handle edge cases"/"similar to Task N" — every code step carries full code. Task 3's code is deferred *by design* (user wants to review first); its steps name exact tests and exact functions.

**Type consistency:** `run_repro(cfg, steps, tweak=None)` used identically in Task 1 and Task 2. `ReproLoopState` fields/`attempts_exhausted`/`reset` consistent between `loop.py` and `echo.py` usage. `classify_message` return literals match the `kind` branches in the callback. `format_result_message` / `ReproResultPayload` reused unchanged.
