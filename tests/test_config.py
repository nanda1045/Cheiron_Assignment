"""Tests for safe environment-backed application configuration."""

import pytest

from cheiron.config import Settings


def test_settings_load_and_mask_anthropic_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "unit-test-anthropic-key")

    settings = Settings(_env_file=None)

    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == "unit-test-anthropic-key"
    assert "unit-test-anthropic-key" not in repr(settings)
    assert settings.anthropic_model == "claude-sonnet-5"
