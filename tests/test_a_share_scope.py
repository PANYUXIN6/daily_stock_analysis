"""Focused contract tests for the A-share-only product boundary."""

import pytest

from src.core.market_strategy import get_market_strategy_blueprint
from src.agent.stock_scope import resolve_stock_scope
from src.services.stock_code_utils import is_code_like, normalize_code
from src.services.stock_list_parser import ParseStatus, parse_analysis_target


@pytest.mark.parametrize("code", ["600519", "000858", "300750", "920493"])
def test_supported_a_share_codes_normalize_to_six_digits(code: str) -> None:
    assert is_code_like(code)
    assert normalize_code(code) == code


@pytest.mark.parametrize("code", ["AAPL", "00700", "7203.T", "2330.TW", "005930.KS"])
def test_overseas_code_shapes_are_rejected(code: str) -> None:
    assert not is_code_like(code)
    assert normalize_code(code) is None
    assert parse_analysis_target(code).asset_type == ParseStatus.UNSUPPORTED


def test_market_strategy_only_accepts_cn() -> None:
    assert get_market_strategy_blueprint("cn").region == "cn"
    with pytest.raises(ValueError, match="仅支持 A 股"):
        get_market_strategy_blueprint("us")


def test_agent_scope_switches_between_a_shares() -> None:
    result = resolve_stock_scope("换成 300750 看看", {"stock_code": "600519"})
    assert result.stock_scope is not None
    assert result.stock_scope.mode == "switch"
    assert result.stock_scope.expected_stock_code == "300750"
    assert result.stock_scope.allowed_stock_codes == {"300750"}


def test_agent_scope_compares_multiple_a_shares() -> None:
    result = resolve_stock_scope("比较 600519 和 300750", {"stock_code": "600519"})
    assert result.stock_scope is not None
    assert result.stock_scope.mode == "compare"
    assert result.stock_scope.allowed_stock_codes == {"600519", "300750"}


def test_agent_scope_drops_non_a_share_context() -> None:
    result = resolve_stock_scope(
        "继续看",
        {"stock_code": "HK", "stock_name": "境外标的"},
    )
    assert result.stock_scope is not None
    assert result.stock_scope.allowed_stock_codes == set()
    assert "stock_code" not in result.effective_context
    assert "stock_name" not in result.effective_context


def test_agent_scope_does_not_switch_to_foreign_ticker() -> None:
    result = resolve_stock_scope("换成 AAPL 看看", {"stock_code": "600519"})
    assert result.stock_scope is not None
    assert result.stock_scope.mode == "maintain"
    assert result.stock_scope.allowed_stock_codes == {"600519"}
