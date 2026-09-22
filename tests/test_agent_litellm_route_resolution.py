# -*- coding: utf-8 -*-
"""Tests for Agent-safe LiteLLM route resolution."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.agent.llm_adapter import LLMToolAdapter
from src.agent.litellm_route_resolution import resolve_agent_litellm_route


def _config(**overrides):
    base = {
        "agent_generation_backend": "auto",
        "generation_backend": "litellm",
        "agent_litellm_model": "",
        "litellm_model": "",
        "litellm_fallback_models": [],
        "llm_model_list": [],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _remote_deployment(model_name: str):
    return {
        "model_name": model_name,
        "litellm_params": {
            "model": "deepseek/deepseek-flash",
            "api_key": "sk-remote",
        },
    }


def test_agent_resolver_preserves_direct_model_without_preflight_credentials() -> None:
    resolution = resolve_agent_litellm_route(
        _config(
            agent_litellm_model="deepseek/deepseek-flash",
            litellm_model="deepseek/deepseek-flash",
            litellm_fallback_models=["deepseek/deepseek-v4-pro"],
        )
    )

    assert resolution.available
    assert resolution.models_to_try == [
        "deepseek/deepseek-flash",
        "deepseek/deepseek-v4-pro",
    ]


def test_call_completion_does_not_overwrite_adapter_route_resolution() -> None:
    config = _config(litellm_model="deepseek/deepseek-test-model")
    adapter = LLMToolAdapter.__new__(LLMToolAdapter)
    adapter._config = config
    adapter._backend_error = None
    adapter._route_resolution = resolve_agent_litellm_route(config)

    original_resolution = adapter._route_resolution
    dynamic_resolution = type(original_resolution)(
        available=False,
        primary_model="deepseek/deepseek-test-model",
        models_to_try=[],
        model_list=[],
        reason="no_safe_agent_models",
    )

    with patch("src.agent.llm_adapter.resolve_agent_litellm_route", return_value=dynamic_resolution):
        response = adapter.call_completion([{"role": "user", "content": "hello"}])

    assert response.provider == "error"
    assert adapter._route_resolution is original_resolution
