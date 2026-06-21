from triage.parser_agent.claude import build_user_prompt
from triage.parser_agent.github import Issue


def _issue():
    return Issue(url="https://issue/X", title="Crash on delete", body="Deleting crashes.")


def test_prior_context_is_woven_into_prompt():
    p = build_user_prompt(_issue(), prior_context="Prior-run memory: add a task first.")
    assert "Prior-run memory: add a task first." in p
    assert "prior" in p.lower()


def test_prompt_without_prior_context_is_unchanged():
    p = build_user_prompt(_issue())
    assert "Prior-run memory" not in p


def test_redirect_and_prior_context_coexist():
    p = build_user_prompt(_issue(), redirect="too fast", prior_context="add a task first")
    assert "too fast" in p and "add a task first" in p
