# -*- coding: utf-8 -*-
"""Stock-scope helpers for ask-stock follow-up chat turns."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set


SWITCH_CLEANUP_KEYS = {
    "stock_name",
    "previous_analysis_summary",
    "previous_strategy",
    "previous_price",
    "previous_change_pct",
    "realtime_quote",
    "daily_history",
    "trend_result",
    "news_context",
    "fundamental_context",
    "market_structure_context",
    "analysis_context_pack_summary",
    "market_phase_context",
}

_STRONG_COMPARE_PATTERN = re.compile(r"比较|对比|vs\b|和[^，。,.!?！？]{0,40}比", re.IGNORECASE)
_WEAK_COMPARE_HINT_PATTERN = re.compile(r"差异(?!化)|区别|不同|相比|对照|比一比")
_CHOICE_COMPARE_PATTERN = re.compile(r"哪个|哪只|哪一个|谁更|更值得|更适合|怎么选|选哪|二选一")
_LINKED_COMPARE_PATTERN = re.compile(
    r"(?:和|与|跟|同)(?P<body>[^，。,.!?！？]{0,40})(?:差异(?!化)|区别|不同|相比|对照|比一比)"
)
_SWITCH_PATTERN = re.compile(r"换成|改看|分析|看看|研究|诊断")
_EXCHANGE_TOKEN_CANDIDATES = {"SH", "SZ", "BJ", "SS"}
_CONTEXTUAL_INDICATOR_TOKENS = {"MA"}
_INDICATOR_CONTEXT_PATTERN = re.compile(
    r"指标|均线|移动平均|排列|多头|空头|金叉|死叉|支撑|压力|MA\d|SMA|EMA",
    re.IGNORECASE,
)

# Match complete explicit SH/SZ/CSI tokens; the registry parser remains the
# only authority that can promote a match to index identity.
_INDEX_TOKEN_PATTERNS = (
    (r"(?<![a-zA-Z0-9_])(?:sh|sz)\d{6}(?![a-zA-Z0-9_])", re.IGNORECASE),
    (r"(?<![a-zA-Z0-9_])csi\d{6}(?![a-zA-Z0-9_])", re.IGNORECASE),
    (
        r"(?<![a-zA-Z0-9_])\d{6}\.(?:sh|sz|csi)(?![a-zA-Z0-9_])",
        re.IGNORECASE,
    ),
)


def _extract_index_canonical_tokens(
    text: str,
    registry: Any,
) -> "tuple[list[tuple[int, int]], list[str]]":
    """Return full spans and canonicals for exact registered index tokens."""
    spans: List[tuple[int, int]] = []
    canonicals: List[str] = []
    for pattern, flags in _INDEX_TOKEN_PATTERNS:
        for match in re.finditer(pattern, text, flags):
            raw = match.group(0)
            try:
                from src.services.stock_list_parser import (
                    ParseStatus,
                    parse_analysis_target,
                )

                target = parse_analysis_target(raw, registry)
            except Exception:
                continue
            if target.asset_type != ParseStatus.INDEX:
                continue
            if not target.canonical_id:
                continue
            start, end = match.span()
            if any(s <= start and end <= e for s, e in spans):
                continue
            spans.append((start, end))
            canonicals.append(target.canonical_id)
    return spans, canonicals


def _is_inside_index_span(start: int, end: int, spans: List[tuple[int, int]]) -> bool:
    return any(span_start <= start and end <= span_end for span_start, span_end in spans)


def _has_ascii_token_boundaries(text: str, start: int, end: int) -> bool:
    def _is_word_char(char: str) -> bool:
        return bool(char) and char.isascii() and (char.isalnum() or char == "_")

    return (
        not _is_word_char(text[start - 1:start])
        and not _is_word_char(text[end:end + 1])
    )


@dataclass(frozen=True)
class StockScope:
    """Runtime stock-scope contract for one chat turn."""

    expected_stock_code: str = ""
    allowed_stock_codes: Set[str] = field(default_factory=set)
    mode: str = "maintain"

    def as_log_payload(self) -> Dict[str, Any]:
        return {
            "expected_stock_code": self.expected_stock_code,
            "allowed_stock_codes": sorted(self.allowed_stock_codes),
            "mode": self.mode,
        }


@dataclass(frozen=True)
class StockScopeResolution:
    """Result produced before a chat turn enters the agent loop."""

    effective_context: Dict[str, Any]
    stock_scope: Optional[StockScope]


def _normalize_stock_code(value: Any, registry: Optional[Any] = None) -> str:
    """Normalize an A-share code, preserving registered index canonicals."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    try:
        from src.services.stock_list_parser import ParseStatus, parse_analysis_target

        target = parse_analysis_target(text, registry)
    except Exception:
        return ""
    if target.asset_type == ParseStatus.INDEX:
        return target.canonical_id
    if target.asset_type == ParseStatus.STOCK:
        return target.normalized_code or ""
    return ""


def _is_denied_candidate(candidate: str, text: str = "") -> bool:
    token = candidate.strip().upper()
    if token in _EXCHANGE_TOKEN_CANDIDATES:
        return True
    if token in _CONTEXTUAL_INDICATOR_TOKENS and _INDICATOR_CONTEXT_PATTERN.search(text or ""):
        return True
    return False


def _append_candidate(
    candidates: List[str],
    candidate: str,
    text: str = "",
    registry: Optional[Any] = None,
) -> None:
    normalized = _normalize_stock_code(candidate, registry)
    if not normalized or _is_denied_candidate(normalized, text):
        return
    if normalized not in candidates:
        candidates.append(normalized)


