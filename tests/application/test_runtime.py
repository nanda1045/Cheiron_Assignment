"""Tests for planner-provider runtime selection without network access."""

import pytest

from cheiron.application.runtime import build_runtime
from cheiron.config import Settings


@pytest.mark.asyncio
async def test_auto_mode_without_key_uses_rules() -> None:
    runtime = build_runtime(
        Settings(_env_file=None, planner_provider="auto", anthropic_api_key=None)
    )
    try:
        assert runtime.effective_planner == "rules"
        assert runtime.anthropic_client is None
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
async def test_anthropic_mode_without_key_is_explicitly_unavailable() -> None:
    runtime = build_runtime(
        Settings(_env_file=None, planner_provider="anthropic", anthropic_api_key=None)
    )
    try:
        assert runtime.effective_planner == "unavailable"
        assert runtime.anthropic_client is None
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
async def test_auto_mode_with_key_builds_guarded_anthropic_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "unit-test-anthropic-key")
    runtime = build_runtime(Settings(_env_file=None, planner_provider="auto"))
    try:
        assert runtime.effective_planner == "claude_with_rules_fallback"
        assert runtime.anthropic_client is not None
    finally:
        await runtime.aclose()
