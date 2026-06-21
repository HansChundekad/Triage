"""attach_diagnosis_capture — records HypothesisAgent's real diagnosis so the
harness eval/synthesis judge the actual root cause, not an empty string."""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib


def _load_script():
    p = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "phase7_traced_run.py"
    spec = importlib.util.spec_from_file_location("phase7_traced_run", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_attach_diagnosis_capture_records_last_message_without_breaking_send():
    mod = _load_script()

    class FakeAgent:
        def __init__(self):
            self.sent = []

        async def send_message(self, mentions, text):
            self.sent.append((mentions, text))
            return "ok"

    agent = FakeAgent()
    holder = mod.attach_diagnosis_capture(agent)
    assert holder["text"] == ""  # nothing sent yet

    async def run():
        r1 = await agent.send_message(["ParserAgent"], "redirect: add tasks first")
        r2 = await agent.send_message(["ReproAgent"], "confirmed. Root cause: reads .name on undefined")
        return r1, r2

    r1, r2 = asyncio.run(run())

    # Original send_message behaviour preserved (return value + side effect).
    assert (r1, r2) == ("ok", "ok")
    assert agent.sent == [
        (["ParserAgent"], "redirect: add tasks first"),
        (["ReproAgent"], "confirmed. Root cause: reads .name on undefined"),
    ]
    # The LAST diagnosis (the confirm with the root cause) is what eval/synthesis use.
    assert holder["text"] == "confirmed. Root cause: reads .name on undefined"
