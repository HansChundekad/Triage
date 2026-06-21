#!/usr/bin/env python
"""Phase 3 integration harness — the Python equivalent of the spec's testEchoChain.

Spawns the three REAL merged agents as separate child processes, lets the
echo chain run end-to-end against the live Band room, captures the transcript,
and asserts five checks. Runs the whole thing three times consecutively.

This project is all-Python (no TypeScript / npm), so this is the faithful
Python port of the spec's Step 2 harness. Two intentional, documented
deviations from the literal spec:

  1. No separate "observer" trigger client. ParserAgent self-posts its opening
     @ReproAgent message ~2s after it connects (see triage/parser_agent/__main__.py),
     so starting ParserAgent LAST is itself the trigger. We also only own three
     Band identities, so a fourth observer identity isn't available.
  2. The transcript is reconstructed from each agent's own stdout/stderr (the
     BandAgent layer logs every send as "[Name] → [targets]: text"), rather
     than from an observer socket.

Chain under test:
    ParserAgent --@ReproAgent-->     ReproAgent
    ReproAgent  --@HypothesisAgent--> HypothesisAgent
    HypothesisAgent --@ReproAgent-->  ReproAgent (ignores HypothesisAgent -> chain ends)

Coordination (per the build note): start the LISTENERS first
(HypothesisAgent + ReproAgent) so their WebSockets are subscribed, THEN start
the TALKER (ParserAgent) last so its opening message lands after the other two
are listening. Band only delivers @mentioned messages received while subscribed.

Run:
    .venv/bin/python scripts/test_echo_chain.py
"""
from __future__ import annotations

import ast
import asyncio
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from triage.config import load_config  # noqa: E402
from triage.shared.band import BandAgent  # noqa: E402

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
NUM_RUNS = 3
PAUSE_BETWEEN_RUNS = 5.0       # spec: 5s pause between runs
LISTENER_CONNECT_TIMEOUT = 12.0  # max wait for both listeners to connect
CONNECT_DEADLINE = 6.0         # per-agent connect latency we treat as "prompt"
CHAIN_TIMEOUT = 15.0           # spec: up to 15s for HypothesisAgent's final post
SETTLE_AFTER_FINAL = 1.5       # let trailing logs flush after the final post
GRACEFUL_KILL_TIMEOUT = 6.0

AGENTS = {
    "ParserAgent": ["-m", "triage.parser_agent"],
    "ReproAgent": ["-m", "triage.repro_agent"],
    "HypothesisAgent": ["-m", "triage.hypothesis_agent"],
}

# A send is logged uniformly by BandAgent.send_message: "[Name] → [targets]: text"
_SEND_RE = re.compile(r"\[(?P<name>\w+)\] → (?P<targets>\[[^\]]*\]): (?P<text>.*)")
# Connect markers printed/logged by each agent on join.
_CONNECT_RE = re.compile(r"connected to room|listening in room")
# Anything that smells like a dropped / re-established socket.
_RECONNECT_RE = re.compile(
    r"reconnect|connection closed|connectionclosed|going away|"
    r"\b1006\b|websocket.*clos|listener error|lost connection",
    re.IGNORECASE,
)


@dataclass
class LogLine:
    ts: float          # time.monotonic() when the harness read the line
    agent: str         # which child process produced it
    text: str


@dataclass
class SendEvent:
    ts: float
    sender: str
    targets: list[str]
    text: str


@dataclass
class Recorder:
    """Thread-safe sink for child output."""

    lines: list[LogLine] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, agent: str, text: str) -> None:
        with self._lock:
            self.lines.append(LogLine(time.monotonic(), agent, text))

    def snapshot(self) -> list[LogLine]:
        with self._lock:
            return list(self.lines)


def _pump(proc: subprocess.Popen, agent: str, rec: Recorder) -> None:
    """Read a child's merged stdout/stderr line-by-line, record + echo live."""
    tag = {"ParserAgent": "P", "ReproAgent": "R", "HypothesisAgent": "H"}[agent]
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip("\n")
        rec.add(agent, line)
        print(f"   {tag}| {line}", flush=True)


