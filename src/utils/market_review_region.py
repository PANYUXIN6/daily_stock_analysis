# -*- coding: utf-8 -*-
"""Shared normalization rules for market-review region values."""

from typing import Optional


MARKET_REVIEW_REGION_ORDER = ("cn",)
MARKET_REVIEW_REGION_SET = frozenset(MARKET_REVIEW_REGION_ORDER)
MARKET_REVIEW_REGION_ALL = ",".join(MARKET_REVIEW_REGION_ORDER)
MARKET_REVIEW_REGION_VALID_INPUTS = MARKET_REVIEW_REGION_ORDER


def normalize_market_review_region_lenient(value: Optional[str]) -> Optional[str]:
    """Normalize persistent config input for the A-share-only runtime."""

    normalized = str(value or "cn").strip().lower()
    if normalized in MARKET_REVIEW_REGION_SET:
        return normalized
    return None


def normalize_market_review_region_strict(value: str) -> str:
    """Validate and canonicalize a request-scoped market-review region.

    Request input is fail-fast and accepts only ``cn``.
    """

    normalized = value.strip().lower()
    valid_hint = ", ".join(MARKET_REVIEW_REGION_VALID_INPUTS)
    if not normalized:
        raise ValueError(f"region 不能为空；合法值：{valid_hint}")

    tokens = [token.strip() for token in normalized.split(",")]
    if any(not token for token in tokens):
        raise ValueError(f"region 不能包含空项；合法值：{valid_hint}")

    invalid_tokens = sorted({token for token in tokens if token not in MARKET_REVIEW_REGION_SET})
    if invalid_tokens:
        raise ValueError(
            f"region 包含非法值：{', '.join(invalid_tokens)}；合法值：{valid_hint}"
        )

    if len(tokens) != 1:
        raise ValueError(f"region 仅支持 cn；收到：{normalized}")
    return "cn"
