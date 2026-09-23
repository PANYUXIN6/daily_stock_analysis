# -*- coding: utf-8 -*-
"""麦蕊行情适配；内部日线/实时报价统一使用股、元、百分点。

端点及已验证差异见 docs/mairui-migration.md。只接受已知响应形状，
供应商错误、缺失数据和权限不足交回现有 manager 执行 fallback。
"""
from collections import deque
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timedelta
import logging
import os
import re
from threading import RLock
import time
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from src.config import get_config
from src.services.stock_list_parser import parse_analysis_target
from .base import BaseFetcher, DataFetchError, RateLimitError, normalize_stock_code, is_bse_code, _is_etf_code
from .realtime_types import UnifiedRealtimeQuote, RealtimeSource, safe_float, safe_int

logger = logging.getLogger(__name__)


class MairuiClient:
    """共享进程内配额和短缓存；不把含证书的 URL/响应错误写入异常。"""

    _lock = RLock()
    _bulk_lock = RLock()
    _calls: dict[str, deque] = {}
    _cache: dict[tuple, tuple[float, object]] = {}
    _bulk_attempts: dict[tuple, float] = {}

    def __init__(self, licence=None, *, timeout=15, base_url=None):
        self._licence = (licence if licence is not None else get_config().mairui_licence or '').strip()
        self.timeout = timeout
        self.deadline = None
        self.base_url = (base_url or os.getenv('MAIRUI_BASE_URL') or 'https://api.mairuiapi.com').rstrip('/')
        parsed = urlsplit(self.base_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError('MAIRUI_BASE_URL 必须是无凭据和查询参数的 HTTPS 地址')

    def get(self, path, *, params=None, ttl=0):
        if not self._licence:
            raise DataFetchError('未配置 MAIRUI_LICENCE')
        path = path.strip('/')
        key = (self.base_url, self._licence, path, tuple(sorted((params or {}).items())))
        # Only one-call-per-minute endpoints serialize network misses.
        bulk = path in {'hsrl/real/all', 'hsrl/ssjy/all'}
        with self._bulk_lock if bulk else nullcontext():
            with self._lock:
                now = time.monotonic()
                if self.deadline is not None and now >= self.deadline:
                    raise TimeoutError('麦蕊数据检查达到总时限，覆盖不完整')
                cached = self._cache.get(key)
                if cached and cached[0] > now:
                    return deepcopy(cached[1])
                if bulk:
                    bulk_key = (self.base_url, self._licence, path)
                    if now - self._bulk_attempts.get(bulk_key, float('-inf')) < 60:
                        raise RateLimitError('麦蕊全市场接口每分钟只能请求一次，请稍后重试')
                    self._bulk_attempts[bulk_key] = now
            url = f'{self.base_url}/{path}/{quote(self._licence, safe="")}'
            failure = None
            payload = None
            attempts = 1 if bulk else 2
            for attempt in range(attempts):
                timeout = self.timeout
                if self.deadline is not None:
                    timeout = min(timeout, self.deadline - time.monotonic())
                    if timeout <= 0:
                        raise TimeoutError('麦蕊数据检查达到总时限，覆盖不完整')
                with self._lock:
                    now = time.monotonic()
                    calls = self._calls.setdefault(self._licence, deque())
                    while calls and now - calls[0] >= 60:
                        calls.popleft()
                    if len(calls) >= 280:
                        raise RateLimitError('麦蕊本地每分钟请求预算已用完，请稍后重试')
                    calls.append(now)
                try:
                    response = requests.get(url, params=params, timeout=timeout, allow_redirects=False)
                    if response.status_code == 429:
                        failure = RateLimitError('麦蕊请求限流')
                        break
                    if response.status_code >= 500 and attempt + 1 < attempts:
                        continue
                    if response.status_code != 200:
                        failure = DataFetchError(f'麦蕊 HTTP {response.status_code}')
                        break
                    payload = response.json()
                    break
                except (requests.RequestException, ValueError):
                    failure = DataFetchError('麦蕊网络请求失败或返回非 JSON 数据')
            if self.deadline is not None and time.monotonic() >= self.deadline:
                raise TimeoutError('麦蕊数据检查达到总时限，覆盖不完整')
            if payload is None:
                # Raise outside the except block, without a credential-bearing
                # requests exception as __context__ (diagnostics unwrap chains).
                raise failure or DataFetchError('麦蕊返回空响应')
            if isinstance(payload, dict) and ('error' in payload or 'code' in payload and 'msg' in payload):
                raise DataFetchError('麦蕊数据不存在、参数错误或证书无对应权限')
            if not isinstance(payload, (list, dict)):
                raise DataFetchError('麦蕊响应类型错误')
            if ttl:
                with self._lock:
                    self._cache[key] = (time.monotonic() + ttl, deepcopy(payload))
                    expired = [k for k, v in self._cache.items() if v[0] <= time.monotonic()]
                    for k in expired:
                        self._cache.pop(k, None)
            return payload

    def frame(self, path, **kwargs):
        data = self.get(path, **kwargs)
        if isinstance(data, dict):
            data = [data]
        if any(not isinstance(row, dict) for row in data):
            raise DataFetchError('麦蕊表格响应格式错误')
        return pd.DataFrame(data)

    def calendar(self, start, end):
        days = []
        for year in range(int(start[:4]), int(end[:4]) + 1):
            rows = self.get(f'tcalendar/list/{year}', ttl=3600)
            if not isinstance(rows, list) or any(not re.fullmatch(r'\d{8}', str(day)) for day in rows):
                raise DataFetchError('麦蕊交易日历格式错误')
            days.extend(str(day) for day in rows if start <= str(day) <= end)
        return sorted(set(days))


def mairui_symbol(stock_code):
    """保留显式交易所；裸 000001 始终是深市股票。"""
    raw = str(stock_code).strip().upper()
    code = normalize_stock_code(raw)
    if not re.fullmatch(r'\d{6}', code):
        raise ValueError('麦蕊仅支持六位 A 股/指数/场内基金代码')
    for exchange in ('SH', 'SZ', 'BJ'):
        if raw.startswith(exchange) or raw.endswith('.' + exchange):
            return f'{code}.{exchange}'
    if raw.startswith('SS') or raw.endswith('.SS'):
        return f'{code}.SH'
    exchange = 'BJ' if is_bse_code(code) else 'SH' if code.startswith(('5', '6')) else 'SZ'
    return f'{code}.{exchange}'


def _number_columns(frame, columns):
    for col in columns:
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors='coerce')
    return frame


