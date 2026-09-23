"""Mairui migration contracts: observed units, security identity, missing evidence."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
import requests

from data_provider.base import DataFetchError, RateLimitError
from data_provider.mairui_fetcher import MairuiClient, MairuiFetcher
from data_provider.gap_limit_up import GapLimitUpDataSource
from src.services.screening.gap_limit_up import check_price_gap
from src.services.screening.models import GapLimitUpConfig


class FixtureClient:
    _licence = 'fixture'

    def __init__(self, data):
        self.data = data
        self.paths = []

    def frame(self, path, **kwargs):
        self.paths.append((path, kwargs))
        value = self.data[path]
        if isinstance(value, Exception):
            raise value
        return pd.DataFrame(deepcopy(value if isinstance(value, list) else [value]))


@pytest.fixture(autouse=True)
def clear_client_state():
    MairuiClient._cache.clear()
    MairuiClient._calls.clear()
    MairuiClient._bulk_attempts.clear()


@pytest.mark.parametrize('payload', [[{'p': 10}], {'p': 10}])
def test_https_transport_accepts_record_and_array_without_sdk(monkeypatch, payload):
    get = Mock(return_value=SimpleNamespace(status_code=200, json=lambda: payload))
    monkeypatch.setattr('data_provider.mairui_fetcher.requests.get', get)
    client = MairuiClient('fixture', timeout=7)
    assert client.frame('hsrl/ssjy/000001').iloc[0]['p'] == 10
    assert get.call_args.kwargs['allow_redirects'] is False
    assert get.call_args.kwargs['timeout'] == 7
    assert get.call_args.args[0].startswith('https://api.mairuiapi.com/')


@pytest.mark.parametrize('failure', ['exception', 'error', 'redirect', 'rate_limit', 'non_json'])
def test_provider_failure_does_not_leak_credential_in_exception_chain(monkeypatch, failure):
    key = 'secret-test-licence'
    if failure == 'exception':
        get = Mock(side_effect=requests.ConnectionError('https://api.mairuiapi.com/x/' + key))
    else:
        def payload():
            if failure == 'non_json':
                raise ValueError(key)
            return {'error': key}
        get = Mock(return_value=SimpleNamespace(status_code={'redirect': 302, 'rate_limit': 429}.get(failure, 200), json=payload))
    monkeypatch.setattr('data_provider.mairui_fetcher.requests.get', get)
    with pytest.raises((DataFetchError, RateLimitError)) as error:
        MairuiClient(key).get('x')
    assert key not in str(error.value)
    assert error.value.__context__ is None
    assert error.value.__cause__ is None


def test_all_market_request_is_shared_between_clients(monkeypatch):
    get = Mock(return_value=SimpleNamespace(status_code=200, json=lambda: [{'dm': '000001'}]))
    monkeypatch.setattr('data_provider.mairui_fetcher.requests.get', get)
    a = MairuiClient('fixture').get('hsrl/real/all', ttl=65)
    a[0]['dm'] = 'changed'
    assert MairuiClient('fixture').get('hsrl/real/all', ttl=65)[0]['dm'] == '000001'
    assert get.call_count == 1


def test_daily_history_converts_lots_to_shares_and_preserves_yuan():
    client = FixtureClient({'hsstock/history/000001.SZ/d/n': [
        dict(t='2026-09-22', o=11.70, h=11.75, l=11.62, c=11.71, pc=11.73, v=759457, a=887703100),
    ]})
    result = MairuiFetcher(client=client).daily('SZ000001', '20260922', '20260922')
    assert result.iloc[0]['volume'] == 75_945_700
    assert result.iloc[0]['amount'] == 887_703_100
    assert result.iloc[0]['pct_chg'] == pytest.approx((11.71 / 11.73 - 1) * 100)


def test_daily_uses_index_and_bse_endpoints_without_symbol_collision():
    row = [dict(t='2026-09-22', o=10, h=11, l=9, c=10, pc=10, v=100, a=100000)]
    client = FixtureClient({'hsindex/history/000001.SH/d': row, 'bj/history/920000.BJ/d/fr': row})
    fetcher = MairuiFetcher(client=client)
    fetcher.daily('SH000001', '20260922', '20260922')
    fetcher.daily('BJ920000', '20260922', '20260922', adjustment='fr')
    assert [x[0] for x in client.paths] == ['hsindex/history/000001.SH/d', 'bj/history/920000.BJ/d/fr']


def test_etf_missing_turnover_fails_over_instead_of_zero():
    client = FixtureClient({'jj/lskx/510050/Day': [dict(t='2026-09-22', o=3, h=3.1, l=2.9, c=3, v=1000, a=0)]})
    with pytest.raises(DataFetchError, match='成交额缺失'):
        MairuiFetcher(client=client).daily('510050', '20260922', '20260922')


def test_quote_uses_raw_broker_shares_not_rounded_network_volume(monkeypatch):
    client = FixtureClient({
        'hsstock/real/time/000001': dict(p=11.71, v=759457, pv=75945732, cje=887703100, t='2026-09-22 15:00:00'),
        'hsrl/ssjy/000001': dict(v=75.95, sz=227243302099, lt=227240571245, lb=.93, pe=4.42),
    })
    fetcher = MairuiFetcher(client=client)
    monkeypatch.setattr(fetcher, 'get_stock_name', lambda _: '平安银行')
    value = fetcher.get_realtime_quote('SZ000001')
    assert value.volume == 75_945_732
    assert value.amount == 887_703_100
    assert value.total_mv == 227_243_302_099
    assert value.provider_timestamp == '2026-09-22 15:00:00'


def test_snapshot_needs_only_market_data_and_a_share_universe():
    client = FixtureClient({
        'hsrl/real/all': [dict(dm=code, p=10, pc=1, cje=1000, sz=10000, lt=8000, pe=99, t='2026-09-22 15:35:00') for code in ['000001','920000','900001']],
        'hslt/list': [dict(dm='000001.SZ', mc='平安银行')],
        'bj/list/all': [dict(dm='920000.BJ', mc='安徽凤凰')],
    })
    result = MairuiFetcher(client=client).snapshot().set_index('code')
    assert set(result.index) == {'000001', '920000'}
    assert pd.isna(result.loc['000001', 'pe_ratio'])
    assert all(path != 'himk/syl' for path, _ in client.paths)
    assert pd.isna(result.loc['920000', 'pe_ratio'])
    assert result.loc['000001', 'amount'] == 1000
    assert result.loc['000001', 'total_mv'] == 10000




def test_adjusted_bars_reject_uncertain_cent_gap_and_accept_confirmed_gap():
    days = ['20260918','20260921']
    rows = [dict(trade_date=d, open=10, high=10.2, low=9.9, close=10, vol=100, up_limit=11,
                 adjusted_open=100, adjusted_high=102, adjusted_low=99.0, adjusted_close=100) for d in days]
    for row in rows[1:]:
        row.update(open=10.5, high=11, low=10.4, close=11, adjusted_open=105, adjusted_high=110, adjusted_low=104, adjusted_close=110)
    frame = pd.DataFrame(rows)
    result = check_price_gap(frame, days, GapLimitUpConfig())
    assert result['gap_lower_current_basis'] == pytest.approx(10.2)
    frame.loc[1, 'adjusted_low'] = 102.005
    with pytest.raises(ValueError, match='未形成完整'):
        check_price_gap(frame, days, GapLimitUpConfig())


def test_stock_list_script_keeps_csv_contract_and_does_not_overwrite_on_error(tmp_path, monkeypatch):
    from scripts import fetch_mairui_stock_list as script
    monkeypatch.setattr(script, 'OUTPUT_DIR', tmp_path)
    monkeypatch.setattr(script, 'MairuiFetcher', lambda: SimpleNamespace(stock_list=lambda: pd.DataFrame([dict(ts_code='000001.SZ', symbol='000001', name='平安银行')])))
    assert script.main([]) == 0
    original = (tmp_path / 'stock_list_a.csv').read_bytes()
    monkeypatch.setattr(script, 'MairuiFetcher', Mock(side_effect=DataFetchError('unavailable')))
    assert script.main([]) == 1
    assert (tmp_path / 'stock_list_a.csv').read_bytes() == original





def test_migration_diagnostics_redact_path_licence():
    from src.llm.diagnostic_redaction import redact_diagnostic_text
    text = redact_diagnostic_text('GET https://api.mairuiapi.com/hslt/list/short-secret')
    assert 'short-secret' not in text


def test_market_review_preserves_its_lot_volume_contract(monkeypatch):
    fetcher = MairuiFetcher(client=FixtureClient({}))
    value = SimpleNamespace(price=10, change_amount=1, change_pct=1, open_price=9, high=11, low=8,
                            pre_close=9, volume=123400, amount=1000000, amplitude=3)
    monkeypatch.setattr(fetcher, 'get_realtime_quote', lambda _: value)
    assert fetcher.get_main_indices()[0]['volume'] == 1234


def test_failed_bulk_call_is_not_retried_within_one_minute(monkeypatch):
    get = Mock(return_value=SimpleNamespace(status_code=503))
    monkeypatch.setattr('data_provider.mairui_fetcher.requests.get', get)
    with pytest.raises(DataFetchError):
        MairuiClient('fixture').get('hsrl/real/all', ttl=65)
    with pytest.raises(RateLimitError, match='每分钟只能请求一次'):
        MairuiClient('fixture').get('hsrl/real/all', ttl=65)
    assert get.call_count == 1


def test_retry_consumes_shared_request_budget(monkeypatch):
    from collections import deque
    import time
    MairuiClient._calls['fixture'] = deque([time.monotonic()] * 279)
    get = Mock(return_value=SimpleNamespace(status_code=503))
    monkeypatch.setattr('data_provider.mairui_fetcher.requests.get', get)
    with pytest.raises(RateLimitError):
        MairuiClient('fixture').get('hslt/list')
    assert get.call_count == 1


@pytest.fixture
def instrument_source(monkeypatch):
    from datetime import date
    monkeypatch.setattr(GapLimitUpDataSource, '_completed_date', staticmethod(lambda: date(2026, 9, 21)))
    rows = [
        dict(t='2026-09-18', o=10, h=10.2, l=9.9, c=10, pc=10, v=100, a=100000),
        dict(t='2026-09-21', o=10.5, h=11, l=10.4, c=11, pc=10, v=200, a=200000),
    ]
    client = FixtureClient({
        'hsstock/history/000001.SZ/d/n': rows,
        'hsstock/history/000001.SZ/d/br': rows,
        'hsstock/instrument/000001.SZ': dict(ei='SZ', ii='000001', pc=10, up=11),
    })
    return GapLimitUpDataSource(60, client=client), client


def test_instrument_confirms_tonights_new_gap(instrument_source):
    source, _ = instrument_source
    bars = source.prices('000001', '20260918', '20260921', '20260921')
    evidence = check_price_gap(bars, ['20260918', '20260921'], GapLimitUpConfig())
    assert evidence['event_trade_date'] == '20260921'
    assert evidence['observation_days'] == 0
    assert bars.attrs['limit_up_source'] == 'hsstock/instrument/000001.SZ'


@pytest.mark.parametrize('change,reason', [
    ({'pc': 9}, '前收盘价不一致'),
    ({'up': None}, '涨停价不可用'),
    ({'up': 0}, '涨停价不可用'),
    ({'ii': '000002'}, '证券身份不一致'),
])
def test_instrument_rejects_stale_or_invalid_data(instrument_source, change, reason):
    source, client = instrument_source
    client.data['hsstock/instrument/000001.SZ'].update(change)
    with pytest.raises(ValueError, match=reason):
        source.prices('000001', '20260918', '20260921', '20260921')


def test_close_below_instrument_limit_is_not_limit_up(instrument_source):
    source, client = instrument_source
    client.data['hsstock/instrument/000001.SZ']['up'] = 12
    bars = source.prices('000001', '20260918', '20260921', '20260921')
    with pytest.raises(ValueError, match='未收盘封涨停'):
        check_price_gap(bars, ['20260918', '20260921'], GapLimitUpConfig())


def test_current_instrument_cannot_be_used_for_past_event(instrument_source):
    source, _ = instrument_source
    with pytest.raises(ValueError, match='不能用当日限价判断历史事件'):
        source.prices('000001', '20260917', '20260918', '20260918')


def test_instrument_bse_route(instrument_source):
    source, client = instrument_source
    client.data = {path.replace('hsstock/history/000001.SZ', 'bj/history/920000.BJ'): value for path, value in client.data.items()}
    client.data['bj/instrument/920000.BJ'] = dict(ei='BJ', ii='920000', pc=10, up=13)
    bars = source.prices('920000', '20260918', '20260921', '20260921')
    assert bars['up_limit'].iloc[-1] == 13
    assert bars.attrs['limit_up_source'] == 'bj/instrument/920000.BJ'


def test_replay_cannot_roll_back_to_yesterday_before_close(monkeypatch):
    from datetime import datetime
    class BeforeClose(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 23, 12, 0, tzinfo=tz)
    monkeypatch.setattr('data_provider.gap_limit_up.datetime', BeforeClose)
    with pytest.raises(ValueError, match='22:00'):
        GapLimitUpDataSource._completed_date()
