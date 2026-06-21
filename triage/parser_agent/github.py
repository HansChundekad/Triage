# triage/parser_agent/github.py
"""ParserAgent GitHub integration — fetch a live issue via the REST API.

No browser, no auth: a plain public GET of the issue ParserAgent must parse.
"""
from __future__ import annotations

import re

# GitHub REST API version header. Live docs surfaced "2026-03-10"; the header is
# optional and GitHub defaults sensibly, so we pin the stable, widely-supported
# value. Bump only if a needed field requires a newer version.
_API_VERSION = "2022-11-28"

_ISSUE_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)$"
)


def issue_api_url(web_url: str) -> str:
    """Convert a GitHub issue web URL to its REST API URL.

    Raises:
        ValueError: if ``web_url`` is not a GitHub issue URL.
    """
    match = _ISSUE_URL_RE.match(web_url.strip())
    if not match:
        raise ValueError(f"Not a GitHub issue URL: {web_url!r}")
    owner = match.group("owner")
    repo = match.group("repo")
    number = match.group("number")
    return f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
