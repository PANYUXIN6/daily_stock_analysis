# -*- coding: utf-8 -*-
"""Tests for provider prompt-cache capability registry and hint lowering."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import textwrap
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.llm.provider_cache import (
    DeepSeekCaps,
    DirectiveSupport,
    ProviderCacheCaps,
    ProviderCacheRouteContext,
    RetentionPolicySupport,
    apply_prompt_cache_hints,
    build_provider_cache_route_context,
    filter_prompt_cache_telemetry,
    infer_provider_family,
    resolve_provider_cache_caps,
)
from src.llm.usage import build_domain_hmac


def _config(**kwargs):
    defaults = {
        "llm_prompt_cache_telemetry_enabled": True,
        "llm_prompt_cache_hints_enabled": False,
        "llm_prompt_cache_diagnostics_level": "off",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _verified_caps(
    provider: str,
    directive_support: DirectiveSupport,
    *,
    api_surface: str | None = None,
    gateway: str | None = None,
    model_pattern: str = "*",
) -> ProviderCacheCaps:
    return ProviderCacheCaps(
        schema_version="provider_cache_caps_v1",
        provider=provider,
        api_surface=api_surface or "chat_completions",
        gateway=gateway,
        cloud_platform="none",
        model_pattern=model_pattern,
        verification_status="smoke_tested",
        cache_activation="routing_hint_only" if provider == "deepseek" else "explicit_breakpoint",
        directive_support=directive_support,
        retention_policy_support=RetentionPolicySupport(),
        usage_paths={},
        rate_limit_semantics="unknown",
        cost_model="unknown",
        doc_sources=("https://example.test/docs",),
        last_verified_at="2026-06-20",
        deepseek_caps=DeepSeekCaps(user_id_supported=True, user_id_enabled_by_default=True)
        if provider == "deepseek"
        else None,
    )


def test_registry_returns_unknown_for_unregistered_openai_compatible_gateway():
    caps = resolve_provider_cache_caps(
        ProviderCacheRouteContext(
            model="openai/some-proxy-model",
            provider="openai_compatible",
            api_base="https://unknown-gateway.example/v1",
        )
    )

    assert caps.provider == "unknown"
    assert not caps.directive_support.prompt_cache_key












def test_registry_honors_exact_and_prefix_model_patterns():
    prefix_caps = _verified_caps(
        "deepseek",
        DirectiveSupport(prompt_cache_key=True),
        model_pattern="deepseek/deepseek-flash*",
    )

    with patch("src.llm.provider_cache.PROVIDER_CACHE_REGISTRY", (prefix_caps,)):
        matched = resolve_provider_cache_caps(
            ProviderCacheRouteContext(
                model="deepseek/deepseek-flash",
                provider="deepseek",
                api_surface="chat_completions",
            )
        )
        rejected = resolve_provider_cache_caps(
            ProviderCacheRouteContext(
                model="openai/o3",
                provider="deepseek",
                api_surface="chat_completions",
            )
        )

    assert matched.provider == "deepseek"
    assert rejected.provider == "unknown"




def test_provider_family_resolver_only_recognizes_deepseek_models():
    assert infer_provider_family(model="deepseek/deepseek-flash") == "deepseek"
    assert infer_provider_family(model="custom-model", api_base="https://deepseek-compatible.example") == "unknown"


def test_hints_disabled_preserves_request_shape_and_input_object():
    original = {
        "model": "deepseek/deepseek-flash",
        "messages": [{"role": "user", "content": "hello"}],
        "extra_body": {"thinking": {"type": "enabled"}},
    }
    before = copy.deepcopy(original)

    result = apply_prompt_cache_hints(
        original,
        ProviderCacheRouteContext(model="deepseek/deepseek-flash", provider="deepseek"),
        _config(llm_prompt_cache_hints_enabled=False),
    )

    assert result.call_kwargs == before
    assert original == before
    assert not result.hint_applied
    assert result.disabled_reason == "hints_disabled"


def test_openai_doc_only_caps_do_not_emit_prompt_cache_key_until_verified():
    original = {"model": "deepseek/deepseek-flash", "messages": [{"role": "user", "content": "hello"}]}

    result = apply_prompt_cache_hints(
        original,
        ProviderCacheRouteContext(model="deepseek/deepseek-flash", provider="deepseek", api_surface="chat_completions"),
        _config(llm_prompt_cache_hints_enabled=True, llm_prompt_cache_diagnostics_level="basic"),
    )

    assert "prompt_cache_key" not in result.call_kwargs
    assert not result.hint_applied
    assert result.disabled_reason == "capability_not_verified"
    assert result.diagnostics["verification_status"] == "doc_only"






def test_repeated_lowering_from_shared_input_does_not_cross_pollute_results():
    original = {
        "model": "deepseek/deepseek-v4-pro",
        "messages": [
            {"role": "system", "content": "stable rules"},
            {"role": "user", "content": "dynamic quote 600519"},
        ],
    }
    before = copy.deepcopy(original)
    caps = _verified_caps("deepseek", DirectiveSupport(block_cache_control=True))

    with patch("src.llm.provider_cache.resolve_provider_cache_caps", return_value=caps):
        first = apply_prompt_cache_hints(
            original,
            ProviderCacheRouteContext(model="deepseek/deepseek-v4-pro", provider="deepseek"),
            _config(llm_prompt_cache_hints_enabled=True),
        )
        second = apply_prompt_cache_hints(
            original,
            ProviderCacheRouteContext(model="deepseek/deepseek-v4-pro", provider="deepseek"),
            _config(llm_prompt_cache_hints_enabled=True),
        )

    assert original == before
    assert first.call_kwargs is not second.call_kwargs
    assert first.call_kwargs["messages"] is not second.call_kwargs["messages"]
    first.call_kwargs["messages"][0]["content"] = "mutated first result"
    assert second.call_kwargs["messages"][0]["content"] == "stable rules"
    assert original["messages"][0]["content"] == "stable rules"




def test_domain_hmac_separates_prompt_cache_route_and_deepseek_domains(monkeypatch):
    monkeypatch.setenv("LLM_USAGE_HMAC_SECRET", "same-secret")
    value = {"provider": "deepseek", "call_type": "analysis"}

    prompt_key = build_domain_hmac(value, domain="prompt_cache_key")
    route_key = build_domain_hmac(value, domain="route_key")
    deepseek_id = build_domain_hmac(value, domain="deepseek_session_isolation")

    assert prompt_key["hmac"] != route_key["hmac"]
    assert route_key["hmac"] != deepseek_id["hmac"]
    assert prompt_key["hmac_key_version"] == "local-v1"


def test_debug_diagnostics_do_not_include_raw_prompt_or_request_body(monkeypatch):
    monkeypatch.setenv("LLM_USAGE_HMAC_SECRET", "cache-secret")
    original = {
        "model": "deepseek/deepseek-flash",
        "messages": [{"role": "user", "content": "SECRET_PROMPT 600519 https://hooks.example"}],
    }
    caps = _verified_caps("deepseek", DirectiveSupport(prompt_cache_key=True))

    with patch("src.llm.provider_cache.resolve_provider_cache_caps", return_value=caps):
        result = apply_prompt_cache_hints(
            original,
            ProviderCacheRouteContext(model="deepseek/deepseek-flash", provider="deepseek"),
            _config(llm_prompt_cache_hints_enabled=True, llm_prompt_cache_diagnostics_level="debug"),
        )

    diagnostics_text = str(result.diagnostics)
    assert "SECRET_PROMPT" not in diagnostics_text
    assert "600519" not in diagnostics_text
    assert "hooks.example" not in diagnostics_text


def test_filter_prompt_cache_telemetry_removes_provider_cache_fields_when_disabled():
    usage = {
        "prompt_tokens": 10,
        "completion_tokens": 2,
        "total_tokens": 12,
        "provider_usage_json": '{"prompt_tokens":10}',
        "normalized_cache_read_tokens": 5,
        "cache_capability": "supported",
        "cache_observation": "partial_hit",
        "messages_hmac": "a" * 64,
    }

    filtered = filter_prompt_cache_telemetry(
        usage,
        _config(llm_prompt_cache_telemetry_enabled=False),
    )

    assert filtered["prompt_tokens"] == 10
    assert filtered["messages_hmac"] == "a" * 64
    assert getattr(filtered, "prompt_cache_telemetry_disabled", False)
    assert "prompt_cache_telemetry_disabled" not in filtered
    assert "provider_usage_json" not in filtered
    assert "normalized_cache_read_tokens" not in filtered
    assert "cache_capability" not in filtered
