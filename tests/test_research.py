import numpy as np
import pandas as pd
from research import Config, next_config, resample, simulate, score

def sample():
    n=1600
    times=pd.date_range("2025-01-01",periods=n,freq="15min",tz="UTC")
    x=100*np.exp(np.cumsum(np.random.default_rng(1).normal(0,.002,n)))
    return pd.DataFrame({"open":x,"high":x*1.003,"low":x*.997,"close":x,"volume":np.repeat(100,n)},index=times)

def test_config_reproducible():
    assert next_config("BTCUSDT",10)==next_config("BTCUSDT",10)
    assert next_config("BTCUSDT",10)!=next_config("BTCUSDT",11)

def test_resample_complete_intervals_only():
    x=sample()
    assert len(resample(x,"30m"))==800
    assert len(resample(x,"1h"))==400

def test_flat_no_trades():
    a=sample()
    a[["open","high","low","close"]]=100.
    funds=pd.DataFrame({"time":[0,10**15],"rate":[0.,0.],"mark":[100.,100.]})
    cfg=Config("BTCUSDT","15m","BREAK_LONG",12,.8,2,2,8,2,"ALL",.0002)
    assert simulate(a,funds,cfg)==[]

def test_empty_score():
    a=score([],pd.Timestamp("2025-01-01",tz="UTC"),pd.Timestamp("2025-03-01",tz="UTC"))
    assert a["exploratory_candidate"] is False

def test_no_lookahead_breakout():
    x=sample()
    x[["open","high","low","close"]]=100.
    x.loc[x.index[110],"high"]=120.
    x.loc[x.index[110],"close"]=119.
    cfg=Config("BTCUSDT","15m","BREAK_LONG",12,.8,2,2,8,2,"ALL",.0002)
    funds=pd.DataFrame({"time":[0,10**15],"rate":[0.,0.],"mark":[100.,100.]})
    from research import signals
    sig,_=signals(x,cfg,funds)
    assert sig[110]==1
