# -*- coding: utf-8 -*-
"""Watchlist batch alert helpers for Alert Center P6."""

from __future__ import annotations

from data_provider.base import canonical_stock_code, normalize_stock_code

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List


logger = logging.getLogger(__name__)

SYMBOL_BATCH_TARGET_SCOPES = frozenset({"watchlist"})

EXPANDED_TARGET_SOFT_CAP = 100
TARGET_RESULTS_LIMIT = 20
DRY_RUN_TARGET_TIMEOUT_SECONDS = 10
DRY_RUN_TOTAL_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class ExpandedSymbolTarget:
    """A concrete symbol produced from a parent batch rule."""

    symbol: str
    display_target: str


@dataclass(frozen=True)
class RuntimeAlertPayload:
    """Runtime rule plus the identity used for cooldown/history."""

    key: str
    rule: Any
    effective_target: str
    display_target: str


@dataclass
class StaticAlertEvaluation:
    """Runtime placeholder for skipped/degraded expansion results."""

    stock_code: str
    alert_type: str
    message: str
    record_status: str = "skipped"
    metadata: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


def normalize_batch_target_scope_target(target_scope: str, target: str) -> str:
    target_text = str(target or "").strip()
    if target_scope == "watchlist":
        if target_text not in {"", "default"}:
            raise ValueError("watchlist target must be default")
        return "default"
    return target_text


def expand_symbol_targets(
    *,
    target_scope: str,
    target: str,
    config: Any,
) -> tuple[List[ExpandedSymbolTarget], int]:
    """Expand watchlist into concrete, de-duplicated symbols.

    Returns ``(targets, overflow_count)``. The returned targets are already capped
    by ``EXPANDED_TARGET_SOFT_CAP``.
    """

    if target_scope == "watchlist":
        symbols = _watchlist_symbols(config)
        display_prefix = "自选股"
    else:
        return [], 0

    unique = _dedupe_symbols(symbols)
    overflow_count = max(0, len(unique) - EXPANDED_TARGET_SOFT_CAP)
    capped = unique[:EXPANDED_TARGET_SOFT_CAP]
    return [
        ExpandedSymbolTarget(symbol=symbol, display_target=f"{display_prefix} - {symbol}")
        for symbol in capped
    ], overflow_count


def make_static_payload(
    *,
    parent_key: str,
    rule_id: int,
    alert_type: str,
    effective_target: str,
    display_target: str,
    message: str,
    record_status: str = "skipped",
) -> RuntimeAlertPayload:
    rule = StaticAlertEvaluation(
        stock_code=effective_target,
        alert_type=alert_type,
        message=message,
        record_status=record_status,
        metadata={
            "persisted_rule_id": rule_id,
            "effective_target": effective_target,
            "display_target": display_target,
        },
        description=message,
    )
    return RuntimeAlertPayload(
        key=f"{parent_key}|{effective_target}",
        rule=rule,
        effective_target=effective_target,
        display_target=display_target,
    )


def evaluate_static_alert(rule: StaticAlertEvaluation) -> Dict[str, Any]:
    return {
        "rule_id": int(rule.metadata.get("persisted_rule_id", 0) or 0),
        "status": "not_triggered",
        "record_status": rule.record_status,
        "triggered": False,
        "observed_value": None,
        "threshold": None,
        "data_source": None,
        "data_timestamp": None,
        "reason": rule.message,
        "message": rule.message,
    }


def result_to_target_result(payload: RuntimeAlertPayload, result: Dict[str, Any]) -> Dict[str, Any]:
    record_status = result.get("record_status")
    return {
        "target": payload.effective_target,
        "display_target": payload.display_target,
        "status": result.get("status") or "evaluation_error",
        "record_status": record_status,
        "triggered": bool(result.get("triggered")),
        "observed_value": result.get("observed_value"),
        "threshold": result.get("threshold"),
        "message": result.get("message") or result.get("reason") or "",
    }


def aggregate_dry_run_results(rule_id: int, target_scope: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    target_results = sorted(
        results,
        key=lambda item: (
            0 if item.get("triggered") else 1,
            0 if item.get("record_status") in {"degraded", "failed"} else 1,
            str(item.get("target") or ""),
        ),
    )
    visible_results = target_results[:TARGET_RESULTS_LIMIT]
    triggered_count = sum(1 for item in target_results if item.get("triggered"))
    degraded_count = sum(1 for item in target_results if item.get("record_status") == "degraded")
    skipped_count = sum(1 for item in target_results if item.get("record_status") == "skipped")
    failed_count = sum(1 for item in target_results if item.get("record_status") == "failed")
    successful_count = sum(
        1
        for item in target_results
        if item.get("record_status") not in {"failed"} and item.get("status") != "evaluation_error"
    )

    if triggered_count:
        status = "triggered"
        triggered = True
    elif successful_count or skipped_count or degraded_count:
        status = "not_triggered"
        triggered = False
    else:
        status = "evaluation_error"
        triggered = False

    if not target_results:
        status = "evaluation_error"
        triggered = False
        message = "No targets were evaluated"
    else:
        message = (
            f"Evaluated {len(target_results)} targets: "
            f"{triggered_count} triggered, {degraded_count} degraded, "
            f"{skipped_count} skipped, {failed_count} failed"
        )

    first_observed = next((item.get("observed_value") for item in target_results if item.get("observed_value") is not None), None)
    return {
        "rule_id": rule_id,
        "target_scope": target_scope,
        "status": status,
        "triggered": triggered,
        "observed_value": first_observed,
        "message": message,
        "evaluated_count": len(target_results),
        "triggered_count": triggered_count,
        "degraded_count": degraded_count,
        "skipped_count": skipped_count,
        "target_results": visible_results,
    }


def _watchlist_symbols(config: Any) -> List[str]:
    refresh = getattr(config, "refresh_stock_list", None)
    if callable(refresh):
        try:
            refresh()
        except Exception as exc:
            logger.warning("[watchlist_alerts] Failed to refresh watchlist symbols: %s", exc)
    return list(getattr(config, "stock_list", []) or [])


def _dedupe_symbols(symbols: Iterable[Any]) -> List[str]:
    output: List[str] = []
    seen = set()
    for raw in symbols:
        symbol = _normalize_symbol(raw)
        if not symbol or symbol in seen:
            continue
        output.append(symbol)
        seen.add(symbol)
    return output


def _normalize_symbol(value: Any) -> str:
    symbol = str(value or "")
    raw = canonical_stock_code(symbol)
    if not raw:
        return ""

    if len(raw) >= 8 and raw[:2] in {"SH", "SZ", "BJ"} and raw[2:].isdigit():
        return raw

    if "." in raw:
        base, suffix = raw.rsplit(".", 1)
        if base.isdigit() and suffix in {"SH", "SS", "SZ", "BJ"}:
            exchange = "SH" if suffix == "SS" else suffix
            return f"{exchange}{base}"

    return canonical_stock_code(normalize_stock_code(symbol))
