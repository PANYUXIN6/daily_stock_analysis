# -*- coding: utf-8 -*-
"""Agent-safe LiteLLM route resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.llm.route_identity import route_identity_candidates
from src.config import (
    get_effective_agent_models_to_try,
    get_effective_agent_primary_model,
)


@dataclass(frozen=True)
class AgentLiteLLMRouteResolution:
    available: bool
    primary_model: str = ""
    models_to_try: List[str] = field(default_factory=list)
    model_list: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""


def _matched_route_alias(model: str, provenance: Dict[str, Any]) -> str:
    for candidate in route_identity_candidates(model):
        if candidate in provenance:
            return candidate
    return (model or "").strip()


def resolve_agent_litellm_route(config: Any) -> AgentLiteLLMRouteResolution:
    """Resolve the Agent LiteLLM route using configured cloud models."""


    primary = get_effective_agent_primary_model(config)
    if not primary:
        return AgentLiteLLMRouteResolution(False, reason="no_agent_primary")

    model_list = list(getattr(config, "llm_model_list", []) or [])
    provenance = {str(entry.get("model_name") or ""): entry for entry in model_list}
    filtered_model_list = model_list

    safe_models: List[str] = []
    seen = set()
    for model in get_effective_agent_models_to_try(config):
        normalized = (model or "").strip()
        if not normalized or normalized in seen:
            continue
        safe_model = _matched_route_alias(normalized, provenance)
        if safe_model in seen:
            continue
        seen.add(safe_model)
        safe_models.append(safe_model)

    if not safe_models:
        return AgentLiteLLMRouteResolution(
            False,
            primary_model=primary,
            model_list=filtered_model_list,
            reason="no_safe_agent_models",
        )

    return AgentLiteLLMRouteResolution(
        True,
        primary_model=safe_models[0],
        models_to_try=safe_models,
        model_list=filtered_model_list,
        reason="",
    )
