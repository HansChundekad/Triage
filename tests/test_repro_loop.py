from triage.repro_agent.loop import (
    parse_steps,
    classify_message,
    is_confirm,
    extract_tweak,
    ReproLoopState,
    MAX_REPRO_ATTEMPTS,
    format_giveup_message,
)

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


# --- Task 2: classifiers + state -------------------------------------------

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


def test_format_giveup_message_lists_session_urls():
    state = ReproLoopState(attempts=3, session_urls=["url-a", "url-b", "url-c"])
    msg = format_giveup_message(state)
    assert "@hanschundekad/hypothesisagent" in msg
    assert "could not reproduce after 3" in msg
    assert "url-a" in msg and "url-b" in msg and "url-c" in msg
