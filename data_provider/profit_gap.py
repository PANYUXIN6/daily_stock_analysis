"""Tushare evidence for the earnings-gap screen; no LLM inference or price proxies."""

from datetime import datetime, timedelta
import time
from zoneinfo import ZoneInfo

import pandas as pd

from data_provider.tushare_fetcher import _TushareHttpClient, _resolve_tushare_http_url
from src.config import get_config


class ProfitGapDataSource:
    """One request, one bounded budget, with request-local query reuse."""

    def __init__(self, timeout_seconds: float, *, client=None):
        if client is None:
            token = get_config().tushare_token
            if not token:
                raise ValueError("净利润断层需要配置 TUSHARE_TOKEN 及财务与行情访问权限")
            url = _resolve_tushare_http_url()
            client = _TushareHttpClient(token, **({"api_url": url} if url else {}))
        self.client = client
        self.deadline = time.monotonic() + timeout_seconds
        self.cache: dict[tuple, pd.DataFrame] = {}

    def query(self, endpoint: str, **params) -> pd.DataFrame:
        key = (endpoint, tuple(sorted(params.items())))
        if key in self.cache:
            return self.cache[key].copy()
        pages = []
        offset = 0
        while True:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("净利润断层数据检查达到总时限，覆盖不完整")
            # Reuse the project's HTTP client and bound each actual socket call.
            self.client._timeout = min(15.0, remaining)
            try:
                page = self.client.query(endpoint, limit=3000, offset=offset, **params)
            except Exception as exc:
                # Provider exceptions can contain gateway details; do not persist them.
                raise RuntimeError(f"{endpoint} 数据不可用（{type(exc).__name__}），请检查权限或网络") from exc
            if not isinstance(page, pd.DataFrame):
                raise ValueError(f"{endpoint} 返回格式错误")
            if time.monotonic() > self.deadline:
                raise TimeoutError("净利润断层数据检查达到总时限，覆盖不完整")
            pages.append(page)
            if len(page) < 3000:
                break
            offset += len(page)
        result = pd.concat(pages, ignore_index=True) if pages else pd.DataFrame()
        self.cache[key] = result
        return result.copy()

    def calendar(self, lookback_days: int) -> list[str]:
        # Only completed sessions: allow the vendor's evening daily update to finish.
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        end = now.date() if now.hour >= 22 else now.date() - timedelta(days=1)
        frame = self.query(
            "trade_cal", exchange="SSE", is_open="1",
            start_date=(end - timedelta(days=lookback_days + 90)).strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"), fields="cal_date,is_open",
        )
        if frame.empty or "cal_date" not in frame:
            raise ValueError("交易日历缺失")
        return sorted(set(frame["cal_date"].astype(str)))

    def events(self, start: str, end: str) -> tuple[list[dict], list[str]]:
        events, notes = [], []
        sources = [
            ("income_vip", "report", "ts_code,ann_date,f_ann_date,end_date,report_type,n_income_attr_p"),
            ("forecast_vip", "forecast", "ts_code,ann_date,end_date,net_profit_min,p_change_min,last_parent_net,change_reason"),
        ]
        for endpoint, kind, fields in sources:
            try:
                frame = self.query(endpoint, start_date=start, end_date=end, fields=fields)
                for row in frame.to_dict("records"):
                    if kind == "report" and str(row.get("report_type")) != "1":
                        continue  # Consolidated cumulative figures only.
                    actual_ann = row.get("f_ann_date")
                    ann = str(actual_ann if pd.notna(actual_ann) and actual_ann else row.get("ann_date", ""))
                    if not start <= ann <= end:
                        continue
                    events.append({**row, "ann_date": ann, "kind": kind, "source": endpoint})
            except TimeoutError:
                raise
            except Exception as exc:
                notes.append(str(exc))
        events.sort(key=lambda row: (row["ann_date"], row["ts_code"]), reverse=True)
        return events, notes

    def prices(self, code: str, start: str, end: str) -> pd.DataFrame:
        params = dict(ts_code=code, start_date=start, end_date=end)
        daily = self.query("daily", **params, fields="trade_date,open,high,low,close,vol")
        factors = self.query("adj_factor", **params, fields="trade_date,adj_factor")
        limits = self.query("stk_limit", **params, fields="trade_date,up_limit")
        if any(frame.empty for frame in (daily, factors, limits)):
            raise ValueError("日线、复权因子或涨停价缺失")
        return daily.merge(factors, on="trade_date", how="left", validate="one_to_one").merge(
            limits, on="trade_date", how="left", validate="one_to_one",
        ).sort_values("trade_date").reset_index(drop=True)

    def financials(self, code: str, period: str, as_of: str) -> tuple[dict, dict]:
        indicator = self.query(
            "fina_indicator", ts_code=code, period=period,
            fields="ann_date,end_date,profit_dedt,dt_netprofit_yoy,or_yoy,ocfps,eps",
        )
        income = self.query(
            "income", ts_code=code, period=period, report_type="1",
            fields="ann_date,f_ann_date,end_date,n_income_attr_p",
        )
        return self._known_row(indicator, as_of), self._known_row(income, as_of)

    @staticmethod
    def _known_row(frame: pd.DataFrame, as_of: str) -> dict:
        if frame.empty or "ann_date" not in frame:
            return {}
        frame = frame.copy()
        if "f_ann_date" in frame:
            frame["ann_date"] = frame["f_ann_date"].fillna(frame["ann_date"])
        frame = frame[frame["ann_date"].astype(str) <= as_of]
        if frame.empty:
            return {}
        return frame.sort_values("ann_date").iloc[-1].to_dict()
