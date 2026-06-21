# tests/test_parser_github.py
from __future__ import annotations

import pytest

from triage.parser_agent.github import issue_api_url


def test_issue_api_url_converts_web_url():
    assert (
        issue_api_url("https://github.com/octocat/hello-world/issues/42")
        == "https://api.github.com/repos/octocat/hello-world/issues/42"
    )


def test_issue_api_url_tolerates_trailing_whitespace_and_http():
    assert (
        issue_api_url("  http://github.com/o/r/issues/7  ")
        == "https://api.github.com/repos/o/r/issues/7"
    )


def test_issue_api_url_rejects_non_issue_url():
    with pytest.raises(ValueError):
        issue_api_url("https://github.com/octocat/hello-world/pull/42")
