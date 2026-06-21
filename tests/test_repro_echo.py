from triage.repro_agent.echo import (
    build_fake_result,
    format_result_message,
    _sender_is_hypothesis,
)
from triage.shared.band import ReproResultPayload


def test_build_fake_result_shape():
    result = build_fake_result()
    assert isinstance(result, ReproResultPayload)
    assert result.success is True              # placeholder: bug reproduced
    assert result.evidence                     # non-empty
    assert any("TypeError" in c for c in result.console_errors)
    assert "PLACEHOLDER" in result.session_url  # honest: not a real Browserbase session


def test_format_result_message_mentions_hypothesis():
    text = format_result_message(build_fake_result())
    assert "@hanschundekad/hypothesisagent" in text
    assert "TypeError" in text
    assert "BUG REPRODUCED" in text


def test_sender_is_hypothesis():
    assert _sender_is_hypothesis("hanschundekad/hypothesisagent") is True
    assert _sender_is_hypothesis("HypothesisAgent") is True
    assert _sender_is_hypothesis("hanschundekad/parseragent") is False
    assert _sender_is_hypothesis(None) is False
