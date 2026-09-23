"""Trading decisions must be independent of financial valuation fields."""
from pathlib import Path

import pandas as pd
import pytest

from src.services.screening.filter import apply_hard_filters
from src.services.screening.models import Pick
from src.services.screening.post_analysis import _scorecard_delta
from src.services.screening.risk import assess_pick_risk
from src.services.screening.scorer import compute_screen_scores
from src.services.screening.strategy import load_strategy


@pytest.mark.parametrize('strategy_path', sorted(Path('src/services/screening/strategies').glob('*.yaml')), ids=lambda p:p.stem)
def test_all_screening_scores_and_filters_ignore_valuation(strategy_path):
    config = load_strategy(strategy_path).screening
    common = dict(name='量价样本', price=20, amount=500_000_000, total_mv=10_000_000_000,
                  change_pct=3, turnover_rate=5, volume_ratio=2, signal_score=80,
                  ma_bullish=True, price_above_ma20=True, macd_status="bullish",
                  breakout_20d_pct=1,range_20d_pct=20,volume_ratio_20d=1.4,body_pct=1,
                  consolidation_days_20d=12,pullback_to_ma20_pct=3,
                  volatility_20d_pct=25,max_drawdown_20d_pct=-5,atr_20_pct=3)
    frame = pd.DataFrame([{**common, 'pe_ratio':pe, 'pb_ratio':pb} for pe,pb in [(5,1),(500,30),(-2,-1),(None,None)]])
    scores = compute_screen_scores(frame, config)
    assert scores.screen_score.nunique() == 1
    assert 'factor_value_score' not in scores
    # All rows have identical technical conditions.
    assert len(apply_hard_filters(frame, config.hard_filters)) in (0,4)


def test_risk_and_scorecard_ignore_old_valuation_fields():
    def pick(pe,pb,value):
        return Pick(rank=1,code='000001',name='样本',final_score=70,screen_score=70,
                    pe_ratio=pe,pb_ratio=pb,factor_scores={'value':value,'momentum':80,'activity':80,'stability':70})
    normal=pick(10,1,90)
    extreme=pick(-10,20,0)
    assert assess_pick_risk(normal) == assess_pick_risk(extreme)
    assert _scorecard_delta(normal) == _scorecard_delta(extreme)
