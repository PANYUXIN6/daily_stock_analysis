# -*- coding: utf-8 -*-
"""Provider prompt-cache capability registry and safe hint lowering."""

from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Mapping, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

VerificationStatus = Literal["verified", "doc_only", "smoke_tested", "unverified"]
CacheActivation = Literal[
    "implicit_provider_managed",
    "explicit_breakpoint",
    "explicit_cached_resource",
    "routing_hint_only",
    "response_cache",
    "none",
    "unknown",
]
ApiSurface = Literal["chat_completions", "litellm_completion", "unknown"]
CloudPlatform = Literal["none", "unknown"]
RateLimitSemantics = Literal["cached_counts", "cached_not_counted", "unknown"]
CostModel = Literal["deepseek_hit_miss", "unknown"]

ACTIVE_HINT_VERIFICATION_STATUSES = {"verified", "smoke_tested"}
DIAGNOSTICS_LEVELS = {"off", "basic", "debug"}
PROMPT_CACHE_TELEMETRY_DISABLED_ATTR = "prompt_cache_telemetry_disabled"

class PromptCacheTelemetryFilteredUsage(dict):
    """Usage mapping marker for storage without adding a public usage field."""


@dataclass(frozen=True)
class DirectiveSupport:
    prompt_cache_key: bool = False
    prompt_cache_retention: bool = False
    top_level_cache_control: bool = False
    block_cache_control: bool = False
    cached_content_resource: bool = False
    session_id: bool = False
    litellm_cache_control_injection_points: bool = False
    provider_managed_no_directive: bool = False


@dataclass(frozen=True)
class RetentionPolicySupport:
    supported_values: Tuple[str, ...] = ()
    default_policy_source: Literal["provider_default", "gateway_default", "project_default", "unknown"] = "unknown"
    zdr_interaction: Literal["compatible", "disabled", "unknown"] = "unknown"


@dataclass(frozen=True)
class DeepSeekCaps:
    user_id_supported: bool = False
    user_id_enabled_by_default: bool = False
    allowed_charset: str = "A-Za-z0-9_-"
    max_length: int = 64


@dataclass(frozen=True)
class ProviderCacheCaps:
    schema_version: str
    provider: str
    api_surface: ApiSurface
    gateway: Optional[str]
    cloud_platform: CloudPlatform
    model_pattern: str
    verification_status: VerificationStatus
    cache_activation: CacheActivation
    directive_support: DirectiveSupport
    native_min_cache_tokens: Optional[int] = None
    routed_min_cache_tokens: Optional[int] = None
    observed_min_cache_tokens: Optional[int] = None
    eligibility_source: Literal["provider_doc", "gateway_doc", "smoke_test", "unknown"] = "unknown"
    ttl_options: Tuple[str, ...] = ()
    retention_policy_support: RetentionPolicySupport = field(default_factory=RetentionPolicySupport)
    requires_resource_lifecycle: bool = False
    usage_paths: Dict[str, str] = field(default_factory=dict)
    rate_limit_semantics: RateLimitSemantics = "unknown"
    cost_model: CostModel = "unknown"
    doc_sources: Tuple[str, ...] = ()
    last_verified_at: str = ""
    deepseek_caps: Optional[DeepSeekCaps] = None

    @property
    def caps_id(self) -> str:
        gateway = self.gateway or "direct"
        return f"{self.provider}:{self.api_surface}:{gateway}:{self.model_pattern}"


@dataclass(frozen=True)
class ProviderCacheRouteContext:
    model: str
    provider: Optional[str] = None
    api_base: Optional[str] = None
    api_surface: ApiSurface = "litellm_completion"
    gateway: Optional[str] = None
    cloud_platform: CloudPlatform = "none"
    call_type: Optional[str] = None


@dataclass(frozen=True)
class PromptCacheHintResult:
    call_kwargs: Dict[str, Any]
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    hint_applied: bool = False
    disabled_reason: Optional[str] = None
    caps: Optional[ProviderCacheCaps] = None


