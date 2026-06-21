# triage/hypothesis_agent/reasoning.py
"""HypothesisAgent reasoning — Claude diagnoses root cause from evidence.

Pure reasoning: given the evidence text ReproAgent posts (verdict, session URL,
step evidence, console errors), call Claude and return a structured Diagnosis.
No Band, no asyncio — the Anthropic client is injected so this stays testable
and the caller controls its lifecycle.

SDK shape verified against the claude-api skill + installed anthropic 0.111.0:
structured output via output_config.format (json_schema); adaptive thinking
(budget_tokens is removed on Claude 4.x).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

MODEL = "claude-sonnet-4-6"

Decision = Literal["confirm", "redirect_repro", "redirect_parser"]


@dataclass
class Diagnosis:
    """Structured result of reasoning over one repro attempt's evidence."""

    decision: Decision
    root_cause: str
    redirect_instruction: str  # "" when decision == "confirm"


SYSTEM_PROMPT = (
    "You are HypothesisAgent in the TRIAGE bug-reproduction system. ReproAgent "
    "drove a REAL browser through a live app to reproduce a reported bug and has "
    "sent you the evidence from one attempt: a verdict, a session replay URL, "
    "step-by-step evidence, and any captured console errors.\n\n"
    "Reason about the likely ROOT CAUSE from the observed behavior and the "
    "console error ALONE — you cannot see the source code, and a diagnosis "
    "grounded in behavior is exactly what is wanted. Be specific and mechanistic "
    '(e.g. "reads items[0] after the array is emptied by the delete, '
    'dereferencing undefined").\n\n'
    "CRITICAL routing rule: ReproAgent executes ONE action per step and CANNOT "
    "invent, add, or reorder steps — it can only re-run the steps ParserAgent "
    "gave it, optionally with a small execution tweak. Only ParserAgent can "
    "change the step LIST. So if the fix requires ADDING, REMOVING, or "
    "REORDERING steps — e.g. a missing precondition (the list was empty, so "
    "items must be ADDED before they can be deleted), a wrong/absent control, "
    "or a needed action that simply isn't in the current steps — you MUST route "
    "to redirect_parser, never redirect_repro.\n\n"
    "Then choose EXACTLY ONE decision:\n"
    '- "confirm": the evidence clearly shows the reported bug fired (e.g. blank '
    "screen plus a matching console TypeError). The repro is valid.\n"
    '- "redirect_repro": use ONLY when the existing steps are CORRECT but '
    "execution was flaky or timing-sensitive (a real action didn't register, a "
    "dialog needed a moment). Same steps, run them again with a small tweak — "
    'put it in redirect_instruction (e.g. "retry with a slower delete so the '
    'confirmation dialog registers"). Do NOT use this to add a missing step.\n'
    '- "redirect_parser": the repro STEPS themselves were wrong or incomplete — '
    "a step found no target element, a precondition was missing (e.g. nothing "
    "to delete because no task was ever added), or the sequence needs new "
    "steps. The issue must be re-parsed. Put the concrete fix in "
    'redirect_instruction (e.g. "the task list was empty — the steps must first '
    'add a task via the input and Add button before deleting").\n\n'
    'For "confirm", set redirect_instruction to an empty string. Respond only '
    "via the structured schema."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["confirm", "redirect_repro", "redirect_parser"],
        },
        "root_cause": {"type": "string"},
        "redirect_instruction": {"type": "string"},
    },
    "required": ["decision", "root_cause", "redirect_instruction"],
    "additionalProperties": False,
}


def diagnose(evidence_text: str, client, model: str = MODEL) -> Diagnosis:
    """Reason about root cause and confirm/redirect from one attempt's evidence.

    Args:
        evidence_text: the raw Band message content ReproAgent sent.
        client: an anthropic.Anthropic-shaped client (only messages.create used).
        model: Claude model id.

    Returns:
        A Diagnosis. Blocking/synchronous — call via asyncio.to_thread from
        async code so the WebSocket event loop is not stalled.
    """
    # Evidence text format is produced by triage/repro_agent/echo.py::format_result_message
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": evidence_text}],
        output_config={"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}},
    )
    text = next(
        (
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ),
        None,
    )
    if text is None:
        raise ValueError(
            "No text block in Claude response; blocks: "
            f"{[getattr(b, 'type', '?') for b in response.content]}"
        )
    data = json.loads(text)
    return Diagnosis(
        decision=data["decision"],
        root_cause=data["root_cause"],
        redirect_instruction=data.get("redirect_instruction", ""),
    )
