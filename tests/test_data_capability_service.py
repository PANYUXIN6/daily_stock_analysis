"""A-share-only data capability contracts."""

from src.services.data_capability_service import (
    _MARKET_OVERVIEW_PROVIDER_MARKETS,
    _PROVIDER_DEFINITIONS,
    _REALTIME_SOURCE_PROVIDER,
)


def test_every_provider_dataset_is_scoped_to_cn() -> None:
    assert _PROVIDER_DEFINITIONS
    for provider in _PROVIDER_DEFINITIONS:
        assert provider.markets == ("cn",)
        assert provider.dataset_markets
        assert all(tuple(markets) == ("cn",) for markets in provider.dataset_markets.values())


def test_capability_registry_contains_no_overseas_providers() -> None:
    provider_names = {provider.name for provider in _PROVIDER_DEFINITIONS}
    assert provider_names == {
        "efinance",
        "akshare",
        "tencent",
        "pytdx",
        "baostock",
        "tushare",
        "tickflow",
    }
    assert set(_REALTIME_SOURCE_PROVIDER.values()) <= provider_names


def test_market_overview_capabilities_are_cn_only() -> None:
    assert _MARKET_OVERVIEW_PROVIDER_MARKETS
    assert all(markets == {"cn"} for markets in _MARKET_OVERVIEW_PROVIDER_MARKETS.values())
