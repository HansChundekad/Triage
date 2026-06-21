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


# append to tests/test_parser_github.py
import asyncio

import httpx

from triage.parser_agent.github import Issue, fetch_issue


def test_fetch_issue_extracts_title_and_body_and_sends_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["accept"] = request.headers.get("Accept")
        seen["version"] = request.headers.get("X-GitHub-Api-Version")
        return httpx.Response(
            200,
            json={"title": "App goes blank", "body": "when I delete my last task"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        issue = asyncio.run(
            fetch_issue("https://github.com/o/r/issues/7", http_client=client)
        )
    finally:
        asyncio.run(client.aclose())

    assert isinstance(issue, Issue)
    assert issue.title == "App goes blank"
    assert "delete my last task" in issue.body
    assert issue.url == "https://github.com/o/r/issues/7"
    assert seen["path"] == "/repos/o/r/issues/7"
    assert seen["accept"] == "application/vnd.github+json"
    assert seen["version"] == "2022-11-28"


def test_fetch_issue_null_body_becomes_empty_string():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"title": "T", "body": None})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        issue = asyncio.run(
            fetch_issue("https://github.com/o/r/issues/1", http_client=client)
        )
    finally:
        asyncio.run(client.aclose())
    assert issue.body == ""


def test_fetch_issue_raises_on_non_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(
                fetch_issue("https://github.com/o/r/issues/9", http_client=client)
            )
    finally:
        asyncio.run(client.aclose())
