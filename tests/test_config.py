import pytest

from triage.config import BandIdentity, Config, MissingConfigError, load_config

# Backend-agnostic base requirements (no trace-backend vars here).
REQUIRED = [
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
]

# Required only when the trace backend is AX (the default).
AX_REQUIRED = ["ARIZE_API_KEY", "ARIZE_SPACE_ID"]


def _set_all(monkeypatch):
    """Set every var for the default (AX) backend."""
    for name in REQUIRED + AX_REQUIRED:
        monkeypatch.setenv(name, f"value-for-{name}")
    # Default backend is ax; ensure no stray override.
    monkeypatch.delenv("TRIAGE_TRACE_BACKEND", raising=False)


def test_missing_all_required_lists_every_var(monkeypatch):
    for name in REQUIRED + AX_REQUIRED + [
        "PHOENIX_API_KEY", "PHOENIX_COLLECTOR_ENDPOINT",
        "ARIZE_PROJECT_NAME", "TRIAGE_TRACE_BACKEND",
    ]:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(MissingConfigError) as exc:
        load_config(load_env=False)
    message = str(exc.value)
    for name in REQUIRED + AX_REQUIRED:
        assert name in message


def test_missing_single_var_names_it(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("BROWSERBASE_PROJECT_ID", raising=False)
    with pytest.raises(MissingConfigError) as exc:
        load_config(load_env=False)
    assert "BROWSERBASE_PROJECT_ID" in str(exc.value)


def test_all_present_returns_config(monkeypatch):
    _set_all(monkeypatch)
    cfg = load_config(load_env=False)
    assert isinstance(cfg, Config)
    assert cfg.anthropic_api_key == "value-for-ANTHROPIC_API_KEY"
    assert isinstance(cfg.band_repro, BandIdentity)
    assert cfg.band_repro.api_key == "value-for-BAND_REPRO_API_KEY"
    assert cfg.band_repro.agent_id == "value-for-BAND_REPRO_AGENT_ID"


def test_trace_backend_defaults_to_ax(monkeypatch):
    _set_all(monkeypatch)
    cfg = load_config(load_env=False)
    assert cfg.trace_backend == "ax"
    assert cfg.arize_api_key == "value-for-ARIZE_API_KEY"
    assert cfg.arize_space_id == "value-for-ARIZE_SPACE_ID"
    assert cfg.arize_project_name == "triage-bug-repro"


def test_ax_backend_requires_arize_vars(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("ARIZE_API_KEY", raising=False)
    monkeypatch.delenv("ARIZE_SPACE_ID", raising=False)
    with pytest.raises(MissingConfigError) as exc:
        load_config(load_env=False)
    msg = str(exc.value)
    assert "ARIZE_API_KEY" in msg and "ARIZE_SPACE_ID" in msg


def test_phoenix_backend_requires_phoenix_key_not_arize(monkeypatch):
    # Select the Phoenix fallback: ARIZE vars are NOT required, PHOENIX_API_KEY is.
    for name in REQUIRED:
        monkeypatch.setenv(name, f"value-for-{name}")
    monkeypatch.delenv("ARIZE_API_KEY", raising=False)
    monkeypatch.delenv("ARIZE_SPACE_ID", raising=False)
    monkeypatch.setenv("TRIAGE_TRACE_BACKEND", "phoenix")
    monkeypatch.delenv("PHOENIX_API_KEY", raising=False)
    with pytest.raises(MissingConfigError) as exc:
        load_config(load_env=False)
    assert "PHOENIX_API_KEY" in str(exc.value)

    # With PHOENIX_API_KEY set, phoenix backend loads without ARIZE vars.
    monkeypatch.setenv("PHOENIX_API_KEY", "pk-test")
    cfg = load_config(load_env=False)
    assert cfg.trace_backend == "phoenix"
    assert cfg.phoenix_api_key == "pk-test"


def test_arize_project_name_override(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.setenv("ARIZE_PROJECT_NAME", "custom-project")
    cfg = load_config(load_env=False)
    assert cfg.arize_project_name == "custom-project"


def test_phoenix_endpoint_defaults_when_unset(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
    cfg = load_config(load_env=False)
    assert cfg.phoenix_collector_endpoint == "https://app.phoenix.arize.com"


def test_empty_string_counts_as_missing(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    with pytest.raises(MissingConfigError) as exc:
        load_config(load_env=False)
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_phoenix_endpoint_override(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
    cfg = load_config(load_env=False)
    assert cfg.phoenix_collector_endpoint == "http://localhost:6006"


def test_band_room_id_optional(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("BAND_ROOM_ID", raising=False)
    cfg = load_config(load_env=False)
    assert cfg.band_room_id is None


def test_band_room_id_loaded_when_set(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.setenv("BAND_ROOM_ID", "some-room-uuid")
    cfg = load_config(load_env=False)
    assert cfg.band_room_id == "some-room-uuid"


def test_band_room_id_empty_string_is_none(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.setenv("BAND_ROOM_ID", "")
    cfg = load_config(load_env=False)
    assert cfg.band_room_id is None


def test_outer_loop_defaults_off(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("TRIAGE_OUTER_LOOP", raising=False)
    cfg = load_config(load_env=False)
    assert cfg.outer_loop_enabled is False


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on"])
def test_outer_loop_truthy_values_enable(monkeypatch, raw):
    _set_all(monkeypatch)
    monkeypatch.setenv("TRIAGE_OUTER_LOOP", raw)
    assert load_config(load_env=False).outer_loop_enabled is True


def test_outer_loop_not_required(monkeypatch):
    # Absent TRIAGE_OUTER_LOOP must NOT make config fail to load.
    _set_all(monkeypatch)
    monkeypatch.delenv("TRIAGE_OUTER_LOOP", raising=False)
    load_config(load_env=False)  # does not raise
