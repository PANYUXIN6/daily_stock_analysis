# -*- coding: utf-8 -*-
"""Tests for generation backend contracts and backend resolver semantics."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.llm.generation_backend import (  # noqa: E402
    GenerationCapabilities,
    GenerationError,
    GenerationErrorCode,
    GenerationResult,
)
from src.llm.litellm_backend import LiteLLMGenerationBackend  # noqa: E402


def _config(**overrides):
    defaults = {
        "generation_backend": "litellm",
        "generation_fallback_backend": "litellm",
        "agent_generation_backend": "auto",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_generation_result_and_capabilities_fields_are_public_contract() -> None:
    result = GenerationResult(
        text="response",
        model="deepseek/deepseek-v4-pro",
        provider="deepseek",
        backend="litellm",
        usage={"total_tokens": 3},
        raw={"id": "raw"},
        diagnostics={"route": "direct"},
    )
    capabilities = GenerationCapabilities(
        supports_json=True,
        supports_tools=True,
        supports_stream=True,
        supports_vision=False,
        supports_health_check=False,
        supports_smoke_test=False,
    )

    assert result.text == "response"
    assert result.model == "deepseek/deepseek-v4-pro"
    assert result.provider == "deepseek"
    assert result.backend == "litellm"
    assert result.usage == {"total_tokens": 3}
    assert result.raw == {"id": "raw"}
    assert result.diagnostics == {"route": "direct"}
    assert capabilities.supports_json is True
    assert capabilities.supports_tools is True
    assert capabilities.supports_stream is True
    assert capabilities.supports_vision is False
    assert capabilities.supports_health_check is False
    assert capabilities.supports_smoke_test is False


def test_generation_error_stage_uses_descriptive_string_contract() -> None:
    error = GenerationError(
        error_code=GenerationErrorCode.INVALID_JSON,
        stage="generation",
        retryable=True,
        fallbackable=True,
        backend="litellm",
        provider="deepseek",
        details={"allowed_stages": ["generation", "configuration", "execution", "validation", "fallback"]},
    )

    assert str(error) == "invalid_json at generation for backend litellm"
    assert error.stage in {"generation", "configuration", "execution", "validation", "fallback"}
    assert error.provider == "deepseek"
    assert error.details["allowed_stages"] == [
        "generation",
        "configuration",
        "execution",
        "validation",
        "fallback",
    ]


def test_litellm_backend_capabilities_and_result_normalization() -> None:
    received = {}

    def completion(prompt, generation_config, **kwargs):
        received["prompt"] = prompt
        received["generation_config"] = generation_config
        received["kwargs"] = kwargs
        return "ok", "deepseek/deepseek-v4-pro", {
            "provider": "deepseek",
            "total_tokens": 7,
        }

    backend = LiteLLMGenerationBackend(completion)
    result = backend.generate(
        "prompt",
        {"max_tokens": 128},
        system_prompt="system",
        stream=True,
        stream_progress_callback=lambda _chars: None,
        response_validator=lambda text: None,
        audit_context={"call_type": "analysis"},
    )

    assert backend.backend_id == "litellm"
    assert backend.capabilities.supports_json is True
    assert backend.capabilities.supports_tools is True
    assert backend.capabilities.supports_stream is True
    assert backend.capabilities.supports_vision is False
    assert backend.capabilities.supports_health_check is False
    assert backend.capabilities.supports_smoke_test is False
    assert result == GenerationResult(
        text="ok",
        model="deepseek/deepseek-v4-pro",
        provider="deepseek",
        backend="litellm",
        usage={"provider": "deepseek", "total_tokens": 7},
    )
    assert received["prompt"] == "prompt"
    assert received["generation_config"] == {"max_tokens": 128}
    assert received["kwargs"]["system_prompt"] == "system"
    assert received["kwargs"]["stream"] is True
    assert callable(received["kwargs"]["stream_progress_callback"])
    assert callable(received["kwargs"]["response_validator"])
    assert received["kwargs"]["audit_context"] == {"call_type": "analysis"}


def test_litellm_backend_derives_provider_from_model_when_usage_is_empty() -> None:
    backend = LiteLLMGenerationBackend(
        lambda _prompt, _generation_config, **_kwargs: (
            "ok",
            "deepseek/deepseek-v4-pro",
            {},
        )
    )

    result = backend.generate("prompt", {})

    assert result.provider == "deepseek"
    assert result.backend == "litellm"
    assert result.usage == {}
