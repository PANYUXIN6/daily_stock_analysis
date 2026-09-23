"""Offline acceptance scenarios for the three mandatory earnings-gap conditions."""

from copy import deepcopy

import pandas as pd
import pytest

from data_provider.gap_limit_up import GapLimitUpDataSource
from src.services.screening.models import GapLimitUpConfig
from src.services.screening.gap_limit_up import (
    check_price_gap, filter_gap_limit_up, volume_stage,
)


@pytest.fixture
def scenario():
    calendar = pd.bdate_range("2026-03-02", periods=21).strftime("%Y%m%d").tolist()
    bars = pd.DataFrame([
        dict(trade_date=day, open=10.0, high=10.2, low=9.9, close=10.0, vol=100.0, adj_factor=1.0, up_limit=11.0)
        for day in calendar
    ])
    for idx in range(20, 21):
        bars.loc[idx, ["open", "high", "low", "close", "vol", "up_limit"]] = [10.6, 11, 10.5, 10.9, 200, 12]
    bars.loc[20, ["close", "up_limit", "vol"]] = [11, 11, 500]
    return calendar, bars


def test_gap_and_limit_up_pass_without_financial_data(scenario):
    calendar, bars = scenario
    price = check_price_gap(bars, calendar, GapLimitUpConfig())
    assert price["gap_lower"] == 10.2
    assert price["observation_days"] == 0
    assert price["volume"]["stage"] == "当日放量，后续待观察"


@pytest.mark.parametrize("mutation,reason", [
    ("no_limit", "未收盘封涨停"),
    ("no_gap", "未形成完整"),
    ("missing_session", "行情不完整"),
    ("missing_factor", "非有限"),
])
def test_price_exclusions(scenario, mutation, reason):
    calendar, bars = scenario
    if mutation == "no_limit":
        bars.loc[20, "close"] = 10.95  # Intraday touch is insufficient.
    elif mutation == "no_gap":
        bars.loc[20, "low"] = 10.2
    elif mutation == "missing_session":
        bars = bars.drop(index=20)
    elif mutation == "missing_factor":
        bars.loc[20, "adj_factor"] = float("nan")
    with pytest.raises(ValueError, match=reason):
        check_price_gap(bars, calendar, GapLimitUpConfig())


def test_split_does_not_look_like_gap_fill(scenario):
    calendar, bars = scenario
    bars.loc[20:, ["open", "high", "low", "close", "up_limit"]] /= 2
    bars.loc[20:, "adj_factor"] = 2
    result = check_price_gap(bars, calendar, GapLimitUpConfig())
    assert result["gap_lower_current_basis"] == 5.1






def test_first_day_volume_and_one_price_limit(scenario):
    calendar, bars, *_ = scenario
    cfg = GapLimitUpConfig()
    bars = bars.set_index("trade_date")
    assert volume_stage(bars, calendar[-1], cfg)["stage"] == "当日放量，后续待观察"
    assert volume_stage(bars, calendar[-1], cfg)["peak_ratio"] == 5
    bars.loc[calendar[-1], ["low", "high", "open", "close", "up_limit"]] = 11
    assert volume_stage(bars, calendar[-1], cfg)["stage"] == "尚未开板"


class FixtureSource:
    def __init__(self, scenario):
        self.calendar_days, self.bars = deepcopy(scenario)

    def calendar(self, _):
        return self.calendar_days

    def query(self, *_, **__):
        return pd.DataFrame([dict(open=10.6, high=11, low=10.5, close=11, pre_close=10)])

    def prices(self, code, *_):
        result = self.bars.copy()
        if code == "002001":
            result.loc[20, "low"] = 10.2
        return result


