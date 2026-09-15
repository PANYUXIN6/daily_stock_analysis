# -*- coding: utf-8 -*-
"""A-share-only contracts for analysis-target parsing."""

import pytest

from src.services.stock_list_parser import (
    IndexEntry,
    IndexRegistry,
    ParseStatus,
    default_index_registry,
    parse_analysis_target,
    parse_stock_list,
    serialize_stock_list,
    split_stock_list,
)


@pytest.fixture
def registry() -> IndexRegistry:
    return IndexRegistry(
        (
            IndexEntry(
                bare_code="000300",
                exchange="SH",
                canonical_id="sh000300",
                display_name="沪深300",
                aliases=("000300.SH", "sz399300", "399300.SZ"),
            ),
            IndexEntry(
                bare_code="399006",
                exchange="SZ",
                canonical_id="sz399006",
                display_name="创业板指",
                aliases=("399006.SZ",),
            ),
            IndexEntry(
                bare_code="930955",
                exchange="CSI",
                canonical_id="csi930955",
                display_name="红利低波100",
                aliases=("930955.CSI",),
            ),
        )
    )


def test_split_and_serialize_common_separators() -> None:
    value = "600519，300750  000001;920748、sh000300\n002594"
    assert split_stock_list(value) == [
        "600519",
        "300750",
        "000001",
        "920748",
        "sh000300",
        "002594",
    ]
    assert serialize_stock_list(value) == "600519,300750,000001,920748,sh000300,002594"


@pytest.mark.parametrize(
    ("raw", "exchange"),
    [
        ("600519", "SH"),
        ("000001", "SZ"),
        ("300750", "SZ"),
        ("920748", "BJ"),
        ("SH600519", "SH"),
        ("000001.SZ", "SZ"),
    ],
)
def test_parses_a_share_stocks(raw: str, exchange: str, registry: IndexRegistry) -> None:
    target = parse_analysis_target(raw, registry=registry)
    assert target.asset_type == ParseStatus.STOCK
    assert target.exchange == exchange
    assert target.normalized_code is not None


def test_bare_index_code_stays_on_stock_route(registry: IndexRegistry) -> None:
    target = parse_analysis_target("000300", registry=registry)
    assert target.asset_type == ParseStatus.STOCK
    assert target.canonical_id == "000300"
    assert target.matched_index is not None
    assert target.matched_index.canonical_id == "sh000300"


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("sh000300", "sh000300"),
        ("000300.SH", "sh000300"),
        ("sz399300", "sh000300"),
        ("sz399006", "sz399006"),
        ("csi930955", "csi930955"),
        ("930955.CSI", "csi930955"),
    ],
)
def test_registered_explicit_indices_resolve(
    raw: str,
    canonical: str,
    registry: IndexRegistry,
) -> None:
    target = parse_analysis_target(raw, registry=registry)
    assert target.asset_type == ParseStatus.INDEX
    assert target.canonical_id == canonical


def test_unregistered_csi_is_rejected(registry: IndexRegistry) -> None:
    target = parse_analysis_target("csi930956", registry=registry)
    assert target.asset_type == ParseStatus.UNSUPPORTED
    assert "unregistered CSI index" in (target.unsupported_reason or "")


@pytest.mark.parametrize(
    "raw",
    ["AAPL", "AAPL.US", "HK00700", "00700.HK", "7203.T", "005930.KS", "600519.SZ", ""],
)
def test_rejects_non_a_share_or_invalid_input(raw: str, registry: IndexRegistry) -> None:
    assert parse_analysis_target(raw, registry=registry).asset_type == ParseStatus.UNSUPPORTED


def test_registry_keeps_name_lookup_separate_from_identity(registry: IndexRegistry) -> None:
    assert registry.find_by_display_name("沪深300") is not None
    assert registry.find_by_explicit_key("沪深300") is None
    assert parse_analysis_target("沪深300", registry=registry).asset_type == ParseStatus.UNSUPPORTED


def test_registry_rejects_non_explicit_alias() -> None:
    with pytest.raises(ValueError, match="explicit A-share form"):
        IndexRegistry(
            (
                IndexEntry(
                    bare_code="000300",
                    exchange="SH",
                    canonical_id="sh000300",
                    display_name="沪深300",
                    aliases=("CSI300",),
                ),
            )
        )


def test_default_registry_contains_mainland_indices() -> None:
    ids = {entry.canonical_id for entry in default_index_registry()}
    assert {"sh000300", "sh000016", "sz399006", "csi930955"} <= ids


def test_parse_stock_list_returns_one_result_per_token(registry: IndexRegistry) -> None:
    targets = parse_stock_list("sh000300,600519,AAPL,920748", registry=registry)
    assert [target.asset_type for target in targets] == [
        ParseStatus.INDEX,
        ParseStatus.STOCK,
        ParseStatus.UNSUPPORTED,
        ParseStatus.STOCK,
    ]


def test_analysis_target_is_hashable(registry: IndexRegistry) -> None:
    hash(parse_analysis_target("sh000300", registry=registry))
