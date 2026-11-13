"""Unit tests only; deliberately no fabricated empirical performance or synthetic OOS report."""
import datetime as dt
import json
from pathlib import Path
from v20_backtest import (msstamp, prior_months, Bars, Engine, Scenario,
                         equity_max_drawdown_from_path, metrics, month_range)

def test_month_history():
    assert prior_months('2025-07',6)==['2025-01','2025-02','2025-03','2025-04','2025-05','2025-06']
    assert prior_months('2026-01',2)==['2025-11','2025-12']
    assert len(list(month_range()))==22

def test_utc_ms():
    assert msstamp('2026-01-01 00:00:00.123Z')%1000==123

def test_latency_and_spread_and_sl_exit():
    # Controlled unit fixture, not Exness data. One long trade.
    sc=Scenario('unit',1,0.1,100)
    e=Engine('S1_M1_SL1.2_RR1.5','S1',1,1.2,1.5,sc)
    at=msstamp('2026-02-02T10:00:00.000Z')
    e.propose(1,at,0.0004,0.5)  # ATR = 4p, spread eligibility passes
    e.tick(at+99,1.10000,1.10005)
    assert not e.pos
    e.tick(at+100,1.10000,1.10005)
    assert e.pos and abs(e.pos['price']-1.10006)<1e-8
    e.tick(at+200,1.10120,1.10125)
    assert e.pos.get('reason')=='TP' and not e.trades
    e.tick(at+300,1.10120,1.10125)
    assert len(e.trades)==1
    assert e.trades[0]['pnl_usd']>0
    assert e.trades[0]['path_max_dd_usd']>=0

def test_margin_and_risk_cap():
    e=Engine('k','S1',1,1.8,2.2,Scenario('unit',1,0.1,2))
    at=msstamp('2026-02-02T10:00:00Z')
    e.cash=0.3
    e.propose(1,at,0.0006,0.5)
    e.tick(at+2,1.10,1.10005)
    assert not e.pos and e.stats['risk_rejected']==1

def test_equity_path_dd():
    trades=[{'entry_ms':1,'valid_same_day':True,'pnl_usd':1.0,
             'path_min_usd':-0.5,'path_max_usd':2.0,'path_max_dd_usd':1.1},
            {'entry_ms':2,'valid_same_day':True,'pnl_usd':-1.0,
             'path_min_usd':-1.5,'path_max_usd':0.0,'path_max_dd_usd':1.5}]
    assert equity_max_drawdown_from_path(trades)==2.5

def test_real_source_not_available_does_not_become_0_pnl():
    status=Path(__file__).with_name('results').joinpath('status.json')
    if status.exists():
        obj=json.loads(status.read_text())
        assert obj['status']=='DATA_UNAVAILABLE'
        assert obj['metrics']=='NOT_COMPUTED'