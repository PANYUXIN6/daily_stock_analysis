# Derived from AlphaSift revision 9f522747caafd3c0b1ddb7e14d5cf44c8580b6cf.
# Licensed under Apache-2.0 and modified for daily_stock_analysis.
"""Deterministic daily gap-and-limit-up gate before ranking or truncation."""

from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
import math

import pandas as pd

from data_provider.gap_limit_up import GapLimitUpDataSource
from data_provider.base import DataFetchError
from src.services.screening.models import GapLimitUpConfig
from src.services.screening.normalize import normalize_code


def number(value) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("非有限数值")
    return result


def cents(value) -> Decimal:
    return Decimal(str(number(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def check_price_gap(frame: pd.DataFrame, calendar: list[str], cfg: GapLimitUpConfig) -> dict:
    if len(calendar) < 2:
        raise ValueError("缺少前一交易日，无法核实跳空")
    event_day = calendar[-1]
    previous_day = calendar[-2]
    dates = [event_day]
    required = {"trade_date", "open", "high", "low", "close", "vol", "up_limit"}
    if not required.issubset(frame.columns):
        raise ValueError("日线或涨停价字段缺失")
    bars = frame.copy().set_index("trade_date").sort_index()
    if bars.index.has_duplicates or not set([previous_day, *dates]).issubset(bars.index):
        raise ValueError("交易日行情不完整或停牌，不能验证当日缺口")
    bars = bars.loc[:calendar[-1]]
    for col in ("open", "high", "low", "close", "vol"):
        bars[col] = bars[col].map(number)
        if (bars[col] <= 0).any():
            raise ValueError("行情含无效价格、复权因子或成交量")
    if ((bars["low"] > bars[["open", "close"]].min(axis=1)) | (bars["high"] < bars[["open", "close"]].max(axis=1))).any():
        raise ValueError("OHLC 行情不一致")
    event = bars.loc[event_day]
    if number(event["up_limit"]) <= 0 or cents(event["close"]) != cents(event["up_limit"]):
        raise ValueError("当日未收盘封涨停")
    # Use raw prices to verify exchange limit; factors only for cross-day gaps.
    adjusted_cols = [f"adjusted_{col}" for col in ("open", "high", "low", "close")]
    if set(adjusted_cols).issubset(bars):
        adjusted = bars[adjusted_cols].copy()
        adjusted.columns = ["open", "high", "low", "close"]
        for col in adjusted:
            adjusted[col] = adjusted[col].map(number)
            if (adjusted[col] <= 0).any():
                raise ValueError("等比复权行情无效")
        if ((adjusted["low"] > adjusted[["open", "close"]].min(axis=1)) | (adjusted["high"] < adjusted[["open", "close"]].max(axis=1))).any():
            raise ValueError("等比复权 OHLC 行情不一致")
        # Vendor rounds backward-adjusted prices to cents. Reject ambiguous
        # sub-cent boundary gaps instead of claiming exact factor equivalence.
        tolerance = 0.01
        current_basis = float(bars.iloc[-1]["close"]) / float(adjusted.iloc[-1]["close"])
    else:
        if "adj_factor" not in bars:
            raise ValueError("等比复权行情或复权因子缺失")
        bars["adj_factor"] = bars["adj_factor"].map(number)
        if (bars["adj_factor"] <= 0).any():
            raise ValueError("复权因子无效")
        anchor = bars.loc[previous_day, "adj_factor"]
        adjusted = bars[["open", "high", "low", "close"]].mul(bars["adj_factor"] / anchor, axis=0)
        current_basis = anchor / float(bars.iloc[-1]["adj_factor"])
        tolerance = max(abs(float(adjusted.loc[previous_day, "high"])), 1.0) * 1e-10
    lower = float(adjusted.loc[previous_day, "high"])
    upper = float(adjusted.loc[event_day, "low"])
    if adjusted.loc[event_day, "open"] <= lower + tolerance or upper <= lower + tolerance:
        raise ValueError("涨停但未形成完整向上跳空缺口")
    if adjusted.loc[dates, "low"].min() <= lower + tolerance:
        raise ValueError("跳空缺口已回补（含盘中触及下沿）")
    volume = volume_stage(bars, event_day, cfg)
    return {
        "event_trade_date": event_day, "as_of": calendar[-1],
        "gap_lower": lower, "gap_upper": upper,
        "gap_lower_current_basis": lower * current_basis,
        "observation_days": len(dates) - 1,
        "volume": volume,
    }


def volume_stage(bars: pd.DataFrame, event_day: str, cfg: GapLimitUpConfig) -> dict:
    prior = bars.loc[bars.index < event_day, "vol"].tail(cfg.volume_baseline_days)
    result = {"stage": "待观察", "note": "仅描述断层当日量能；后续缩量与稳定尚未发生"}
    if len(prior) < cfg.volume_baseline_days:
        return {**result, "stage": "样本不足"}
    baseline = float(prior.mean())
    event = bars.loc[event_day]
    ratio = float(event["vol"]) / baseline
    result.update(baseline=baseline, peak_ratio=ratio)
    if cents(event["low"]) == cents(event["up_limit"]):
        return {**result, "stage": "尚未开板"}
    stage = "当日放量，后续待观察" if ratio >= cfg.volume_peak_ratio else "量能形态未确认"
    return {**result, "stage": stage, "open_board_date": event_day}


def filter_gap_limit_up(snapshot: pd.DataFrame, cfg: GapLimitUpConfig, *, source=None, progress=None) -> tuple[pd.DataFrame, dict, list[str]]:
    """Check today's price pattern across the snapshot, preserving verified results on timeout."""
    evidence, notes, rejected = {}, [], Counter()
    try:
        source = source or GapLimitUpDataSource(cfg.timeout_seconds)
        calendar = source.calendar(cfg.volume_baseline_days * 3)
        as_of = calendar[-1]
    except Exception as exc:
        return snapshot.iloc[:0].copy(), {}, [f"跳空涨停无法完成硬条件验证：{exc}"]
    # A positive day is necessary for a gap up. No fixed limit-up percentage.
    candidates = snapshot.copy()
    if "change_pct" in candidates:
        candidates = candidates[pd.to_numeric(candidates["change_pct"], errors="coerce") > 0]
    examined = 0
    for row in candidates.to_dict("records"):
        code = normalize_code(row.get("code"))
        if not code or code in evidence:
            continue
        examined += 1
        if progress:
            progress(45, f"正在核实跳空涨停 {examined}/{len(candidates)}")
        try:
            # Same-day snapshot OHLC can skip obvious non-candidates cheaply;
            # full daily data remains authoritative for every accepted stock.
            if str(row.get("trade_date", "")) == as_of and all(pd.notna(row.get(k)) for k in ("open", "high", "pre_close")):
                if cents(row["price"]) != cents(row["high"]) or number(row["open"]) <= number(row["pre_close"]):
                    continue
            market_bars = source.query("daily", ts_code=code, trade_date=as_of)
            if len(market_bars) != 1:
                raise ValueError("当日日线缺失或重复")
            bar = market_bars.iloc[0]
            if cents(bar["close"]) != cents(bar["high"]) or number(bar["open"]) <= number(bar["pre_close"]):
                raise ValueError("当日不符合跳空封板必要条件")
            prices = source.prices(code, calendar[0], as_of, as_of)
            evidence[code] = {
                **check_price_gap(prices, calendar, cfg),
                "source": f"麦蕊 history(n,br)/{prices.attrs.get('limit_up_source', 'instrument')}",
            }
        except TimeoutError as exc:
            notes.append(str(exc))
            break
        except (KeyError, TypeError):
            rejected["关键证据字段缺失"] += 1
        except (ValueError, RuntimeError, DataFetchError) as exc:
            rejected[str(exc)] += 1
    notes.append(f"跳空涨停：截至 {as_of}；核实 {examined}/{len(candidates)} 只上涨股票，确认 {len(evidence)} 只")
    notes.extend(f"跳空涨停排除/待核实：{reason}（{count}）" for reason, count in rejected.most_common())
    return snapshot[snapshot["code"].map(normalize_code).isin(evidence)].copy(), evidence, notes


def evidence_summary(item: dict) -> str:
    return (
        "跳空涨停｜"
        f"{item['event_trade_date']} 跳空涨停；"
        f"截至 {item['as_of']} 缺口未回补，已观察 {item['observation_days']} 个交易日；"
        f"缺口下沿 {item['gap_lower_current_basis']:.2f}（观察日价格口径）；"
        f"{item['volume']['stage']}。"
    )
