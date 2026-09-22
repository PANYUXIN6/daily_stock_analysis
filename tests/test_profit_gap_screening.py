"""Offline acceptance scenarios for the three mandatory earnings-gap conditions."""

from copy import deepcopy

import pandas as pd
import pytest

from data_provider.profit_gap import ProfitGapDataSource
from src.services.screening.models import ProfitGapConfig
from src.services.screening.profit_gap import (
    check_earnings, check_price_gap, filter_profit_gap, volume_stage,
)


@pytest.fixture
def scenario():
    calendar = pd.bdate_range("2026-03-02", periods=30).strftime("%Y%m%d").tolist()
    bars = pd.DataFrame([
        dict(trade_date=day, open=10.0, high=10.2, low=9.9, close=10.0, vol=100.0, adj_factor=1.0, up_limit=11.0)
        for day in calendar
    ])
    for idx in range(20, 30):
        bars.loc[idx, ["open", "high", "low", "close", "vol", "up_limit"]] = [10.6, 11, 10.5, 10.9, 200, 12]
    bars.loc[20, ["close", "up_limit", "vol"]] = [11, 11, 500]
    bars.loc[21:29, "vol"] = [400, 300, 250, 200, 190, 195, 205, 200, 200]
    event = dict(ts_code="002000.SZ", ann_date=calendar[19], end_date="20251231", kind="report",
                 n_income_attr_p=150_000_000, source="income_vip")
    quality = dict(profit_dedt=130_000_000, dt_netprofit_yoy=40, or_yoy=20, ocfps=1.5,
                   ann_date=calendar[19])
    income = dict(n_income_attr_p=150_000_000)
    previous = dict(n_income_attr_p=100_000_000)
    return calendar, bars, event, quality, income, previous


def test_all_three_conditions_and_quality_pass(scenario):
    calendar, bars, event, quality, income, previous = scenario
    price = check_price_gap(bars, event["ann_date"], calendar, ProfitGapConfig())
    earnings = check_earnings(event, quality, income, previous, ProfitGapConfig())
    assert price["gap_lower"] == 10.2
    assert price["observation_days"] == 9
    assert price["volume"]["stage"] == "第三阶段：趋于稳定"
    assert earnings["profit_yoy_pct"] == 50


@pytest.mark.parametrize("mutation,reason", [
    ("no_limit", "未收盘封涨停"),
    ("no_gap", "未形成完整"),
    ("filled", "已回补"),
    ("missing_session", "行情不完整"),
    ("missing_factor", "非有限"),
    ("too_early", "观察交易日不足"),
])
def test_price_exclusions(scenario, mutation, reason):
    calendar, bars, event, *_ = scenario
    if mutation == "no_limit":
        bars.loc[20, "close"] = 10.95  # Intraday touch is insufficient.
    elif mutation == "no_gap":
        bars.loc[20, "low"] = 10.2
    elif mutation == "filled":
        bars.loc[24, "low"] = 10.2  # Exact touch, followed by recovery.
    elif mutation == "missing_session":
        bars = bars.drop(index=20)
    elif mutation == "missing_factor":
        bars.loc[25, "adj_factor"] = float("nan")
    elif mutation == "too_early":
        calendar = calendar[:21]
    with pytest.raises(ValueError, match=reason):
        check_price_gap(bars, event["ann_date"], calendar, ProfitGapConfig())


def test_split_does_not_look_like_gap_fill(scenario):
    calendar, bars, event, *_ = scenario
    bars.loc[25:, ["open", "high", "low", "close", "up_limit"]] /= 2
    bars.loc[25:, "adj_factor"] = 2
    result = check_price_gap(bars, event["ann_date"], calendar, ProfitGapConfig())
    assert result["gap_lower_current_basis"] == 5.1


@pytest.mark.parametrize("mutation,reason", [
    ("slow", "净利润增长未达"),
    ("one_off", "非经常损益"), ("cashflow", "经营现金流"),
    ("missing_quality", ""), ("loss_base", "亏损或零基数"),
])
def test_earnings_exclusions(scenario, mutation, reason):
    _, _, event, quality, income, previous = scenario
    if mutation == "slow":
        previous["n_income_attr_p"] = 120_000_000
    elif mutation == "one_off":
        quality["profit_dedt"] = 30_000_000
    elif mutation == "cashflow":
        quality["ocfps"] = -1
    elif mutation == "missing_quality":
        quality = {}
    elif mutation == "loss_base":
        previous["n_income_attr_p"] = -100
    with pytest.raises((ValueError, TypeError), match=reason or None):
        check_earnings(event, quality, income, previous, ProfitGapConfig())


def test_forecast_uses_lower_bound_and_requires_same_period_quality(scenario):
    _, _, event, quality, income, _ = scenario
    event.update(kind="forecast", net_profit_min=12000, net_profit_max=20000, p_change_min=50, last_parent_net=8000)
    result = check_earnings(event, quality, income, {}, ProfitGapConfig())
    assert result["profit_lower_bound"] == 120_000_000
    event["p_change_min"] = 49
    with pytest.raises(ValueError, match="净利润增长未达"):
        check_earnings(event, quality, income, {}, ProfitGapConfig())


