# -*- coding: utf-8 -*-
"""A-share stock-code normalization shared by runtime entry points."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import List, Optional

_CN_PREFIXES = ("SH", "SZ", "SS", "BJ")
_CN_SUFFIXES = tuple(f".{exchange}" for exchange in _CN_PREFIXES)


@dataclass(frozen=True)
class DailyStockIdentity:
    """One A-share identity shared by daily-bar lookup and refill."""

    normalized_code: str
    market: str
    refill_code: str
    code_candidates: tuple[str, ...]


def _is_bse_code(code: str) -> bool:
    normalized = (code or "").strip().split(".")[0]
    if len(normalized) != 6 or not normalized.isdigit() or normalized.startswith("900"):
        return False
    return normalized.startswith(("92", "43", "81", "82", "83", "87", "88"))


def _infer_cn_exchange(code: str) -> str:
    if not (code.isdigit() and len(code) == 6):
        return ""
    if _is_bse_code(code):
        return "BJ"
    if code.startswith(("5", "6", "9")):
        return "SH"
    return "SZ"


def _split_explicit_exchange(text: str) -> Optional[tuple[str, str]]:
    for suffix in _CN_SUFFIXES:
        if text.endswith(suffix):
            return suffix[1:], text[: -len(suffix)].strip()
    for prefix in _CN_PREFIXES:
        dotted = f"{prefix}."
        if text.startswith(dotted):
            return prefix, text[len(dotted):]
        if text.startswith(prefix):
            return prefix, text[len(prefix):]
    return None


def _valid_exchange_code(exchange: str, code: str) -> bool:
    if not (code.isdigit() and len(code) == 6):
        return False
    inferred = _infer_cn_exchange(code)
    if exchange in {"SH", "SS"}:
        return inferred == "SH"
    return inferred == exchange


def is_code_like(value: str) -> bool:
    """Return whether ``value`` is a six-digit A-share/security code."""
    normalized, _ = _normalize_code_and_exchange(value)
    return normalized is not None


def normalize_code(raw: str) -> Optional[str]:
    """Normalize an A-share code to its six-digit form."""
    normalized, _ = _normalize_code_and_exchange(raw)
    return normalized


def _normalize_code_and_exchange(raw: str) -> tuple[Optional[str], str]:
    """Normalize one Shanghai, Shenzhen, or Beijing code."""
    text = unicodedata.normalize("NFKC", str(raw or "")).strip().upper()
    if not text:
        return None, ""
    if text.isdigit():
        return (text, "") if len(text) == 6 else (None, "")
    explicit = _split_explicit_exchange(text)
    if explicit is None:
        return None, ""
    exchange, code = explicit
    if not _valid_exchange_code(exchange, code):
        return None, exchange
    return code, exchange


def _market_variants(code: str, exchange: str) -> List[str]:
    canonical_exchange = "SH" if exchange == "SS" else exchange
    variants = [
        code,
        f"{canonical_exchange}{code}",
        f"{canonical_exchange}.{code}",
        f"{code}.{canonical_exchange}",
    ]
    if canonical_exchange == "SH":
        variants.extend((f"SS{code}", f"SS.{code}", f"{code}.SS"))
    return variants


def resolve_daily_stock_identity(
    code: Optional[str],
    *,
    market_hint: Optional[str] = None,
) -> Optional[DailyStockIdentity]:
    """Resolve one A-share identity for local daily-bar consumers."""
    if market_hint and str(market_hint).strip().lower() != "cn":
        return None
    raw = str(code or "").strip().upper()
    normalized, explicit_exchange = _normalize_code_and_exchange(raw)
    if normalized is None:
        return None
    exchange = explicit_exchange or _infer_cn_exchange(normalized)
    if not exchange:
        return None
    candidates = tuple(dict.fromkeys([raw, *_market_variants(normalized, exchange)]))
    return DailyStockIdentity(
        normalized_code=normalized,
        market="cn",
        refill_code=normalized,
        code_candidates=candidates,
    )


def build_daily_code_candidates(code: Optional[str]) -> List[str]:
    identity = resolve_daily_stock_identity(code)
    return list(identity.code_candidates) if identity is not None else []


def resolve_index_stock_code_for_analysis(raw: str) -> str:
    """Resolve one registered A-share index or normalize one A-share security."""
    text = str(raw or "").strip()
    if not text:
        return ""

    from src.services.stock_list_parser import ParseStatus, parse_analysis_target

    target = parse_analysis_target(text)
    if target.asset_type == ParseStatus.INDEX and target.canonical_id:
        return target.canonical_id
    if target.asset_type == ParseStatus.STOCK and target.normalized_code:
        return target.normalized_code
    return unicodedata.normalize("NFKC", text).strip().upper()