def _caps(
    provider: str,
    *,
    api_surface: ApiSurface = "litellm_completion",
    gateway: Optional[str] = None,
    cloud_platform: CloudPlatform = "none",
    model_pattern: str = "*",
    verification_status: VerificationStatus = "doc_only",
    cache_activation: CacheActivation = "unknown",
    directive_support: Optional[DirectiveSupport] = None,
    native_min_cache_tokens: Optional[int] = None,
    routed_min_cache_tokens: Optional[int] = None,
    observed_min_cache_tokens: Optional[int] = None,
    eligibility_source: Literal["provider_doc", "gateway_doc", "smoke_test", "unknown"] = "unknown",
    ttl_options: Tuple[str, ...] = (),
    retention_policy_support: Optional[RetentionPolicySupport] = None,
    requires_resource_lifecycle: bool = False,
    usage_paths: Optional[Dict[str, str]] = None,
    rate_limit_semantics: RateLimitSemantics = "unknown",
    cost_model: CostModel = "unknown",
    doc_sources: Tuple[str, ...] = (),
    last_verified_at: str = "2026-06-20",
    deepseek_caps: Optional[DeepSeekCaps] = None,
) -> ProviderCacheCaps:
    return ProviderCacheCaps(
        schema_version="provider_cache_caps_v1",
        provider=provider,
        api_surface=api_surface,
        gateway=gateway,
        cloud_platform=cloud_platform,
        model_pattern=model_pattern,
        verification_status=verification_status,
        cache_activation=cache_activation,
        directive_support=directive_support or DirectiveSupport(),
        native_min_cache_tokens=native_min_cache_tokens,
        routed_min_cache_tokens=routed_min_cache_tokens,
        observed_min_cache_tokens=observed_min_cache_tokens,
        eligibility_source=eligibility_source,
        ttl_options=ttl_options,
        retention_policy_support=retention_policy_support or RetentionPolicySupport(),
        requires_resource_lifecycle=requires_resource_lifecycle,
        usage_paths=usage_paths or {},
        rate_limit_semantics=rate_limit_semantics,
        cost_model=cost_model,
        doc_sources=doc_sources,
        last_verified_at=last_verified_at,
        deepseek_caps=deepseek_caps,
    )


PROVIDER_CACHE_REGISTRY: Tuple[ProviderCacheCaps, ...] = (
    _caps(
        "deepseek",
        api_surface="chat_completions",
        verification_status="doc_only",
        cache_activation="implicit_provider_managed",
        directive_support=DirectiveSupport(provider_managed_no_directive=True),
        usage_paths={
            "cache_read": "usage.prompt_cache_hit_tokens",
            "cache_miss": "usage.prompt_cache_miss_tokens",
        },
        cost_model="deepseek_hit_miss",
        doc_sources=("https://api-docs.deepseek.com/guides/kv_cache",),
        deepseek_caps=DeepSeekCaps(user_id_supported=True, user_id_enabled_by_default=False),
    ),
)

UNKNOWN_PROVIDER_CACHE_CAPS = _caps(
    "unknown",
    api_surface="unknown",
    verification_status="unverified",
    cache_activation="unknown",
    directive_support=DirectiveSupport(),
    last_verified_at="",
)


def normalize_prompt_cache_diagnostics_level(value: Any) -> str:
    normalized = str(value or "off").strip().lower()
    return normalized if normalized in DIAGNOSTICS_LEVELS else "off"


def build_provider_cache_route_context(
    *,
    model: str,
    provider: Optional[str] = None,
    call_kwargs: Optional[Mapping[str, Any]] = None,
    model_list: Optional[List[Dict[str, Any]]] = None,
    call_type: Optional[str] = None,
) -> ProviderCacheRouteContext:
    kwargs = call_kwargs or {}
    api_base = _first_non_empty(
        kwargs.get("api_base"),
        kwargs.get("base_url"),
        _model_list_api_base(model, model_list),
    )
    family = infer_provider_family(model=model, provider=provider, api_base=api_base)
    configured_api_surface = _model_list_api_surface(model, model_list)
    return ProviderCacheRouteContext(
        model=model,
        provider=provider or family,
        api_base=api_base,
        api_surface=configured_api_surface or _infer_api_surface(family, api_base),
        gateway=_infer_gateway(api_base, family),
        cloud_platform=_infer_cloud_platform(api_base, family),
        call_type=call_type,
    )


def resolve_provider_cache_caps(route_context: ProviderCacheRouteContext) -> ProviderCacheCaps:
    family = infer_provider_family(
        model=route_context.model,
        provider=route_context.provider,
        api_base=route_context.api_base,
    )
    for caps in PROVIDER_CACHE_REGISTRY:
        if caps.provider != family:
            continue
        if not _caps_route_matches(caps, route_context):
            continue
        return caps
    return UNKNOWN_PROVIDER_CACHE_CAPS


def _caps_route_matches(caps: ProviderCacheCaps, route_context: ProviderCacheRouteContext) -> bool:
    if (caps.gateway or None) != (route_context.gateway or None):
        return False
    if not _api_surface_matches(caps.api_surface, route_context.api_surface):
        return False
    return _model_pattern_matches(caps.model_pattern, route_context.model)


