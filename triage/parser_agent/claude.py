"""ParserAgent reasoning — turn a vague GitHub issue into structured repro steps.

The impressive part: Claude infers preconditions the user never stated (e.g.
"delete my last task" implies a task must first be added). Output is constrained
to a JSON schema so it drops straight into the shared ReproStepsPayload.
"""
from __future__ import annotations

import json

from triage.parser_agent.github import Issue
from triage.shared.band import ReproStepsPayload

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 4096

_SYSTEM = (
    "You are a senior QA engineer. You receive a bug report filed by a "
    "non-technical user about a web to-do application. The report is vague and "
    "casual. Turn it into a precise, ordered list of reproduction steps that a "
    "browser-automation agent can execute literally, one action at a time, "
    "against the live app.\n\n"
    "Rules:\n"
    "- Each step is a single concrete UI action: focusing a field, typing a "
    "value, or clicking one button. Never bundle two actions into one step.\n"
    "- Phrase each step as a direct imperative the automation agent can act on "
    "(e.g. \"Type 'Buy groceries' into the new-task text input\", \"Click the "
    "Add button\").\n"
    "- The browser is ALREADY open on the app. Do NOT emit any navigation, "
    "\"open the app\", or \"go to the URL\" step — start with the first on-page "
    "UI action. Navigation is not a clickable action and will fail.\n"
    "- Assume the app starts EMPTY with no pre-existing tasks. IGNORE any "
    "mention of pre-loaded or 'sample' todos in the report — the live app ships "
    "with none. So for any bug that involves deleting tasks, you MUST first add "
    "the task(s) yourself (type a value into the new-task input, then click the "
    "Add button) before any delete step.\n"
    "- CRITICAL: infer and include any precondition the user did not state but "
    "that must hold for the bug to occur. If the user says the app breaks when "
    "they delete their last task, the app must first contain a task — so add "
    "the create-task step(s) first, in order, then delete down to empty.\n"
    "- Deleting a task in this app requires CONFIRMING: after clicking a task's "
    "Delete button, a confirmation control appears (e.g. a 'Yes, delete' "
    "button) that must be clicked to complete the deletion. Include the "
    "confirmation click as its own step after each delete.\n"
    "- Do not include verification or assertion steps, and do not add "
    "commentary. Emit only the actions needed to reach the bug.\n"
    "- Order steps so executing them top to bottom reproduces the bug."
)

# Structured-output schema — constrains the response to a clean list of strings
# matching the shared ReproStepsPayload.steps shape. No new fields.
_STEPS_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["steps"],
    "additionalProperties": False,
}


def build_user_prompt(issue: Issue, redirect: str | None = None,
                      *, prior_context: str | None = None) -> str:
    """Render the user-turn prompt from the issue (plus optional learned memory / redirect)."""
    prompt = (
        f"GitHub issue title: {issue.title}\n\n"
        f"GitHub issue body:\n{issue.body}\n\n"
        "Produce the ordered reproduction steps."
    )
    if prior_context:
        prompt += (
            "\n\nLearned context from prior reproduction runs of this same issue:\n"
            f"{prior_context}\n\n"
            "Use this memory to pick a smarter first attempt — set up any required "
            "preconditions up front rather than discovering them through a failure."
        )
    if redirect:
        prompt += (
            "\n\nA previous attempt to reproduce these steps failed. Feedback "
            f"from the reproduction agent:\n{redirect}\n\n"
            "Re-read the issue and produce a revised, corrected set of steps "
            "that addresses this feedback."
        )
    return prompt


async def extract_steps(
    issue: Issue,
    *,
    client,
    redirect: str | None = None,
    prior_context: str | None = None,
) -> ReproStepsPayload:
    """Call Claude to extract structured repro steps from the issue.

    Args:
        issue: the fetched GitHub issue.
        client: an AsyncAnthropic client (injected for testability).
        redirect: optional feedback from a failed repro, woven into the prompt.
        prior_context: optional learned memory from prior runs, woven into the prompt.
    """
    response = await client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": _STEPS_SCHEMA}},
        messages=[{"role": "user",
                   "content": build_user_prompt(issue, redirect, prior_context=prior_context)}],
    )
    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)
    return ReproStepsPayload(issue_url=issue.url, steps=list(data["steps"]))
