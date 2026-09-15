"""A-share stock-index generation contracts."""

import json

import pytest

from scripts.generate_index_from_csv import (
    build_index_entries_from_seed,
    compress_index,
    determine_market,
    extract_symbol_from_ts_code,
    load_index_registry_seed,
    parse_stock_row,
    validate_index_registry,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("000001.SZ", "000001"), ("600519.SH", "600519"), ("920493.BJ", "920493")],
)
def test_extracts_a_share_display_code(raw: str, expected: str) -> None:
    assert extract_symbol_from_ts_code(raw, "CN") == expected


@pytest.mark.parametrize("raw", ["00700.HK", "AAPL", "7203.T", "005930.KS"])
def test_rejects_overseas_market_codes(raw: str) -> None:
    assert determine_market(raw) == ""
    assert parse_stock_row({"ts_code": raw, "name": "unsupported"}) is None


def test_parses_a_share_row_and_strips_temporary_ex_rights_prefix() -> None:
    item = parse_stock_row({"ts_code": "600519.SH", "name": "XD贵州茅台"})
    assert item == {
        "ts_code": "600519.SH",
        "symbol": "600519",
        "name": "贵州茅台",
        "market": "CN",
        "aliases": [],
    }


def test_compressed_stock_index_is_serializable_and_cn_only() -> None:
    rows = compress_index([
        {
            "canonicalCode": "600519.SH",
            "displayCode": "600519",
            "nameZh": "贵州茅台",
            "pinyinFull": "guizhoumaotai",
            "pinyinAbbr": "gzmt",
            "aliases": ["茅台"],
            "market": "CN",
            "assetType": "stock",
            "active": True,
            "popularity": 100,
        }
    ])
    assert len(rows[0]) == 10
    assert rows[0][6] == "CN"
    json.dumps(rows, ensure_ascii=False)


def test_registered_a_share_indices_pass_semantic_validation() -> None:
    entries = build_index_entries_from_seed(load_index_registry_seed())
    assert entries
    assert {entry["market"] for entry in entries} == {"CN"}
    validate_index_registry(entries)


def test_index_validation_rejects_non_cn_market() -> None:
    entry = build_index_entries_from_seed(load_index_registry_seed())[0]
    entry["market"] = "US"
    with pytest.raises(ValueError, match="market must be CN"):
        validate_index_registry([entry])
