"""Focused routing tests for registered A-share indices."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from data_provider.base import DataFetchError, DataFetcherManager
from src.services.stock_list_parser import ParseStatus, parse_analysis_target


def _daily_frame() -> pd.DataFrame:
    return pd.DataFrame([{
        "date": "2026-08-21",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1000,
        "amount": 100_000.0,
        "pct_chg": 0.5,
    }])


class _FakeFetcher:
    def __init__(self, name: str, result) -> None:
        self.name = name
        self.priority = 1
        self.result = result
        self.calls: list[str] = []

    def is_available_for_request(self, capability: str = "") -> bool:
        return True

    def get_daily_data(self, stock_code: str, **_kwargs):
        self.calls.append(stock_code)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result.copy()


@pytest.mark.parametrize("code", ["csi930956", "930956.CSI"])
def test_unregistered_csi_is_rejected_before_provider_calls(code: str) -> None:
    fetcher = _FakeFetcher("AkshareFetcher", _daily_frame())
    manager = DataFetcherManager(fetchers=[fetcher])
    with pytest.raises(DataFetchError, match="unregistered CSI index"):
        manager.get_daily_data(code)
    assert fetcher.calls == []


def test_registered_index_uses_a_share_provider_order() -> None:
    tencent = _FakeFetcher("TencentFetcher", RuntimeError("unavailable"))
    akshare = _FakeFetcher("AkshareFetcher", _daily_frame())
    tickflow = _FakeFetcher("TickFlowFetcher", _daily_frame())
    manager = DataFetcherManager(fetchers=[tickflow, akshare, tencent])

    with patch("data_provider.base.record_provider_run"):
        frame, source = manager.get_daily_data("sh000016")

    assert not frame.empty
    assert source == "AkshareFetcher"
    assert tencent.calls == ["sh000016"]
    assert akshare.calls == ["sh000016"]
    assert tickflow.calls == []


def test_csi_index_only_maps_to_akshare() -> None:
    target = parse_analysis_target("csi930955")
    assert target.asset_type == ParseStatus.INDEX
    assert DataFetcherManager._cn_index_provider_symbol(target, "AkshareFetcher") == "csi930955"
    assert DataFetcherManager._cn_index_provider_symbol(target, "TencentFetcher") == ""
    assert DataFetcherManager._cn_index_provider_symbol(target, "TickFlowFetcher") == ""