def test_volume_three_stages_and_unopened_board(scenario):
    calendar, bars, *_ = scenario
    cfg = ProfitGapConfig()
    bars = bars.set_index("trade_date")
    assert volume_stage(bars.iloc[:23], calendar[20], cfg)["stage"] == "第一阶段：急剧放大"
    assert volume_stage(bars.iloc[:27], calendar[20], cfg)["stage"] == "第二阶段：开始缩小"
    assert volume_stage(bars, calendar[20], cfg)["stage"] == "第三阶段：趋于稳定"
    bars.loc[calendar[20]:, ["low", "high", "open", "close"]] = 12
    bars.loc[calendar[20]:, "up_limit"] = 12
    assert volume_stage(bars, calendar[20], cfg)["stage"] == "尚未开板"


class FixtureSource:
    def __init__(self, scenario):
        self.calendar_days, self.bars, self.event, self.quality, self.income, self.previous = deepcopy(scenario)

    def calendar(self, _):
        return self.calendar_days

    def events(self, *_):
        return [self.event, {**self.event, "ts_code": "002001.SZ"}], []

    def query(self, *_, **__):
        return pd.DataFrame([
            dict(ts_code=code, open=10.6, high=11, low=10.5, close=11, pre_close=10)
            for code in ["002000.SZ", "002001.SZ"]
        ])

    def prices(self, code, *_):
        result = self.bars.copy()
        if code == "002001.SZ":
            result.loc[24, "low"] = 10.2
        return result

    def financials(self, _, period, __):
        return self.quality, self.income if period == "20251231" else self.previous


def test_pipeline_filters_before_ranking_and_persists_evidence(scenario, monkeypatch):
    from src.services.screening import pipeline
    from src.services.screening.config import Config
    from src.services.screening_service import _normalize_candidate

    snapshot = pd.DataFrame([
        dict(code=code, name="测试企业", price=10.9, amount=100_000_000, change_pct=1)
        for code in ["002000", "002001"]
    ])
    monkeypatch.setattr(pipeline, "fetch_snapshot_with_fallback", lambda *a, **kw: snapshot)
    monkeypatch.setattr("src.services.screening.profit_gap.ProfitGapDataSource", lambda _: FixtureSource(scenario))
    result = pipeline.screen("net_profit_gap", use_llm=False, config=Config(
        post_analyzers=[], risk_enabled=False, portfolio_diversity_enabled=False,
    ))
    assert [pick.code for pick in result.picks] == ["002000"]
    assert result.after_filter_count == 1
    candidate = _normalize_candidate(result.picks[0], 1)
    assert "缺口未回补" in candidate["post_analysis_summaries"]["net_profit_gap"]
    assert candidate["raw"]["post_analysis_results"]["net_profit_gap"]["profit_yoy_pct"] == 50
    assert any("已回补" in note for note in result.degradation)
    from src.services.screening.ranker import _format_dsa_context_for_prompt
    prompt_context = _format_dsa_context_for_prompt(result.picks[0])
    assert '"profit_yoy_pct": 50.0' in prompt_context
    assert "第三阶段：趋于稳定" in prompt_context


def test_missing_source_never_degrades_to_generic_candidates(monkeypatch):
    def unavailable(_):
        raise ValueError("缺少 TUSHARE_TOKEN")
    monkeypatch.setattr("src.services.screening.profit_gap.ProfitGapDataSource", unavailable)
    result, evidence, notes = filter_profit_gap(pd.DataFrame([dict(code="002000")]), ProfitGapConfig())
    assert result.empty and not evidence
    assert "TUSHARE_TOKEN" in notes[0]


def test_known_financials_exclude_future_disclosures():
    frame = pd.DataFrame([
        dict(ann_date="20260301", f_ann_date="20260302", n_income_attr_p=100),
        dict(ann_date="20260301", f_ann_date="20260401", n_income_attr_p=900),
    ])
    assert ProfitGapDataSource._known_row(frame, "20260320")["n_income_attr_p"] == 100


def test_source_paginates_and_times_out_without_partial_page_acceptance():
    class Client:
        def query(self, endpoint, **kwargs):
            return pd.DataFrame({"row": range(3000 if kwargs["offset"] == 0 else 1)})
    source = ProfitGapDataSource(60, client=Client())
    assert len(source.query("income_vip")) == 3001
    source.deadline = 0
    with pytest.raises(TimeoutError):
        source.query("daily")


def test_strategy_metadata_declares_evidence_requirements():
    from src.services.screening.strategy import list_strategies
    item = next(item for item in list_strategies() if item.name == "net_profit_gap")
    assert item.requires_daily_features
    assert "earnings" in item.data_requirements
    assert "profit_growth" in item.active_filters
    assert "gap_unfilled" in item.active_filters
    assert "up_limit" in item.required_daily_fields


def test_timeout_preserves_only_already_verified_candidates(scenario):
    source = FixtureSource(scenario)
    original = source.prices

    def prices(code, *args):
        if code == "002001.SZ":
            raise TimeoutError("覆盖不完整")
        return original(code, *args)

    source.prices = prices
    selected, evidence, notes = filter_profit_gap(
        pd.DataFrame([dict(code="002000"), dict(code="002001")]), ProfitGapConfig(), source=source,
    )
    assert selected["code"].tolist() == ["002000"]
    assert set(evidence) == {"002000"}
    assert "覆盖不完整" in notes


@pytest.mark.parametrize("settings", [
    {"min_profit_yoy_pct": float("nan")}, {"volume_baseline_days": 1},
    {"min_observation_days": 0}, {"event_lookback_days": 0.5},
])
def test_invalid_thresholds_cannot_disable_hard_conditions(settings):
    with pytest.raises(ValueError):
        ProfitGapConfig(**settings)