def extract_stock_codes(text: str, registry: Optional[Any] = None) -> List[str]:
    """Extract candidates; no registry preserves the legacy stock-only path."""
    if not text:
        return []

    candidates: List[str] = []
    index_spans: List[tuple[int, int]] = []
    if registry is not None:
        index_spans, canonicals = _extract_index_canonical_tokens(text, registry)
        for canonical in canonicals:
            if canonical not in candidates:
                candidates.append(canonical)

    for pattern, flags in (
        (r"(?<![a-zA-Z])(?:SH|SZ|BJ)\d{6}(?!\d)", re.IGNORECASE),
        (r"(?<!\d)(?:[03648]\d{5}|92\d{4})(?!\d)", 0),
    ):
        for match in re.finditer(pattern, text, flags):
            start, end = match.span()
            if registry is not None and not _has_ascii_token_boundaries(text, start, end):
                continue
            if _is_inside_index_span(start, end, index_spans):
                continue
            raw = match.group(1) if match.lastindex else match.group(0)
            _append_candidate(candidates, raw, text, registry)

    return candidates


def _is_compare_message(
    message: str,
    candidates: List[str],
    current_code: str,
    registry: Optional[Any] = None,
) -> bool:
    if _STRONG_COMPARE_PATTERN.search(message):
        return True
    new_candidates = {code for code in candidates if code != current_code}
    if len(new_candidates) >= 2:
        return True
    if _CHOICE_COMPARE_PATTERN.search(message) and len(candidates) >= 2:
        return True
    if not _WEAK_COMPARE_HINT_PATTERN.search(message):
        return False
    if len(candidates) >= 2:
        return True

    if not new_candidates:
        return False

    for match in _LINKED_COMPARE_PATTERN.finditer(message):
        body_candidates = set(extract_stock_codes(f"比较 {match.group('body')}", registry))
        if body_candidates & new_candidates:
            return True
    return False


def _with_skills(context: Dict[str, Any], skills: Optional[Iterable[str]]) -> Dict[str, Any]:
    if skills is None:
        return context
    next_context = dict(context)
    next_context["skills"] = list(skills)
    return next_context


def _switch_context(context: Dict[str, Any], stock_code: str) -> Dict[str, Any]:
    next_context = {
        key: value
        for key, value in context.items()
        if key not in SWITCH_CLEANUP_KEYS and key != "allowed_stock_codes"
    }
    next_context["stock_code"] = stock_code
    next_context["stock_name"] = ""
    return next_context


def resolve_stock_scope(
    message: str,
    context: Optional[Dict[str, Any]],
    *,
    skills: Optional[Iterable[str]] = None,
    strict_initial_scope: bool = False,
    registry: Optional[Any] = None,
) -> StockScopeResolution:
    """Resolve one turn with a shared registry, failing open to stock semantics."""
    if registry is None:
        try:
            from src.services.stock_list_parser import IndexRegistry, default_index_registry

            registry = default_index_registry()
        except Exception:
            registry = IndexRegistry()

    original_context = dict(context or {})
    message_text = message or ""
    raw_context_code = original_context.get("stock_code")
    current_code = _normalize_stock_code(raw_context_code, registry)
    invalid_context_code = bool(
        isinstance(raw_context_code, str)
        and raw_context_code.strip()
        and not current_code
    ) or bool(current_code and _is_denied_candidate(current_code, message_text))
    original_context.pop("allowed_stock_codes", None)
    if invalid_context_code:
        original_context.pop("stock_code", None)
        original_context.pop("stock_name", None)
        current_code = ""

    if not current_code:
        if invalid_context_code or strict_initial_scope:
            candidates = extract_stock_codes(message_text, registry)
            if strict_initial_scope and not invalid_context_code and not candidates:
                return StockScopeResolution(
                    effective_context=_with_skills(original_context, skills),
                    stock_scope=None,
                )
            allowed = set(candidates)
            expected = candidates[0] if len(candidates) == 1 else ""
            effective_context = dict(original_context)
            mode = "switch" if expected else ("compare" if len(candidates) > 1 else "maintain")
            if expected:
                effective_context["stock_code"] = expected
                effective_context["stock_name"] = ""
            return StockScopeResolution(
                effective_context=_with_skills(effective_context, skills),
                stock_scope=StockScope(
                    expected_stock_code=expected,
                    allowed_stock_codes=allowed,
                    mode=mode,
                ),
            )
        return StockScopeResolution(
            effective_context=_with_skills(original_context, skills),
            stock_scope=None,
        )

    candidates = extract_stock_codes(message_text, registry)
    new_candidates = [code for code in candidates if code != current_code]
    mode = "maintain"
    effective_context = dict(original_context)
    expected = current_code
    allowed = {current_code}

    if _is_compare_message(message_text, candidates, current_code, registry):
        mode = "compare"
        allowed.update(candidates)
    elif _SWITCH_PATTERN.search(message_text) and len(new_candidates) == 1:
        mode = "switch"
        expected = new_candidates[0]
        allowed = {expected}
        effective_context = _switch_context(original_context, expected)

    effective_context["stock_code"] = expected if mode == "switch" else current_code
    effective_context = _with_skills(effective_context, skills)

    return StockScopeResolution(
        effective_context=effective_context,
        stock_scope=StockScope(
            expected_stock_code=expected,
            allowed_stock_codes=allowed,
            mode=mode,
        ),
    )
