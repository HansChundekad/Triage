"""Fail-loud configuration loader for TRIAGE.

Reads all required settings from the environment and raises a single, clear
error listing every missing variable — so a misconfiguration fails immediately
with a readable message instead of deep inside an agent at runtime.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

_PHOENIX_ENDPOINT_DEFAULT = "https://app.phoenix.arize.com"


class MissingConfigError(RuntimeError):
    """Raised when one or more required environment variables are absent."""


@dataclass(frozen=True)
class BandIdentity:
    """One of the three distinct Band agent identities."""

    api_key: str
    agent_id: str


@dataclass(frozen=True)
class Config:
    """Fully-resolved TRIAGE configuration."""

    anthropic_api_key: str
    browserbase_api_key: str
    browserbase_project_id: str
    band_parser: BandIdentity
    band_repro: BandIdentity
    band_hypothesis: BandIdentity
    phoenix_api_key: str
    phoenix_collector_endpoint: str
    app_url: str
    github_issue_url: str


_REQUIRED = (
    "ANTHROPIC_API_KEY",
    "BROWSERBASE_API_KEY",
    "BROWSERBASE_PROJECT_ID",
    "BAND_PARSER_API_KEY",
    "BAND_PARSER_AGENT_ID",
    "BAND_REPRO_API_KEY",
    "BAND_REPRO_AGENT_ID",
    "BAND_HYPOTHESIS_API_KEY",
    "BAND_HYPOTHESIS_AGENT_ID",
    "PHOENIX_API_KEY",
    "TRIAGE_APP_URL",
    "TRIAGE_GITHUB_ISSUE_URL",
)


def load_config(load_env: bool = True) -> Config:
    """Load and validate TRIAGE configuration from the environment.

    Args:
        load_env: when True, load a local ``.env`` file before reading
            ``os.environ``. Tests pass False to read only the patched env.

    Raises:
        MissingConfigError: if any required variable is unset or empty,
            naming every missing variable at once.
    """
    if load_env:
        load_dotenv()

    missing = [name for name in _REQUIRED if not os.environ.get(name)]
    if missing:
        raise MissingConfigError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill these in."
        )

    env = os.environ
    return Config(
        anthropic_api_key=env["ANTHROPIC_API_KEY"],
        browserbase_api_key=env["BROWSERBASE_API_KEY"],
        browserbase_project_id=env["BROWSERBASE_PROJECT_ID"],
        band_parser=BandIdentity(
            api_key=env["BAND_PARSER_API_KEY"],
            agent_id=env["BAND_PARSER_AGENT_ID"],
        ),
        band_repro=BandIdentity(
            api_key=env["BAND_REPRO_API_KEY"],
            agent_id=env["BAND_REPRO_AGENT_ID"],
        ),
        band_hypothesis=BandIdentity(
            api_key=env["BAND_HYPOTHESIS_API_KEY"],
            agent_id=env["BAND_HYPOTHESIS_AGENT_ID"],
        ),
        phoenix_api_key=env["PHOENIX_API_KEY"],
        phoenix_collector_endpoint=env.get(
            "PHOENIX_COLLECTOR_ENDPOINT", _PHOENIX_ENDPOINT_DEFAULT
        ),
        app_url=env["TRIAGE_APP_URL"],
        github_issue_url=env["TRIAGE_GITHUB_ISSUE_URL"],
    )
