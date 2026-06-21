"""Unit tests for ReproAgent bug-detection logic.

These tests are pure logic — no browser, no network, no env vars.
They exercise detect_bug() with synthetic inputs so the thresholds
are verifiable and tunable without a live session.
"""
import pytest
from triage.repro_agent.browser import DetectionResult, detect_bug

CRASH_ERROR = "TypeError: Cannot read properties of undefined (reading 'map')"
OTHER_ERROR = "TypeError: something unrelated"
BLANK_BODY = "   "
RICH_BODY = "My Tasks\n  test task\nAdd Delete"


def test_both_signals_true_detects_bug():
    result = detect_bug(body_text=BLANK_BODY, console_errors=[CRASH_ERROR])
    assert result.bug_detected is True
    assert result.blank_body is True
    assert result.console_match is True


def test_blank_body_only_does_not_detect():
    result = detect_bug(body_text=BLANK_BODY, console_errors=[])
    assert result.bug_detected is False
    assert result.blank_body is True
    assert result.console_match is False


def test_console_match_only_does_not_detect():
    result = detect_bug(body_text=RICH_BODY, console_errors=[CRASH_ERROR])
    assert result.bug_detected is False
    assert result.blank_body is False
    assert result.console_match is True


def test_neither_signal_does_not_detect():
    result = detect_bug(body_text=RICH_BODY, console_errors=[OTHER_ERROR])
    assert result.bug_detected is False


def test_partial_console_error_string_still_matches():
    # The real error may have extra context — match on substring
    partial = "Cannot read properties of undefined"
    result = detect_bug(body_text=BLANK_BODY, console_errors=[f"TypeError: {partial} (reading 'map')"])
    assert result.console_match is True


def test_multiple_errors_any_match_counts():
    result = detect_bug(
        body_text=BLANK_BODY,
        console_errors=[OTHER_ERROR, CRASH_ERROR],
    )
    assert result.bug_detected is True


def test_whitespace_only_body_is_blank():
    result = detect_bug(body_text="\n  \t  \n", console_errors=[CRASH_ERROR])
    assert result.blank_body is True


def test_returns_detection_result_type():
    result = detect_bug(body_text=BLANK_BODY, console_errors=[CRASH_ERROR])
    assert isinstance(result, DetectionResult)