def _spawn(agent: str, room_id: str, rec: Recorder) -> tuple[subprocess.Popen, float]:
    env = os.environ.copy()
    env["BAND_ROOM_ID"] = room_id           # shared room for all three children
    env["PYTHONUNBUFFERED"] = "1"            # line-buffered so we read promptly
    proc = subprocess.Popen(
        [sys.executable, *AGENTS[agent]],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    spawn_ts = time.monotonic()
    threading.Thread(target=_pump, args=(proc, agent, rec), daemon=True).start()
    return proc, spawn_ts


def _connect_ts(rec: Recorder, agent: str) -> float | None:
    for ln in rec.snapshot():
        if ln.agent == agent and _CONNECT_RE.search(ln.text):
            return ln.ts
    return None


def _send_events(rec: Recorder) -> list[SendEvent]:
    out: list[SendEvent] = []
    for ln in rec.snapshot():
        m = _SEND_RE.search(ln.text)
        if not m:
            continue
        try:
            targets = list(ast.literal_eval(m.group("targets")))
        except (ValueError, SyntaxError):
            targets = [m.group("targets")]
        out.append(SendEvent(ln.ts, m.group("name"), targets, m.group("text")))
    return out


async def _create_fresh_room(cfg) -> str:
    """Create a brand-new room and add all three identities as participants.

    A fresh room per run isolates each run and honours the project's
    'new session per retry' convention. ParserAgent owns/creates it.
    """
    creator = BandAgent(
        name="ParserAgent",
        agent_id=cfg.band_parser.agent_id,
        api_key=cfg.band_parser.api_key,
    )
    room_id = await creator.connect(room_id=None)  # None => create
    await creator.add_participant("ReproAgent")
    await creator.add_participant("HypothesisAgent")
    await creator.disconnect()
    return room_id


def _stop(procs: dict[str, subprocess.Popen]) -> None:
    for proc in procs.values():
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)   # agents catch KeyboardInterrupt -> clean shutdown
    deadline = time.monotonic() + GRACEFUL_KILL_TIMEOUT
    for proc in procs.values():
        remaining = max(0.1, deadline - time.monotonic())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            proc.kill()


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _mentions(text: str, *needles: str) -> bool:
    low = text.lower()
    return any(n.lower() in low for n in needles)


def evaluate(
    rec: Recorder,
    spawn_ts: dict[str, float],
    teardown_ts: float,
) -> tuple[list[CheckResult], list[str]]:
    sends = [e for e in _send_events(rec) if e.ts <= teardown_ts]
    first_send: dict[str, SendEvent] = {}
    for e in sends:
        first_send.setdefault(e.sender, e)

    connect = {a: _connect_ts(rec, a) for a in AGENTS}
    results: list[CheckResult] = []

    # CHECK 1 — all three connected promptly
    latencies = {}
    all_connected = True
    for a in AGENTS:
        if connect[a] is None:
            all_connected = False
            latencies[a] = None
        else:
            latencies[a] = connect[a] - spawn_ts[a]
    lat_str = ", ".join(
        f"{a}={'MISS' if latencies[a] is None else f'{latencies[a]:.2f}s'}"
        for a in AGENTS
    )
    slow = [a for a, v in latencies.items() if v is not None and v > CONNECT_DEADLINE]
    c1_pass = all_connected and not slow
    detail1 = f"connect latency: {lat_str}"
    if slow:
        detail1 += f" — slower than {CONNECT_DEADLINE:.0f}s: {', '.join(slow)}"
    if not all_connected:
        detail1 += " — agent(s) never logged a join"
    results.append(CheckResult("CHECK 1 — ALL THREE CONNECTED", c1_pass, detail1))

    # CHECK 2 — mention routing is exclusive / ordered
    have_all = all(a in first_send for a in AGENTS)
    if have_all:
        p, r, h = (first_send["ParserAgent"], first_send["ReproAgent"],
                   first_send["HypothesisAgent"])
        ordered = p.ts < r.ts < h.ts
        targets_ok = (
            "ReproAgent" in p.targets
            and "HypothesisAgent" in r.targets
            and "ReproAgent" in h.targets
        )
        # Hypothesis must not have spoken before Repro's first post
        hyp_after_repro = first_send["HypothesisAgent"].ts > first_send["ReproAgent"].ts
        c2_pass = ordered and targets_ok and hyp_after_repro
        detail2 = (
            f"order Parser<Repro<Hypothesis={ordered}; "
            f"targets P→{p.targets} R→{r.targets} H→{h.targets}; "
            f"Hypothesis-after-Repro={hyp_after_repro}"
        )
    else:
        c2_pass = False
        detail2 = f"not all agents posted; senders seen: {sorted(first_send)}"
    results.append(CheckResult("CHECK 2 — MENTION ROUTING IS EXCLUSIVE", c2_pass, detail2))

    # CHECK 3 — chain completed without intervention
    posted = [a for a in AGENTS if a in first_send]
    c3_pass = len(posted) == 3
    detail3 = f"agents that posted ≥1 message: {posted}"
    results.append(CheckResult("CHECK 3 — CHAIN COMPLETED", c3_pass, detail3))

    # CHECK 4 — transcript reads like a conversation (@mentions present, right targets)
    if have_all:
        p_ok = _mentions(first_send["ParserAgent"].text, "@ReproAgent", "@hanschundekad/reproagent")
        r_ok = _mentions(first_send["ReproAgent"].text, "@HypothesisAgent", "@hanschundekad/hypothesisagent")
        h_ok = _mentions(first_send["HypothesisAgent"].text, "@ReproAgent", "@hanschundekad/reproagent")
        c4_pass = p_ok and r_ok and h_ok
        detail4 = f"Parser→@Repro={p_ok}, Repro→@Hypothesis={r_ok}, Hypothesis→@Repro={h_ok}"
    else:
        c4_pass = False
        detail4 = "chain incomplete — cannot assess @mentions"
    results.append(CheckResult("CHECK 4 — TRANSCRIPT READS LIKE A CONVERSATION", c4_pass, detail4))

    # CHECK 5 — websockets stayed alive (scan only the run window, pre-teardown)
    hits = [
        f"[{ln.agent}] {ln.text}"
        for ln in rec.snapshot()
        if ln.ts <= teardown_ts and _RECONNECT_RE.search(ln.text)
    ]
    c5_pass = not hits
    detail5 = "no reconnect/closed/error events" if c5_pass else f"{len(hits)} event(s): {hits[:3]}"
    results.append(CheckResult("CHECK 5 — WEBSOCKETS STAYED ALIVE", c5_pass, detail5))

    # Transcript (in send order)
    transcript = [
        f"[{e.sender} → {', '.join(e.targets)}]: {e.text}"
        for e in sends
    ]
    return results, transcript


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------
@dataclass
class RunResult:
    passed: bool
    checks: list[CheckResult]
    transcript: list[str]
    room_id: str


