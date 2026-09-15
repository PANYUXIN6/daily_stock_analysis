# -*- coding: utf-8 -*-
"""A-share-only contracts for stock-code normalization."""

import pytest

from src.services.stock_code_utils import (
    build_daily_code_candidates,
    is_code_like,
    normalize_code,
    resolve_daily_stock_identity,
    resolve_index_stock_code_for_analysis,
)


@pytest.mark.parametrize(
    "raw",
    [
        "600519",
        "SH600519",
        "SH.600519",
        "600519.SH",
        "600519.SS",
        "SZ000001",
        "000001.SZ",
        "BJ920748",
        "920748.BJ",
    ],
)
def test_accepts_a_share_code_forms(raw: str) -> None:
    assert is_code_like(raw)
    assert normalize_code(raw) in {"600519", "000001", "920748"}


@pytest.mark.parametrize(
    "raw",
    [
        "AAPL",
        "AAPL.US",
        "HK00700",
        "00700.HK",
        "7203.T",
        "005930.KS",
        "600519.SZ",
        "000001.SH",
        "BJ600519",
        "",
        "贵州茅台",
    ],
)
def test_rejects_non_a_share_or_conflicting_exchange(raw: str) -> None:
    assert not is_code_like(raw)
    assert normalize_code(raw) is None
    assert build_daily_code_candidates(raw) == []


def test_one_identity_drives_a_share_lookup_candidates() -> None:
    identity = resolve_daily_stock_identity("600519.SH")

    assert identity is not None
    assert identity.normalized_code == "600519"
    assert identity.market == "cn"
    assert identity.refill_code == "600519"
    assert {
        "600519.SH",
        "600519",
        "SH600519",
        "SH.600519",
        "SS600519",
    } <= set(identity.code_candidates)


def test_beijing_identity_uses_bj_variants() -> None:
    assert set(build_daily_code_candidates("920748")) == {
        "920748",
        "BJ920748",
        "BJ.920748",
        "920748.BJ",
    }


def test_non_cn_market_hint_fails_closed() -> None:
    assert resolve_daily_stock_identity("600519", market_hint="us") is None


def test_registered_index_alias_is_preserved_for_analysis() -> None:
    assert resolve_index_stock_code_for_analysis("000300.SH") == "sh000300"


def test_unknown_value_falls_back_to_uppercase_text() -> None:
    assert resolve_index_stock_code_for_analysis("unknown") == "UNKNOWN"
