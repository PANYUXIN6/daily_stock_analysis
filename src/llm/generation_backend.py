# -*- coding: utf-8 -*-
"""Shared generation backend contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, Protocol


class GenerationErrorCode(str, Enum):
    """Structured generation backend error codes.

    Used by cloud model generation and route validation.
    """

    INVALID_JSON = "invalid_json"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    UNSUPPORTED_TOOL_CALLING = "unsupported_tool_calling"
    UNSAFE_CONFIG = "unsafe_config"


@dataclass(frozen=True)
class GenerationCapabilities:
    """Backend capability flags surfaced to resolvers and diagnostics."""

    supports_json: bool
    supports_tools: bool
    supports_stream: bool
    supports_vision: bool
    supports_health_check: bool
    supports_smoke_test: bool


@dataclass
class GenerationResult:
    """Normalized result returned by generation backends."""

    text: str
    model: str
    provider: str
    backend: str
    usage: Dict[str, Any]
    raw: Any = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationError(Exception):
    """Structured generation backend failure.

    ``stage`` is intentionally descriptive rather than a closed enum. Current
    generation paths use values such as ``generation``, ``configuration``,
    ``execution``, ``validation``, and ``fallback``.
    """

    error_code: GenerationErrorCode
    stage: str
    retryable: bool
    fallbackable: bool
    backend: str
    provider: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider:
            self.provider = self.backend
        Exception.__init__(self, self.message)

    @property
    def message(self) -> str:
        return f"{self.error_code.value} at {self.stage} for backend {self.backend}"


class GenerationBackend(Protocol):
    """Protocol implemented by generation backends."""

    backend_id: str
    capabilities: GenerationCapabilities

    def generate(
        self,
        prompt: str,
        generation_config: Dict[str, Any],
        *,
        system_prompt: Optional[str] = None,
        stream: bool = False,
        stream_progress_callback: Optional[Callable[[int], None]] = None,
        response_validator: Optional[Callable[[str], None]] = None,
        audit_context: Optional[Dict[str, Any]] = None,
    ) -> GenerationResult:
        """Generate text with the backend."""
