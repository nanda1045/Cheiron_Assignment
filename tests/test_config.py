"""Tests for safe environment-backed application configuration."""

import pytest

from cheiron.config import Settings


def test_settings_load_and_mask_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-openai-key")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "unit-test-openai-key"
    assert "unit-test-openai-key" not in repr(settings)
    assert settings.openai_model == "gpt-5.6-sol"
