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
