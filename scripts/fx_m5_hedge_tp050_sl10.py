#!/usr/bin/env python3
"""Research-only M5 hedge backtest. BUY+SELL each bar, 0.01 lots, TP $0.5 SL $10.
Uses Exness V17 Bid/Ask M5, accounts for floating losses and SL-first M5 ambiguity.
No commission, swap, slippage, margin limits, or tick-order reconstruction.
"""
import io,json,csv,gzip,zipfile
from pathlib import Path
import pandas as pd
import numpy as np

OUT=Path('results/fx_m5_hedge_tp050_sl10_2026')
OUT.mkdir(parents=True,exist_ok=True)
SYMS=('EURUSD','GBPUSD','USDJPY')
T0=pd.Timestamp('2026-08-01',tz='UTC')
T1=pd.Timestamp('2026-11-01',tz='UTC')
UNITS=1000.0 # 0.01 lot * 100000
TP=0.50; SL=10.0

def pnl(sym,side,ent,ex):
    return side*(ex-ent)*UNITS/(ex if sym=='USDJPY' else 1.0)

def targets(sym,side,ent):
    if sym=='USDJPY':
        return ent/(1-side*TP/UNITS),ent/(1+side*SL/UNITS)
    return ent+side*TP/UNITS,ent-side*SL/UNITS

def run(sym):
    source=Path(f'data/v17_exness_2026/{sym}_2026_UTC_7TF.zip')
    with zipfile.ZipFile(source) as z:
        manifest=json.loads(z.read('manifest.json'))
        assert manifest['symbol']==sym and manifest['year']==2026
        b=pd.read_csv(io.BytesIO(z.read(f'{sym}_M5_2026_UTC.csv')))
    b['timestamp_utc']=pd.to_datetime(b.timestamp_utc,utc=True)
    b=b.loc[(b.timestamp_utc>=T0)&(b.timestamp_utc<T1)].sort_values('timestamp_utc')
    assert len(b)>18000 and b.timestamp_utc.is_unique
    assert (b.ask_open>=b.bid_open).all() and (b.ask_close>=b.bid_close).all()
    for s in ('bid','ask'):
        assert (b[f'{s}_high']>=b[[f'{s}_open',f'{s}_close',f'{s}_low']].max(axis=1)).all()
        assert (b[f'{s}_low']<=b[[f'{s}_open',f'{s}_close']].min(axis=1)).all()
    act={s:{'ent':np.array([],dtype=float),'tp':np.array([],dtype=float),
            'sl':np.array([],dtype=float),'time':np.array([],dtype='int64')} for s in (1,-1)}
    res={m:{'entries':0,'tp':0,'sl':0,'realized_usd':0.0,
            'ambiguous_sl_first':0,'sl_gap':0} for m in ('2026-08','2026-09','2026-10')}
    cash=0.0;prev_equity=0.0; max_open=0; peak=0.0; maxdd=0.0
    trades=[];lastmon=None;lastclose=None

    def floating(bid,ask):
        return sum(float(pnl(sym,side,a['ent'],bid if side==1 else ask).sum())
                   for side,a in act.items())

    def finish(mon,bid,ask):
        nonlocal prev_equity
        r=res[mon]
        r['open_buys']=len(act[1]['ent']);r['open_sells']=len(act[-1]['ent'])
        r['open_positions']=r['open_buys']+r['open_sells']
        r['cumulative_realized_usd']=cash
        r['floating_unrealized_usd']=floating(bid,ask)
        r['cumulative_equity_pnl_usd']=cash+r['floating_unrealized_usd']
        r['monthly_equity_change_usd']=r['cumulative_equity_pnl_usd']-prev_equity
        prev_equity=r['cumulative_equity_pnl_usd']

    cols=['bid_open','bid_high','bid_low','bid_close','ask_open','ask_high','ask_low','ask_close']
    data=b[cols].to_numpy(dtype=float)
    for i,(bar,timestamp) in enumerate(zip(data,b.timestamp_utc)):
        mon=timestamp.strftime('%Y-%m')
        bo,bh,bl,bc,ao,ah,al,ac=bar
        if lastmon is not None and mon!=lastmon:finish(lastmon,*lastclose)
        lastmon=mon;lastclose=(bc,ac)
        r=res[mon]
        # Open BUY at ask and SELL at bid, simultaneously each M5.
        for side,entry in ((1,ao),(-1,bo)):
            a=act[side];target,stop=targets(sym,side,entry)
            a['ent']=np.append(a['ent'],entry)
            a['tp']=np.append(a['tp'],target)
            a['sl']=np.append(a['sl'],stop)
            a['time']=np.append(a['time'],i)
            r['entries']+=1
        for side in (1,-1):
            a=act[side]
            op,hi,lo=(bo,bh,bl) if side==1 else (ao,ah,al)
            old=a['time']<i
            gap_sl=old & ((op<=a['sl']) if side==1 else (op>=a['sl']))
            gap_tp=old & ((op>=a['tp']) if side==1 else (op<=a['tp']))
            touch_sl=(lo<=a['sl']) if side==1 else (hi>=a['sl'])
            touch_tp=(hi>=a['tp']) if side==1 else (lo<=a['tp'])
            sl_hit=gap_sl | (touch_sl & ~gap_tp)
            tp_hit=~sl_hit & (gap_tp|touch_tp)
            gone=sl_hit|tp_hit
            ix=np.flatnonzero(gone)
            if len(ix):
                price=np.where(sl_hit[ix],np.where(gap_sl[ix],op,a['sl'][ix]),a['tp'][ix])
                val=pnl(sym,side,a['ent'][ix],price)
                change=float(val.sum()); cash+=change;r['realized_usd']+=change
                r['sl']+=int(sl_hit[ix].sum());r['tp']+=int(tp_hit[ix].sum())
                amb=sl_hit[ix]&touch_sl[ix]&touch_tp[ix]&~gap_sl[ix]
                r['ambiguous_sl_first']+=int(amb.sum())
                r['sl_gap']+=int(gap_sl[ix].sum())
                for j,k in enumerate(ix):
                    trades.append((str(b.timestamp_utc.iloc[int(a['time'][k])]),str(timestamp),
                        sym,'BUY' if side==1 else 'SELL',float(a['ent'][k]),float(price[j]),
                        'SL_GAP' if gap_sl[k] else ('SL_AMBIG' if amb[j] else 'SL') if sl_hit[k] else 'TP',
                        float(val[j])))
                keep=~gone
                for key in a:a[key]=a[key][keep]
        nopen=sum(len(a['ent']) for a in act.values()); max_open=max(max_open,nopen)
        equity=cash+floating(bc,ac)
        peak=max(peak,equity);maxdd=max(maxdd,peak-equity)
    finish(lastmon,*lastclose)
    with gzip.open(OUT/f'{sym}_trades.csv.gz','wt',newline='') as f:
        w=csv.writer(f);w.writerow(['entry_utc','exit_utc','symbol','side','entry_price','exit_price','reason','pnl_usd'])
        w.writerows(trades)
    for r in res.values():
        r['closed']=r['sl']+r['tp']
        r['closed_win_rate_pct']=100*r['tp']/r['closed'] if r['closed'] else 0
        for k,v in list(r.items()):
            if isinstance(v,float):r[k]=round(v,4)
    result={'source':str(source),'bars':len(b),'start_utc':str(b.timestamp_utc.iloc[0]),
        'end_utc':str(b.timestamp_utc.iloc[-1]),
        'mean_spread_pips':round(float(((b.ask_open-b.bid_open)/(0.01 if sym=='USDJPY' else 0.0001)).mean()),4),
        'max_concurrent_positions':max_open,'max_m5_drawdown_usd':round(maxdd,4),
        'monthly':res,'total':{'entries':sum(r['entries'] for r in res.values()),
            'tp':sum(r['tp'] for r in res.values()),'sl':sum(r['sl'] for r in res.values()),
            'realized_usd':round(cash,4),'floating_unrealized_usd':round(floating(*lastclose),4),
            'end_equity_pnl_usd':round(cash+floating(*lastclose),4),
            'open_positions':sum(len(a['ent']) for a in act.values())}}
    print(json.dumps({'symbol':sym,'total':result['total'],'monthly':res},ensure_ascii=False),flush=True)
    return result