def _api_surface_matches(caps_surface: ApiSurface, route_surface: ApiSurface) -> bool:
    if caps_surface in {"unknown", "litellm_completion"}:
        return True
    return caps_surface == route_surface


def _model_pattern_matches(pattern: str, model: str) -> bool:
    normalized_pattern = (pattern or "*").strip().lower()
    normalized_model = (model or "").strip().lower()
    if normalized_pattern in {"", "*"}:
        return True
    if normalized_pattern.endswith("*"):
        return normalized_model.startswith(normalized_pattern[:-1])
    return normalized_model == normalized_pattern


def infer_provider_family(*, model: str = "", provider: Optional[str] = None, api_base: Optional[str] = None) -> str:
    if provider == "deepseek" or model.startswith(("deepseek/", "deepseek-")):
        return "deepseek"
    return "unknown"




def apply_prompt_cache_hints(
    call_kwargs: Mapping[str, Any],
    route_context: ProviderCacheRouteContext,
    config: Any,
) -> PromptCacheHintResult:
    """Return request kwargs with safe provider-specific cache hints applied."""
    new_kwargs = copy.deepcopy(dict(call_kwargs))
    caps = resolve_provider_cache_caps(route_context)
    diagnostics_level = normalize_prompt_cache_diagnostics_level(
        getattr(config, "llm_prompt_cache_diagnostics_level", "off")
    )
    hints_enabled = bool(getattr(config, "llm_prompt_cache_hints_enabled", False))

    if not hints_enabled:
        return PromptCacheHintResult(
            call_kwargs=new_kwargs,
            diagnostics=_diagnostics(diagnostics_level, caps, False, "hints_disabled"),
            hint_applied=False,
            disabled_reason="hints_disabled",
            caps=caps,
        )

    if caps.verification_status not in ACTIVE_HINT_VERIFICATION_STATUSES:
        return PromptCacheHintResult(
            call_kwargs=new_kwargs,
            diagnostics=_diagnostics(diagnostics_level, caps, False, "capability_not_verified"),
            hint_applied=False,
            disabled_reason="capability_not_verified",
            caps=caps,
        )

    applied = False
    disabled_reason: Optional[str] = None
    family = infer_provider_family(
        model=route_context.model,
        provider=route_context.provider,
        api_base=route_context.api_base,
    )

    if family == "deepseek" and caps.deepseek_caps and caps.deepseek_caps.user_id_enabled_by_default:
        user_id = _deepseek_user_id(route_context, caps.deepseek_caps)
        if user_id:
            new_kwargs["user_id"] = user_id
            applied = True
        else:
            disabled_reason = "hmac_secret_unavailable"
    else:
        disabled_reason = "no_supported_hint_for_route"

    return PromptCacheHintResult(
        call_kwargs=new_kwargs,
        diagnostics=_diagnostics(diagnostics_level, caps, applied, disabled_reason, route_context),
        hint_applied=applied,
        disabled_reason=disabled_reason,
        caps=caps,
    )


def filter_prompt_cache_telemetry(usage: Mapping[str, Any], config: Any) -> Dict[str, Any]:
    """Remove provider cache telemetry fields when prompt-cache telemetry is disabled."""
    result = dict(usage or {})
    if bool(getattr(config, "llm_prompt_cache_telemetry_enabled", True)):
        return result
    for key in (
        "provider_usage_json",
        "provider_usage_schema_name",
        "provider_usage_schema_version",
        "provider_usage_observed_at",
        "normalized_cache_read_tokens",
        "normalized_cache_write_tokens",
        "normalized_cache_miss_tokens",
        "normalized_uncached_input_tokens",
        "normalized_cache_eligible_input_tokens",
        "normalized_cache_hit_ratio",
        "normalized_cache_write_ratio",
        "cache_capability",
        "cache_eligibility",
        "cache_observation",
        "estimated_prefix_tokens",
        "provider_reported_cached_tokens",
        "provider_min_cache_tokens",
        "eligibility_confidence",
    ):
        result.pop(key, None)
    filtered = PromptCacheTelemetryFilteredUsage(result)
    setattr(filtered, PROMPT_CACHE_TELEMETRY_DISABLED_ATTR, True)
    return filtered




def _safe_hmac_token(value: Any, *, domain: str) -> Optional[str]:
    from src.llm.usage import build_domain_hmac

    hmac_fields = build_domain_hmac(value, domain=domain)
    digest = hmac_fields.get("hmac")
    return str(digest) if digest else None


