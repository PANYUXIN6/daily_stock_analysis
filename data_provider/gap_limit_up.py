"""麦蕊当日跳空涨停行情证据。"""
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import time
from zoneinfo import ZoneInfo

import pandas as pd

from data_provider.mairui_fetcher import MairuiClient, MairuiFetcher, mairui_symbol


class GapLimitUpDataSource:
    def __init__(self, timeout_seconds: float, *, client=None):
        self.client = client or MairuiClient()
        if client is None and not self.client._licence:
            raise ValueError("跳空涨停需要配置 MAIRUI_LICENCE")
        self.fetcher = MairuiFetcher(client=self.client)
        self.deadline = time.monotonic() + timeout_seconds
        self.client.deadline = self.deadline
        self.cache = {}

    def _frame(self, path, **params):
        key = (path, tuple(sorted(params.items())))
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('跳空涨停数据检查达到总时限，覆盖不完整')
        if key not in self.cache:
            self.client.timeout = min(15.0, remaining)
            self.cache[key] = self.client.frame(path, params=params)
        if time.monotonic() >= self.deadline:
            raise TimeoutError('跳空涨停数据检查达到总时限，覆盖不完整')
        return self.cache[key].copy()

    def calendar(self, lookback_days):
        end = self._completed_date()
        days = self.client.calendar((end - timedelta(days=lookback_days)).strftime('%Y%m%d'), end.strftime('%Y%m%d'))
        if not days or days[-1] != end.strftime('%Y%m%d'):
            raise ValueError('今天不是交易日，不生成当日跳空涨停信号')
        return days

    @staticmethod
    def _completed_date():
        now = datetime.now(ZoneInfo('Asia/Shanghai'))
        if now.hour < 22:
            raise ValueError('跳空涨停在交易日 22:00 后按当日完整日线复盘')
        return now.date()

    def query(self, endpoint, **params):
        """Read a daily bar for the preliminary price predicate."""
        if endpoint != 'daily' or not params.get('ts_code'):
            raise ValueError('麦蕊事件日行情必须指定证券')
        day = params['trade_date']
        frame = self._daily(params['ts_code'], day, day, 'n')
        frame['ts_code'] = params['ts_code']
        return frame

    def _daily(self, code, start, end, adjustment):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('跳空涨停数据检查达到总时限，覆盖不完整')
        self.client.timeout = min(15, remaining)
        frame = self.fetcher.daily(code, start, end, adjustment=adjustment)
        frame['trade_date'] = frame['date'].dt.strftime('%Y%m%d')
        return frame.rename(columns={'volume': 'vol'})

    @staticmethod
    def _price(value):
        try:
            price = Decimal(str(value))
            if price.is_finite() and price > 0:
                return price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            pass
        return None

    def prices(self, code, start, end, event_day):
        if end != self._completed_date().strftime('%Y%m%d') or event_day != end:
            raise ValueError('仅核实当晚跳空涨停新信号，不能用当日限价判断历史事件')
        raw = self._daily(code, start, end, 'n')
        # Proportional backward-adjusted OHLC replaces ratios of adj_factor.
        # Keep the provider's actual adjusted prices, never reconstruct a fake
        # exact factor from rounded closing prices.
        adjusted = self._daily(code, start, end, 'br')
        cols = ['open', 'high', 'low', 'close']
        adjusted = adjusted[['trade_date', *cols]].rename(columns={col: f'adjusted_{col}' for col in cols})
        result = raw.merge(adjusted, on='trade_date', how='left', validate='one_to_one').sort_values('trade_date').reset_index(drop=True)
        result['up_limit'] = float('nan')
        event_rows = result.index[result['trade_date'] == event_day]
        if len(event_rows) != 1:
            raise ValueError('当日行情缺失或重复')
        event_index = event_rows[0]
        symbol = mairui_symbol(code)
        prefix = 'bj' if symbol.endswith('.BJ') else 'hsstock'
        path = f'{prefix}/instrument/{symbol}'
        instrument = self._frame(path)
        if len(instrument) != 1 or not {'ei', 'ii', 'pc', 'up'}.issubset(instrument):
            raise ValueError('股票基础信息缺少当日涨停价或证券身份')
        info = instrument.iloc[0]
        if mairui_symbol(f"{info['ii']}.{info['ei']}") != symbol:
            raise ValueError('股票基础信息的证券身份不一致')
        previous_close = self._price(result.at[event_index, 'pre_close'])
        if previous_close is None or self._price(info['pc']) != previous_close:
            raise ValueError('股票基础信息尚未与当日日线对齐：前收盘价不一致')
        price = self._price(info['up'])
        if price is None:
            raise ValueError('当日涨停价不可用，无法确认收盘涨停')
        result.at[event_index, 'up_limit'] = float(price)
        result.attrs['limit_up_source'] = path
        return result