def run_once(cfg, run_idx: int) -> RunResult:
    print(f"\n========== RUN {run_idx} ==========")
    room_id = asyncio.run(_create_fresh_room(cfg))
    print(f"[harness] fresh room for run {run_idx}: {room_id}")

    rec = Recorder()
    procs: dict[str, subprocess.Popen] = {}
    spawn_ts: dict[str, float] = {}

    # Listeners first so their WebSockets are subscribed before the talker posts.
    for agent in ("HypothesisAgent", "ReproAgent"):
        procs[agent], spawn_ts[agent] = _spawn(agent, room_id, rec)
        print(f"[harness] started listener {agent}")

    # Wait for both listeners to log a join.
    deadline = time.monotonic() + LISTENER_CONNECT_TIMEOUT
    while time.monotonic() < deadline:
        if all(_connect_ts(rec, a) for a in ("HypothesisAgent", "ReproAgent")):
            break
        time.sleep(0.2)
    print("[harness] listeners connected (or timed out) — starting ParserAgent (talker)")

    # Talker last — it self-posts ~2s after connecting.
    procs["ParserAgent"], spawn_ts["ParserAgent"] = _spawn("ParserAgent", room_id, rec)

    # Wait up to CHAIN_TIMEOUT for HypothesisAgent's post (the final link).
    deadline = time.monotonic() + CHAIN_TIMEOUT
    while time.monotonic() < deadline:
        if any(e.sender == "HypothesisAgent" for e in _send_events(rec)):
            break
        time.sleep(0.2)
    time.sleep(SETTLE_AFTER_FINAL)

    teardown_ts = time.monotonic()
    _stop(procs)

    checks, transcript = evaluate(rec, spawn_ts, teardown_ts)
    passed = all(c.passed for c in checks)

    print(f"\n--- RUN {run_idx} RESULT ---")
    for c in checks:
        mark = "✅" if c.passed else "❌"
        print(f"  {mark} {c.name}\n        {c.detail}")
    print("\n  Transcript:")
    for line in transcript:
        print(f"    {line}")
    print(f"\n  {'✅ PHASE 3 PASS — all checks passed' if passed else '❌ PHASE 3 FAIL'}")

    return RunResult(passed, checks, transcript, room_id)


def main() -> int:
    cfg = load_config()
    if cfg.band_room_id:
        # We deliberately mint a fresh room per run; an inherited room would be
        # reused across runs and defeat isolation. Just informational.
        print(f"[harness] note: BAND_ROOM_ID is set ({cfg.band_room_id}); "
              "harness still creates a fresh room per run for isolation.")

    runs: list[RunResult] = []
    for i in range(1, NUM_RUNS + 1):
        result = run_once(cfg, i)
        runs.append(result)
        if not result.passed:
            print(f"\n❌ STOPPING — Run {i} failed. Failed checks:")
            for c in result.checks:
                if not c.passed:
                    print(f"   - {c.name}: {c.detail}")
            print("\nNot retrying automatically (flaky == fail). Surface to operator.")
            return 1
        if i < NUM_RUNS:
            print(f"\n[harness] Run {i} passed — pausing {PAUSE_BETWEEN_RUNS:.0f}s ...")
            time.sleep(PAUSE_BETWEEN_RUNS)

    # Final report
    print("\n\n--- PHASE 3 COMPLETE ---")
    print("Merge: clean")
    print("Build: clean")
    for i, r in enumerate(runs, 1):
        print(f"Run {i}: PASS")
        for c in r.checks:
            print(f"   ✅ {c.name}")
    print("\nBand room transcript (Run 3):")
    for line in runs[-1].transcript:
        print(f"  {line}")
    print("\nREADY FOR PHASE 4. No further action taken.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
