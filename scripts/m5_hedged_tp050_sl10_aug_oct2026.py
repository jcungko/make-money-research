#!/usr/bin/env python3
"""Research: BUY+SELL at every M5 open, TP $0.50 SL -$10, exit at M5 close.
0.01 standard lot, USD account, Exness archived BID/ASK OHLC. SL wins ambiguous bars.
"""
import csv, io, json, zipfile
from collections import defaultdict
from pathlib import Path

MONTHS = ('2026-08','2026-09','2026-10')
SYMBOLS = ('GBPUSD','EURUSD','USDJPY')
SIZE=1000.0
TP=0.50
SL=-10.0

def trade(sym,side,b):
    bid_o,ask_o,bid_h,ask_h,bid_l,ask_l,bid_c,ask_c=(
        float(b[k]) for k in ('bid_open','ask_open','bid_high','ask_high','bid_low','ask_low','bid_close','ask_close'))
    conversion = SIZE/((bid_o+ask_o)*0.5) if sym=='USDJPY' else SIZE
    if side=='BUY':
        ent=ask_o
        sl_hit=(bid_l-ent)*conversion <= SL
        tp_hit=(bid_h-ent)*conversion >= TP
        close=(bid_c-ent)*conversion
    else:
        ent=bid_o
        sl_hit=(ent-ask_h)*conversion <= SL
        tp_hit=(ent-ask_l)*conversion >= TP
        close=(ent-ask_c)*conversion
    if sl_hit: return (SL,'SL', bool(tp_hit))
    if tp_hit: return (TP,'TP',False)
    return (close,'CLOSE',False)

def main():
    stats=defaultdict(lambda:dict(bars=0,trades=0,win=0,loss=0,flat=0,tp=0,sl=0,close=0,ambiguous=0,pnl=0.0,gross_profit=0.0,gross_loss=0.0))
    daily=defaultdict(float)
    out=Path('results/m5_hedged_tp050_sl10_aug_oct2026')
    out.mkdir(parents=True,exist_ok=True)
    with (out/'trades.csv').open('w',newline='',encoding='utf-8') as f:
      w=csv.writer(f)
      w.writerow(['symbol','month','timestamp_utc','side','exit_reason','ambiguous_tp_sl','pnl_usd'])
      for sym in SYMBOLS:
        zpath=Path(f'data/v17_exness_2026/{sym}_2026_UTC_7TF.zip')
        with zipfile.ZipFile(zpath) as z:
          with z.open(f'{sym}_M5_2026_UTC.csv') as bz:
            rdr=csv.DictReader(io.TextIOWrapper(bz,encoding='utf-8'))
            for b in rdr:
              ts=b['timestamp_utc']
              mo=ts[:7]
              if mo not in MONTHS: continue
              s=stats[(sym,mo)]
              s['bars']+=1
              for side in ('BUY','SELL'):
                p,reason,amb=trade(sym,side,b)
                s['trades']+=1
                s['pnl']+=p
                s['gross_profit']+=max(0,p)
                s['gross_loss']+=min(0,p)
                s['win']+=p>1e-8
                s['loss']+=p< -1e-8
                s['flat']+=abs(p)<=1e-8
                s[reason.lower()]+=1
                s['ambiguous']+=amb
                daily[(sym,ts[:10])]+=p
                w.writerow([sym,mo,ts,side,reason,int(amb),f'{p:.6f}'])
    summary=[]
    for sym in SYMBOLS:
      for mo in MONTHS:
        d=dict(symbol=sym,month=mo,**stats[(sym,mo)])
        d['pnl']=round(d['pnl'],4)
        d['win_rate_pct']=round(100*d['win']/d['trades'],3) if d['trades'] else None
        d['profit_factor']=round(d['gross_profit']/-d['gross_loss'],5) if d['gross_loss'] else None
        summary.append(d)
    with (out/'monthly.csv').open('w',newline='',encoding='utf-8') as f:
      wr=csv.DictWriter(f,fieldnames=list(summary[0]))
      wr.writeheader(); wr.writerows(summary)
    (out/'summary.json').write_text(json.dumps(dict(assumptions=dict(lot=0.01,units=SIZE,tp_usd=TP,sl_usd=SL,account='USD',execution='open BOTH each M5; force-close each M5 end',pricing='BUY at ask open; SELL at bid open; exit at opposing quote; within-bar extremes',both_hit='Conservative SL-first; intrabar sequence unknown',usdjpy_conversion='Entry-mid-rate approximation; 5-minute rate drift ignored',commission='not included; spread implicitly included',slippage='not included'), monthly=summary),indent=2),encoding='utf-8')
    with (out/'daily.csv').open('w',newline='',encoding='utf-8') as f:
      wr=csv.writer(f);wr.writerow(['symbol','date_utc','pnl_usd'])
      for (sym,date),val in sorted(daily.items()): wr.writerow([sym,date,round(val,6)])
    print('BACKTEST_RESULT_START')
    print(json.dumps(summary,ensure_ascii=False))
    print('BACKTEST_RESULT_END')
    print('NOTE: BID/ASK OHLC M5, ambiguous both-hit treated as SL. No commission/slippage. Not tick-exact.')

if __name__=='__main__': main()