class MairuiFetcher(BaseFetcher):
    name = 'MairuiFetcher'
    priority = 2

    def __init__(self, *, client=None):
        self.client = client or MairuiClient()
        self.priority = int(os.getenv('MAIRUI_PRIORITY', '-1' if self.is_available() else '2'))

    def is_available(self):
        return bool(getattr(self.client, "_licence", None))

    _convert_stock_code = staticmethod(mairui_symbol)

    def stock_list(self):
        frames = [self.client.frame('hslt/list', ttl=3600), self.client.frame('bj/list/all', ttl=3600)]
        if any(df.empty or not {'dm', 'mc'}.issubset(df.columns) for df in frames):
            raise DataFetchError('麦蕊沪深/北交所股票列表不完整')
        frame = pd.concat(frames, ignore_index=True)
        frame['symbol'] = frame['dm'].map(normalize_stock_code)
        frame['ts_code'] = frame['dm'].map(mairui_symbol)  # Existing CSV contract.
        frame['name'] = frame['mc'].astype(str)
        frame = frame[frame['symbol'].str.match(r'^(?:00|30|60|68|4|8|92)\d*$', na=False)]
        return frame.drop_duplicates('symbol')[['ts_code', 'symbol', 'name']].reset_index(drop=True)

    def get_stock_list(self):
        try:
            frame = self.stock_list().rename(columns={'symbol': 'code'})
            # These optional classifications have no exact bulk counterpart.
            for col in ('industry', 'area', 'market'):
                frame[col] = None
            return frame[['code', 'name', 'industry', 'area', 'market']]
        except (DataFetchError, ValueError) as exc:
            logger.warning('麦蕊股票列表不可用：%s', exc)
            return None

    def get_stock_name(self, stock_code):
        code = normalize_stock_code(stock_code)
        target = parse_analysis_target(stock_code)
        if target.matched_index and target.asset_type == 'index':
            return target.matched_index.display_name
        try:
            if _is_etf_code(code):
                frame = self.client.frame('jj/etf', ttl=3600)
                return next((str(row['mc']) for row in frame.to_dict('records') if normalize_stock_code(str(row['dm'])) == code), None)
            frame = self.stock_list()
            rows = frame.loc[frame['symbol'] == code, 'name']
            return str(rows.iloc[0]) if not rows.empty else None
        except (DataFetchError, ValueError):
            return None

    def daily(self, stock_code, start_date, end_date, *, adjustment='n'):
        symbol = mairui_symbol(stock_code)
        code = normalize_stock_code(stock_code)
        target = parse_analysis_target(stock_code)
        index = target.asset_type == 'index'
        params = {'st': start_date.replace('-', ''), 'et': end_date.replace('-', '')}
        if index:
            path = f'hsindex/history/{symbol}/d'
        elif _is_etf_code(code):
            if adjustment != 'n':
                raise DataFetchError('麦蕊基金 K 线仅支持不复权')
            path = f'jj/lskx/{code}/Day'
        else:
            prefix = 'bj' if symbol.endswith('.BJ') else 'hsstock'
            path = f'{prefix}/history/{symbol}/d/{adjustment}'
        frame = self.client.frame(path, params=params)
        required = {'t', 'o', 'h', 'l', 'c', 'v', 'a'}
        if frame.empty or not required.issubset(frame.columns):
            raise DataFetchError('麦蕊历史行情为空或缺少 OHLC/量额字段')
        frame = frame.rename(columns={'t': 'date', 'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume', 'a': 'amount', 'pc': 'pre_close'})
        frame['date'] = pd.to_datetime(frame['date'], errors='coerce')
        frame = frame.dropna(subset=['date']).sort_values('date')
        frame = frame[(frame['date'] >= pd.Timestamp(start_date)) & (frame['date'] < pd.Timestamp(end_date) + pd.Timedelta(days=1))]
        _number_columns(frame, ['open', 'high', 'low', 'close', 'volume', 'amount', 'pre_close'])
        if not _is_etf_code(code):
            frame['volume'] *= 100  # Vendor daily bars: lots, verified against broker pv.
        else:
            # ETF endpoint actually returns 0 for unavailable turnover. Do not
            # turn that into a real zero; fail over when the amount is absent.
            if not (frame['amount'] > 0).any():
                raise DataFetchError('麦蕊 ETF 日线成交额缺失，使用其他行情源')
        if 'pre_close' in frame:
            frame['pct_chg'] = (frame['close'] / frame['pre_close'].where(frame['pre_close'] > 0) - 1) * 100
        else:
            frame['pct_chg'] = frame['close'].pct_change(fill_method=None) * 100
        frame['code'] = stock_code
        if frame.empty or frame['date'].duplicated().any():
            raise DataFetchError('麦蕊历史行情区间为空或日期重复')
        return frame.reset_index(drop=True)

    def _fetch_raw_data(self, stock_code, start_date, end_date):
        return self.daily(stock_code, start_date, end_date)

    def _normalize_data(self, df, stock_code):
        return df.copy()

    def get_realtime_quote(self, stock_code):
        code = normalize_stock_code(stock_code)
        symbol = mairui_symbol(stock_code)
        target = parse_analysis_target(stock_code)
        index = target.asset_type == 'index'
        path = (f'hsindex/real/time/{symbol}' if index else f'fd/real/time/{code}' if _is_etf_code(code)
                else f'bj/stock/real/time/{code}' if is_bse_code(code) else f'hsstock/real/time/{code}')
        try:
            frame = self.client.frame(path, ttl=15)
            if frame.empty:
                return None
            row = frame.iloc[0].to_dict()
            if not safe_float(row.get('p')):
                return None
            extra = {}
            if not index and not _is_etf_code(code):
                try:
                    extra_frame = self.client.frame(f'hsrl/ssjy/{code}', ttl=60)
                    if not extra_frame.empty:
                        extra = extra_frame.iloc[0].to_dict()
                except DataFetchError:
                    pass
            # Index pv is in lots too; stock broker pv is the unrounded shares.
            volume = safe_int(row.get('pv')) if not index else None
            if index and safe_float(row.get('v')) is not None:
                volume = int(float(row['v']) * 100)
            return UnifiedRealtimeQuote(
                code=code, name=self.get_stock_name(stock_code) or code, source=RealtimeSource.MAIRUI,
                price=safe_float(row.get('p')), change_pct=safe_float(row.get('pc')),
                change_amount=safe_float(row.get('ud')), volume=volume, amount=safe_float(row.get('cje')),
                open_price=safe_float(row.get('o')), high=safe_float(row.get('h')), low=safe_float(row.get('l')),
                pre_close=safe_float(row.get('yc')), turnover_rate=safe_float(row.get('tr', extra.get('hs'))),
                amplitude=safe_float(row.get('zf')), pe_ratio=safe_float(extra.get('pe')),
                pb_ratio=safe_float(row.get('pb_ratio', extra.get('sjl'))),
                total_mv=safe_float(extra.get('sz')), circ_mv=safe_float(extra.get('lt')),
                volume_ratio=safe_float(extra.get('lb')), change_60d=safe_float(extra.get('zdf60')),
                provider_timestamp=str(row.get('t') or '') or None,
            )
        except (DataFetchError, ValueError) as exc:
            logger.warning('麦蕊实时报价不可用 %s：%s', code, exc)
            return None

    def snapshot(self):
        raw = self.client.frame('hsrl/real/all', ttl=65)
        if raw.empty or not {'dm', 'p', 'pc', 'cje', 'sz', 'lt'}.issubset(raw.columns):
            raise DataFetchError('麦蕊全市场快照缺少必要字段')
        frame = raw.rename(columns={'dm': 'code', 'p': 'price', 'pc': 'change_pct', 'cje': 'amount',
                                    'sz': 'total_mv', 'lt': 'circ_mv', 'sjl': 'pb_ratio', 'lb': 'volume_ratio',
                                    'hs': 'turnover_rate'})
        frame['code'] = frame['code'].map(normalize_stock_code)
        listed = self.stock_list().rename(columns={'symbol': 'code'})
        frame = frame.merge(listed[['code', 'name']], on='code', how='inner', validate='one_to_one')
        frame = frame.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'yc': 'pre_close'})
        _number_columns(frame, ['price', 'change_pct', 'amount', 'total_mv', 'circ_mv', 'volume_ratio', 'turnover_rate', 'open', 'high', 'low', 'pre_close'])
        frame['trade_date'] = pd.to_datetime(frame.get('t'), errors='coerce').dt.strftime('%Y%m%d')
        frame['pe_ratio'] = float('nan')
        frame['pb_ratio'] = float('nan')
        frame = frame.reindex(columns=['code', 'name', 'price', 'change_pct', 'amount', 'total_mv',
                                       'circ_mv', 'pe_ratio', 'pb_ratio', 'volume_ratio', 'turnover_rate',
                                       'open', 'high', 'low', 'pre_close', 'trade_date'])
        frame.attrs['snapshot_source'] = 'mairui'
        frame.attrs['source_notes'] = ['行业分类缺少与旧数据源一致的批量映射；industry 留空']
        return frame

    def get_main_indices(self, region='cn'):
        if region != 'cn':
            return None
        result = []
        for symbol, name in [('000001.SH', '上证指数'), ('399001.SZ', '深证成指'), ('399006.SZ', '创业板指'),
                             ('000688.SH', '科创50'), ('000016.SH', '上证50'), ('000300.SH', '沪深300')]:
            value = self.get_realtime_quote(symbol)
            if value:
                result.append(dict(code=symbol.split('.')[0], name=name, current=value.price,
                                   change=value.change_amount, change_pct=value.change_pct,
                                   open=value.open_price, high=value.high, low=value.low,
                                   prev_close=value.pre_close, volume=value.volume / 100 if value.volume is not None else None, amount=value.amount,
                                   amplitude=value.amplitude))
        return result or None

    def get_market_stats(self):
        try:
            frame = self.client.frame('hsrl/real/all', ttl=65)
            frame['code'] = frame['dm'].map(normalize_stock_code)
            listed = self.stock_list().rename(columns={'symbol': 'code'})
            frame = frame.merge(listed[['code', 'name']], on='code', how='inner', validate='one_to_one')
            _number_columns(frame, ['p', 'yc', 'cje'])
            valid = frame[(frame['p'] > 0) & (frame['yc'] > 0) & (frame['cje'] > 0)].copy()
            # Pools provide exchange-observed limits, including first-listing exceptions.
            as_of = pd.to_datetime(valid['t'], errors='coerce').dt.date
            if valid.empty or as_of.isna().any() or as_of.nunique() != 1:
                raise DataFetchError('麦蕊全市场行情日期不一致')
            day = str(as_of.iloc[0])
            up = self.client.frame(f'hslt/ztgc/{day}', ttl=65)
            down = self.client.frame(f'hslt/dtgc/{day}', ttl=65)
            return dict(up_count=int((valid['p'] > valid['yc']).sum()),
                        down_count=int((valid['p'] < valid['yc']).sum()),
                        flat_count=int((valid['p'] == valid['yc']).sum()),
                        limit_up_count=len(up), limit_down_count=len(down),
                        total_amount=float(valid['cje'].sum()) / 1e8)
        except (DataFetchError, ValueError, KeyError) as exc:
            logger.warning('麦蕊市场统计不可用：%s', exc)
            return None

    def get_sector_rankings(self, n=5):
        # hibk/zjhhy currently mixes industry and concept boards despite its
        # label. Do not call this a same-taxonomy industry ranking.
        return None