def _deepseek_user_id(route_context: ProviderCacheRouteContext, caps: DeepSeekCaps) -> Optional[str]:
    digest = _safe_hmac_token(
        {
            "provider": "deepseek",
            "api_surface": route_context.api_surface,
            "gateway": route_context.gateway,
            "call_type": route_context.call_type,
        },
        domain="deepseek_session_isolation",
    )
    if not digest:
        return None
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", digest)
    return sanitized[: caps.max_length]


def _diagnostics(
    level: str,
    caps: ProviderCacheCaps,
    hint_applied: bool,
    disabled_reason: Optional[str],
    route_context: Optional[ProviderCacheRouteContext] = None,
) -> Dict[str, Any]:
    if level == "off":
        return {}
    diagnostics: Dict[str, Any] = {
        "provider": caps.provider,
        "api_surface": caps.api_surface,
        "verification_status": caps.verification_status,
        "cache_activation": caps.cache_activation,
        "hint_applied": hint_applied,
        "disabled_reason": disabled_reason,
    }
    if level == "debug":
        diagnostics.update(
            {
                "matched_caps_id": caps.caps_id,
                "usage_paths": dict(caps.usage_paths),
                "requires_resource_lifecycle": caps.requires_resource_lifecycle,
                "directive_support": {
                    "prompt_cache_key": caps.directive_support.prompt_cache_key,
                    "prompt_cache_retention": caps.directive_support.prompt_cache_retention,
                    "top_level_cache_control": caps.directive_support.top_level_cache_control,
                    "block_cache_control": caps.directive_support.block_cache_control,
                    "cached_content_resource": caps.directive_support.cached_content_resource,
                    "session_id": caps.directive_support.session_id,
                    "litellm_cache_control_injection_points": caps.directive_support.litellm_cache_control_injection_points,
                    "provider_managed_no_directive": caps.directive_support.provider_managed_no_directive,
                },
            }
        )
        if route_context is not None:
            route_hmac = _safe_hmac_token(
                {
                    "provider": caps.provider,
                    "api_surface": route_context.api_surface,
                    "gateway": route_context.gateway,
                    "call_type": route_context.call_type,
                    "model_pattern": caps.model_pattern,
                },
                domain="route_key",
            )
            diagnostics["route_key_hmac"] = route_hmac
    return diagnostics


def _model_list_api_base(model: str, model_list: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    normalized_model = (model or "").strip()
    if not normalized_model or not model_list:
        return None
    for entry in model_list:
        if not isinstance(entry, Mapping):
            continue
        params = entry.get("litellm_params", {}) or {}
        if not isinstance(params, Mapping):
            params = {}
        names = {
            str(entry.get("model_name") or "").strip(),
            str(params.get("model") or "").strip(),
        }
        if normalized_model not in names:
            continue
        return _first_non_empty(params.get("api_base"), params.get("base_url"))
    return None


def _model_list_api_surface(model: str, model_list: Optional[List[Dict[str, Any]]]) -> Optional[ApiSurface]:
    """Return the endpoint surface attached to a matching Router deployment."""
    normalized_model = (model or "").strip()
    if not normalized_model or not model_list:
        return None
    surfaces: set[str] = set()
    for entry in model_list:
        if not isinstance(entry, Mapping):
            continue
        params = entry.get("litellm_params", {}) or {}
        if not isinstance(params, Mapping):
            params = {}
        names = {
            str(entry.get("model_name") or "").strip(),
            str(params.get("model") or "").strip(),
        }
        if normalized_model not in names:
            continue
        model_info = entry.get("model_info", {}) or {}
        if not isinstance(model_info, Mapping):
            model_info = {}
        surface = str(model_info.get("dsa_api_surface") or "chat_completions").strip().lower()
        surfaces.add(surface)
    if len(surfaces) == 1:
        surface = next(iter(surfaces))
        if surface in {"responses", "chat_completions"}:
            return surface
    if len(surfaces) > 1:
        return "unknown"
    return None


def _first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _infer_api_surface(family: str, api_base: Optional[str]) -> ApiSurface:
    return "chat_completions" if family == "deepseek" else "unknown"


def _infer_gateway(api_base: Optional[str], family: str) -> Optional[str]:
    return None


def _infer_cloud_platform(api_base: Optional[str], family: str) -> CloudPlatform:
    return "none"




def _api_base_host(api_base: Optional[str]) -> str:
    text = (api_base or "").strip().lower()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    return (parsed.hostname or "").strip(".")