if __name__=='__main__':
    report={'name':'M5 simultaneous BUY and SELL 0.01 lot TP+0.50USD SL-10USD',
      'period':'2026-08-01..2026-10-31 UTC','per_trade_lot':0.01,'tp_usd':TP,'sl_usd':SL,
      'entry':'Each observed M5 open at BUY ask / SELL bid, no cap on overlapping positions',
      'exit':'Trigger vs M5 bid/ask highs/lows. SL first when intra-M5 TP/SL both reached; stop gaps fill at observed open, favorable TP gaps at target',
      'usd_jpy_conversion':'Profit JPY converted to USD at exit price',
      'limitations':'OHLC is not tick sequence; no swap, commission, slippage, margin, broker restrictions; mark-to-market open positions at each month close',
      'symbols':{s:run(s) for s in SYMS}}
    (OUT/'summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    with (OUT/'monthly.csv').open('w',newline='') as f:
        w=csv.writer(f)
        fields=['symbol','month','entries','closed','tp','sl','closed_win_rate_pct','realized_usd',
                'floating_unrealized_usd','monthly_equity_change_usd','cumulative_equity_pnl_usd',
                'open_positions','ambiguous_sl_first','sl_gap']
        w.writerow(fields)
        for sym,x in report['symbols'].items():
            for mon,r in x['monthly'].items():w.writerow([sym,mon]+[r.get(k) for k in fields[2:]])
    print('COMPLETE',OUT/'summary.json',flush=True)
