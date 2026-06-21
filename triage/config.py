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
_ARIZE_PROJECT_DEFAULT = "triage-bug-repro"
_TRACE_BACKEND_DEFAULT = "ax"


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
    # Trace backend selector: "ax" (Arize AX, primary) or "phoenix" (fallback).
    trace_backend: str
    # Arize AX credentials (required when trace_backend == "ax").
    arize_api_key: str
    arize_space_id: str
    arize_project_name: str
    # Phoenix Cloud credentials (required only when trace_backend == "phoenix").
    phoenix_api_key: str
    phoenix_collector_endpoint: str
    band_room_id: str | None
    app_url: str
    github_issue_url: str
    outer_loop_enabled: bool


# Required regardless of trace backend.
_REQUIRED_BASE = (
    "ANTHROPIC_API_KEY",
    "BROWSERBASE_API_KEY",
    "BROWSERBASE_PROJECT_ID",
    "BAND_PARSER_API_KEY",
    "BAND_PARSER_AGENT_ID",
    "BAND_REPRO_API_KEY",
    "BAND_REPRO_AGENT_ID",
    "BAND_HYPOTHESIS_API_KEY",
    "BAND_HYPOTHESIS_AGENT_ID",
    "TRIAGE_APP_URL",
    "TRIAGE_GITHUB_ISSUE_URL",
)
# Backend-specific required vars (the migration makes AX primary).
_REQUIRED_BY_BACKEND = {
    "ax": ("ARIZE_API_KEY", "ARIZE_SPACE_ID"),
    "phoenix": ("PHOENIX_API_KEY",),
}


_TRUTHY = {"1", "true", "yes", "on"}


def _parse_bool(raw: str | None) -> bool:
    return (raw or "").strip().lower() in _TRUTHY


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

    trace_backend = (os.environ.get("TRIAGE_TRACE_BACKEND") or _TRACE_BACKEND_DEFAULT).strip().lower()
    backend_required = _REQUIRED_BY_BACKEND.get(trace_backend, _REQUIRED_BY_BACKEND["ax"])
    required = _REQUIRED_BASE + backend_required

    missing = [name for name in required if not os.environ.get(name)]
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
        trace_backend=trace_backend,
        arize_api_key=env.get("ARIZE_API_KEY", ""),
        arize_space_id=env.get("ARIZE_SPACE_ID", ""),
        arize_project_name=env.get("ARIZE_PROJECT_NAME") or _ARIZE_PROJECT_DEFAULT,
        phoenix_api_key=env.get("PHOENIX_API_KEY", ""),
        phoenix_collector_endpoint=env.get(
            "PHOENIX_COLLECTOR_ENDPOINT", _PHOENIX_ENDPOINT_DEFAULT
        ),
        band_room_id=env.get("BAND_ROOM_ID") or None,
        app_url=env["TRIAGE_APP_URL"],
        github_issue_url=env["TRIAGE_GITHUB_ISSUE_URL"],
        outer_loop_enabled=_parse_bool(env.get("TRIAGE_OUTER_LOOP")),
    )
