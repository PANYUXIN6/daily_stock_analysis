# Derived from AlphaSift revision 9f522747caafd3c0b1ddb7e14d5cf44c8580b6cf.
# Licensed under Apache-2.0 and modified for daily_stock_analysis.
"""Deterministic earnings-gap gate before any ranking or candidate truncation."""

from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import math

import pandas as pd

from data_provider.profit_gap import ProfitGapDataSource
from src.services.screening.models import ProfitGapConfig
from src.services.screening.normalize import normalize_code


def number(value) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("非有限数值")
    return result


def cents(value) -> Decimal:
    return Decimal(str(number(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def check_price_gap(frame: pd.DataFrame, announcement: str, calendar: list[str], cfg: ProfitGapConfig) -> dict:
    dates = [day for day in calendar if day > announcement]
    if len(dates) < cfg.min_observation_days + 1:
        raise ValueError("断层后观察交易日不足")
    event_day = dates[0]
    previous_day = calendar[calendar.index(event_day) - 1]
    required = {"trade_date", "open", "high", "low", "close", "vol", "adj_factor", "up_limit"}
    if not required.issubset(frame.columns):
        raise ValueError("日线或涨停价字段缺失")
    bars = frame.copy().set_index("trade_date").sort_index()
    if bars.index.has_duplicates or not set([previous_day, *dates]).issubset(bars.index):
        raise ValueError("交易日行情不完整或停牌，不能验证下一交易日与缺口")
    bars = bars.loc[:calendar[-1]]
    for col in ("open", "high", "low", "close", "adj_factor", "vol"):
        bars[col] = bars[col].map(number)
        if (bars[col] <= 0).any():
            raise ValueError("行情含无效价格、复权因子或成交量")
    if ((bars["low"] > bars[["open", "close"]].min(axis=1)) | (bars["high"] < bars[["open", "close"]].max(axis=1))).any():
        raise ValueError("OHLC 行情不一致")
    event = bars.loc[event_day]
    if number(event["up_limit"]) <= 0 or cents(event["close"]) != cents(event["up_limit"]):
        raise ValueError("公告下一交易日未收盘封涨停")
    # Use raw prices to verify exchange limit; factors only for cross-day gaps.
    anchor = bars.loc[previous_day, "adj_factor"]
    adjusted = bars[["open", "high", "low", "close"]].mul(bars["adj_factor"] / anchor, axis=0)
    lower = float(adjusted.loc[previous_day, "high"])
    upper = float(adjusted.loc[event_day, "low"])
    tolerance = max(abs(lower), 1.0) * 1e-10  # Arithmetic noise, not a price band.
    if adjusted.loc[event_day, "open"] <= lower + tolerance or upper <= lower + tolerance:
        raise ValueError("涨停但未形成完整向上跳空缺口")
    if adjusted.loc[dates, "low"].min() <= lower + tolerance:
        raise ValueError("跳空缺口已回补（含盘中触及下沿）")
    volume = volume_stage(bars, event_day, cfg)
    return {
        "event_trade_date": event_day, "as_of": calendar[-1],
        "gap_lower": lower, "gap_upper": upper,
        "gap_lower_current_basis": lower * anchor / float(bars.iloc[-1]["adj_factor"]),
        "observation_days": len(dates) - 1,
        "volume": volume,
    }


def volume_stage(bars: pd.DataFrame, event_day: str, cfg: ProfitGapConfig) -> dict:
    prior = bars.loc[bars.index < event_day, "vol"].tail(cfg.volume_baseline_days)
    result = {"stage": "待观察", "note": "量价不能证明机构身份或换庄"}
    if len(prior) < cfg.volume_baseline_days:
        return {**result, "stage": "样本不足"}
    baseline = float(prior.mean())
    after = bars.loc[event_day:]
    unlocked = []
    for day, bar in after.iterrows():
        try:
            if number(bar["up_limit"]) <= 0:
                raise ValueError("无涨停价")
            if cents(bar["low"]) < cents(bar["up_limit"]):
                unlocked.append(day)
        except (TypeError, ValueError):
            return {**result, "stage": "样本不足"}
    if not unlocked:
        return {**result, "stage": "尚未开板", "baseline": baseline}
    volumes = after.loc[unlocked[0]:, "vol"]
    peak = float(volumes.iloc[:3].max())
    result.update(baseline=baseline, peak_ratio=peak / baseline, open_board_date=unlocked[0])
    if peak < baseline * cfg.volume_peak_ratio or volumes.max() > peak:
        return {**result, "stage": "量能形态未确认"}
    if len(volumes) <= 3:
        return {**result, "stage": "第一阶段：急剧放大"}
    tail = volumes.iloc[3:]
    if len(tail) >= 5:
        recent = tail.tail(5)
        cv = float(recent.std(ddof=0) / recent.mean())
        if baseline < recent.mean() < peak * 0.65 and cv <= cfg.volume_stable_cv:
            return {**result, "stage": "第三阶段：趋于稳定", "recent_cv": cv}
    midpoint = max(1, len(tail) // 2)
    if len(tail) >= 2 and baseline < tail.iloc[midpoint:].mean() < tail.iloc[:midpoint].mean() < peak:
        return {**result, "stage": "第二阶段：开始缩小"}
    return {**result, "stage": "量能形态未确认"}


def check_earnings(event: dict, quality: dict, income: dict, previous_income: dict,
                   cfg: ProfitGapConfig) -> dict:
    if event["kind"] == "forecast":
        if number(event.get("last_parent_net")) <= 0:
            raise ValueError("上年同期亏损或零基数，增长幅度不可比")
        profit = number(event["net_profit_min"]) * 10000  # Conservative lower bound, CNY.
        yoy = number(event["p_change_min"])
    else:
        profit = number(event["n_income_attr_p"])
        previous = number(previous_income.get("n_income_attr_p"))
        if previous <= 0:
            raise ValueError("上年同期亏损或零基数，增长幅度不可比")
        yoy = (profit / previous - 1) * 100
    if profit <= 0 or yoy + 1e-9 < cfg.min_profit_yoy_pct:
        raise ValueError("净利润增长未达门槛")
    # Same-period actual quality is required, also for forecasts. Never silently
    # substitute last year's profitability for this event's sustainable growth.
    actual = number(income.get("n_income_attr_p"))
    if actual < profit:
        raise ValueError("最新实际利润低于事件披露值或预告下限，事件需重新核实")
    core = number(quality.get("profit_dedt"))
    if actual <= 0 or core / actual < cfg.min_core_profit_ratio:
        raise ValueError("非经常损益占比过高或扣非利润不合格")
    if any(number(quality.get(key)) <= 0 for key in ("dt_netprofit_yoy", "or_yoy", "ocfps")):
        raise ValueError("扣非增长、营收增长或经营现金流不合格")
    return {
        "profit_yoy_pct": round(yoy, 2),
        "profit_lower_bound": profit,
        "core_profit_ratio": round(core / actual, 4),
        "quality_ann_date": str(quality.get("ann_date", "")),
        "fundamental_note": "扣非、营收和经营现金流已验证；主营持续性、行业估值及机构买入仍需深入研究",
    }


def filter_profit_gap(snapshot: pd.DataFrame, cfg: ProfitGapConfig, *, source=None, progress=None) -> tuple[pd.DataFrame, dict, list[str]]:
    """Scan event universe, fail closed per event, report incomplete coverage."""
    evidence, notes, rejected = {}, [], Counter()
    try:
        source = source or ProfitGapDataSource(cfg.timeout_seconds)
        calendar = source.calendar(cfg.event_lookback_days)
        as_of = calendar[-1]
        start = (datetime.strptime(as_of, "%Y%m%d") - timedelta(days=cfg.event_lookback_days)).strftime("%Y%m%d")
        events, source_notes = source.events(start, as_of)
        notes.extend(source_notes)
    except Exception as exc:
        return snapshot.iloc[:0].copy(), {}, [f"净利润断层无法完成硬条件验证：{exc}"]
    universe = set(snapshot["code"].map(normalize_code))
    examined = 0
    for event in events:
        code = normalize_code(event.get("ts_code"))
        if code not in universe or code in evidence:
            continue
        examined += 1
        if progress:
            progress(45, f"正在核实净利润断层财报事件 {examined}/{len(events)}")
        try:
            next_days = [day for day in calendar if day > event["ann_date"]]
            if len(next_days) < cfg.min_observation_days + 1:
                raise ValueError("断层后观察交易日不足")
            # Batch necessary price conditions by date before fetching per-stock
            # history; every event is considered, with no generic Top-K cutoff.
            day = next_days[0]
            market_bars = source.query("daily", trade_date=day, fields="ts_code,open,high,low,close,pre_close")
            if market_bars.empty or "ts_code" not in market_bars:
                raise ValueError("事件日全市场行情缺失")
            bar = market_bars[market_bars["ts_code"] == event["ts_code"]]
            if len(bar) != 1:
                raise ValueError("公告下一交易日行情缺失或停牌")
            bar = bar.iloc[0]
            if cents(bar["close"]) != cents(bar["high"]) or number(bar["open"]) <= number(bar["pre_close"]):
                raise ValueError("公告下一交易日不符合跳空封板必要条件")
            prices = source.prices(event["ts_code"], calendar[0], as_of)
            technical = check_price_gap(prices, event["ann_date"], calendar, cfg)
            quality, income = source.financials(event["ts_code"], event["end_date"], as_of)
            previous_income = {}
            if event["kind"] == "report":
                previous_period = str(int(event["end_date"][:4]) - 1) + event["end_date"][4:]
                _, previous_income = source.financials(event["ts_code"], previous_period, event["ann_date"])
            fundamental = check_earnings(event, quality, income, previous_income, cfg)
            evidence[code] = {
                **technical, **fundamental, "announcement_date": event["ann_date"],
                "report_period": event["end_date"], "event_kind": event["kind"],
                "source": f"Tushare {event['source']}/daily/stk_limit/adj_factor/fina_indicator/income",
            }
        except TimeoutError as exc:
            notes.append(str(exc))
            break
        except (KeyError, TypeError):
            rejected["关键证据字段缺失"] += 1
        except (ValueError, RuntimeError) as exc:
            rejected[str(exc)] += 1
    notes.append(f"净利润断层：截至 {as_of} 已完成交易日；扫描 {examined}/{len(events)} 个事件，确认 {len(evidence)} 只")
    notes.extend(f"净利润断层排除/待核实：{reason}（{count}）" for reason, count in rejected.most_common())
    return snapshot[snapshot["code"].map(normalize_code).isin(evidence)].copy(), evidence, notes


def evidence_summary(item: dict) -> str:
    return (
        f"净利润断层｜净利润同比 +{item['profit_yoy_pct']:.1f}%；"
        f"{item['event_trade_date']} 跳空涨停；"
        f"截至 {item['as_of']} 缺口未回补，已观察 {item['observation_days']} 个交易日；"
        f"缺口下沿 {item['gap_lower_current_basis']:.2f}（观察日价格口径）；"
        f"{item['volume']['stage']}；扣非占比 {item['core_profit_ratio']:.0%}。"
    )