def test_pipeline_filters_before_ranking_and_persists_evidence(scenario, monkeypatch):
    from src.services.screening import pipeline
    from src.services.screening.config import Config
    from src.services.screening_service import _normalize_candidate

    snapshot = pd.DataFrame([
        dict(code=code, name="测试企业", price=10.9, amount=100_000_000, change_pct=1)
        for code in ["002000", "002001"]
    ])
    monkeypatch.setattr(pipeline, "fetch_snapshot_with_fallback", lambda *a, **kw: snapshot)
    monkeypatch.setattr("src.services.screening.gap_limit_up.GapLimitUpDataSource", lambda _: FixtureSource(scenario))
    result = pipeline.screen("gap_limit_up", use_llm=False, config=Config(
        post_analyzers=[], risk_enabled=False, portfolio_diversity_enabled=False,
    ))
    assert [pick.code for pick in result.picks] == ["002000"]
    assert result.after_filter_count == 1
    candidate = _normalize_candidate(result.picks[0], 1)
    assert "缺口未回补" in candidate["post_analysis_summaries"]["gap_limit_up"]
    assert candidate["raw"]["post_analysis_results"]["gap_limit_up"]["observation_days"] == 0
    assert any("未形成完整" in note for note in result.degradation)
    from src.services.screening.ranker import _format_dsa_context_for_prompt
    prompt_context = _format_dsa_context_for_prompt(result.picks[0])
    assert '"event_trade_date": "20260330"' in prompt_context
    assert "当日放量，后续待观察" in prompt_context


def test_missing_source_never_degrades_to_generic_candidates(monkeypatch):
    def unavailable(_):
        raise ValueError("缺少 MAIRUI_LICENCE")
    monkeypatch.setattr("src.services.screening.gap_limit_up.GapLimitUpDataSource", unavailable)
    result, evidence, notes = filter_gap_limit_up(pd.DataFrame([dict(code="002000")]), GapLimitUpConfig())
    assert result.empty and not evidence
    assert "MAIRUI_LICENCE" in notes[0]




def test_source_times_out_before_returning_cached_data():
    from unittest.mock import Mock
    source = GapLimitUpDataSource(60, client=Mock())
    source.cache[("income", ())] = pd.DataFrame({"profit": [100]})
    source.deadline = 0
    with pytest.raises(TimeoutError):
        source._frame("income")



def test_strategy_metadata_declares_evidence_requirements():
    from src.services.screening.strategy import list_strategies
    item = next(item for item in list_strategies() if item.name == "gap_limit_up")
    assert item.requires_daily_features
    assert item.data_requirements == ["snapshot", "daily_k", "limit_prices"]
    assert "gap_limit_up" in item.active_filters
    assert "gap_unfilled" in item.active_filters
    assert "up_limit" in item.required_daily_fields


def test_timeout_preserves_only_already_verified_candidates(scenario):
    source = FixtureSource(scenario)
    original = source.prices

    def prices(code, *args):
        if code == "002001":
            raise TimeoutError("覆盖不完整")
        return original(code, *args)

    source.prices = prices
    selected, evidence, notes = filter_gap_limit_up(
        pd.DataFrame([dict(code="002000"), dict(code="002001")]), GapLimitUpConfig(), source=source,
    )
    assert selected["code"].tolist() == ["002000"]
    assert set(evidence) == {"002000"}
    assert "覆盖不完整" in notes


@pytest.mark.parametrize("settings", [
    {"volume_peak_ratio": float("nan")}, {"volume_baseline_days": 1},
    {"volume_peak_ratio": 0}, {"volume_baseline_days": 20.5},
])
def test_invalid_thresholds_cannot_disable_hard_conditions(settings):
    with pytest.raises(ValueError):
        GapLimitUpConfig(**settings)


def test_historical_gap_is_not_rescreened_using_todays_limit(scenario):
    source = FixtureSource(scenario)
    source.calendar_days.append("20260331")
    selected, evidence, notes = filter_gap_limit_up(
        pd.DataFrame([dict(code="002000")]), GapLimitUpConfig(), source=source,
    )
    assert selected.empty and not evidence
    assert any("行情不完整" in note for note in notes)




def test_per_security_data_error_keeps_already_verified_candidates(scenario):
    from data_provider.base import DataFetchError
    source = FixtureSource(scenario)
    original = source.prices

    def prices(code, *args):
        if code == '002001':
            raise DataFetchError('麦蕊日线暂不可用')
        return original(code, *args)

    source.prices = prices
    selected, evidence, notes = filter_gap_limit_up(
        pd.DataFrame([dict(code='002000'), dict(code='002001')]), GapLimitUpConfig(), source=source,
    )
    assert selected['code'].tolist() == ['002000']
    assert set(evidence) == {'002000'}
    assert any('麦蕊日线暂不可用' in note for note in notes)
