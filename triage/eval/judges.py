"""LLM-as-judge classifiers + pure input builders for repro-attempt scoring.

create_classifier / LLM signatures verified against the installed arize-phoenix-evals
in Task 0 — adjust prompt_template kwarg name / choices kwarg if drift was recorded.
"""
from __future__ import annotations

from triage.eval.ground_truth import PLANTED_BUG

FIDELITY_CHOICES = {"reproduced": 1.0, "inconclusive": 0.5, "not_reproduced": 0.0}
ROOT_CAUSE_CHOICES = {"correct": 1.0, "partially_correct": 0.5, "incorrect": 0.0}

_FIDELITY_TEMPLATE = (
    "You are grading whether a browser-automation attempt genuinely reproduced "
    "the REPORTED bug (not merely produced some error).\n\n"
    "Reported issue:\n{input}\n\n"
    "Attempt evidence:\n{output}\n\n"
    "Answer 'reproduced' only if the observed behavior matches the reported bug; "
    "'not_reproduced' if it clearly did not; 'inconclusive' if the evidence is "
    "insufficient."
)
_ROOT_CAUSE_TEMPLATE = (
    "You are grading whether a diagnosed root cause is correct.\n\n"
    "Reported issue:\n{input}\n\n"
    "Known correct root cause (ground truth):\n{reference}\n\n"
    "Proposed root cause:\n{output}\n\n"
    "Answer 'correct', 'partially_correct', or 'incorrect'."
)


def build_fidelity_input(issue_text: str, attempt: dict) -> dict:
    verdict = "BUG REPRODUCED" if attempt.get("bug_detected") else "BUG NOT REPRODUCED"
    evidence = "\n".join(attempt.get("evidence", []))
    console = "\n".join(attempt.get("console_errors", []))
    return {
        "input": issue_text,
        "output": f"verdict: {verdict}\nconsole:\n{console}\nevidence:\n{evidence}",
    }


def build_root_cause_input(issue_text: str, hypothesis_root_cause: str) -> dict:
    return {
        "input": issue_text,
        "reference": PLANTED_BUG.root_cause,
        "output": hypothesis_root_cause,
    }


def make_fidelity_judge(llm):
    from phoenix.evals import create_classifier
    return create_classifier(
        name="repro_fidelity", llm=llm,
        prompt_template=_FIDELITY_TEMPLATE, choices=FIDELITY_CHOICES,
    )


def make_root_cause_judge(llm):
    from phoenix.evals import create_classifier
    return create_classifier(
        name="root_cause_correctness", llm=llm,
        prompt_template=_ROOT_CAUSE_TEMPLATE, choices=ROOT_CAUSE_CHOICES,
    )


def build_judge_llm(cfg):
    """Anthropic judge LLM (or LiteLLM->Anthropic if no native adapter — see Task 0)."""
    from phoenix.evals.llm import LLM
    try:
        return LLM(provider="anthropic", model="claude-sonnet-4-6")
    except Exception:  # noqa: BLE001 — adapter not present; fall back to LiteLLM
        return LLM(provider="litellm", model="anthropic/claude-sonnet-4-6")
