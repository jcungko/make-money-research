#!/usr/bin/env python3
"""Sensitivity backtest: same Exness Bid/Ask M5 bars, TP $0.10/$0.20/$0.30/$0.40 (and 0.50 control).
BUY and SELL simultaneously at every 5-minute candle open; exit by TP/SL or candle end.
0.01 standard lot each leg, USD account; SL=-10 USD. Research only.
"""
import csv, io, json, zipfile
from pathlib import Path
from collections import defaultdict
import m5_hedged_tp050_sl10_aug_oct2026 as baseline

TPS=(0.10,0.20,0.30,0.40,0.50)
OUT=Path('results/m5_hedged_tp_sweep_aug_oct2026')
MONTHS=baseline.MONTHS
SYMBOLS=baseline.SYMBOLS

def fresh():
    return dict(bars=0, trades=0, wins=0, losses=0, flat=0, tp_exits=0, sl_exits=0, candle_exits=0,
                ambiguous=0, pnl=0.0, gross_profit=0.0, gross_loss=0.0)

def finish(k,s):
    x=dict(symbol=k[0],month=k[1],tp_usd=k[2],**s)
    x['pnl_usd']=round(x.pop('pnl'),4)
    x['win_pct']=round(100*x['wins']/x['trades'],3) if x['trades'] else 0
    x['profit_factor']=round(x['gross_profit']/-x['gross_loss'],5) if x['gross_loss'] else None
    x['gross_profit']=round(x['gross_profit'],4)
    x['gross_loss']=round(x['gross_loss'],4)
    return x

def combine(rows):
    res=fresh()
    for r in rows:
        for k in res:
            if k=='bars': res[k]+=r[k]
            else: res[k]+=r[k]
    return res

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    month_stats=defaultdict(fresh)
    day_pnl=defaultdict(float)
    with (OUT/'trades.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f)
        writer.writerow(['symbol','month','timestamp_utc','tp_usd','side','exit_reason','ambiguous_tp_sl','pnl_usd'])
        for sym in SYMBOLS:
            path=Path(f'data/v17_exness_2026/{sym}_2026_UTC_7TF.zip')
            with zipfile.ZipFile(path) as archive:
                with archive.open(f'{sym}_M5_2026_UTC.csv') as stream:
                    reader=csv.DictReader(io.TextIOWrapper(stream,encoding='utf-8'))
                    for bar in reader:
                        timestamp=bar['timestamp_utc']
                        month=timestamp[:7]
                        if month not in MONTHS: continue
                        for tp in TPS:
                            baseline.TP=tp
                            stats=month_stats[(sym,month,tp)]
                            stats['bars']+=1
                            for side in ('BUY','SELL'):
                                pnl,reason,ambiguous=baseline.trade(sym,side,bar)
                                stats['trades']+=1
                                stats['wins']+=(pnl>1e-8)
                                stats['losses']+=(pnl< -1e-8)
                                stats['flat']+=(abs(pnl)<=1e-8)
                                stats['tp_exits']+=(reason=='TP')
                                stats['sl_exits']+=(reason=='SL')
                                stats['candle_exits']+=(reason=='CLOSE')
                                stats['ambiguous']+=ambiguous
                                stats['pnl']+=pnl
                                stats['gross_profit']+=max(pnl,0)
                                stats['gross_loss']+=min(pnl,0)
                                day_pnl[(sym,timestamp[:10],tp)]+=pnl
                                writer.writerow((sym,month,timestamp,tp,side,reason,int(ambiguous),f'{pnl:.6f}'))
    monthly=[finish((sym,mo,tp),month_stats[(sym,mo,tp)])
             for tp in TPS for sym in SYMBOLS for mo in MONTHS]
    by_symbol=[]
    totals=[]
    for tp in TPS:
        grand=fresh()
        for sym in SYMBOLS:
            summ=combine([month_stats[(sym,mo,tp)] for mo in MONTHS])
            grand=combine((grand,summ))
            by_symbol.append(finish((sym,'ALL',tp),summ))
        totals.append(finish(('ALL','ALL',tp),grand))
    with (OUT/'monthly.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,monthly[0].keys());writer.writeheader();writer.writerows(monthly)
    with (OUT/'by_symbol.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,by_symbol[0].keys());writer.writeheader();writer.writerows(by_symbol)
    with (OUT/'by_tp.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,totals[0].keys());writer.writeheader();writer.writerows(totals)
    with (OUT/'daily.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(['symbol','date_utc','tp_usd','pnl_usd'])
        for (sym,date,tp),pnl in sorted(day_pnl.items()):
            writer.writerow([sym,date,tp,round(pnl,6)])
    expected={'GBPUSD':-3329.33,'EURUSD':-2681.41,'USDJPY':-2287.4035}
    for row in by_symbol:
        if row['tp_usd']==0.50 and abs(row['pnl_usd']-expected[row['symbol']])>0.02:
            raise RuntimeError(f'Baseline $0.50 mismatch: {row}')
    payload=dict(parameters=dict(tps_usd=TPS,sl_usd=-10.0,lot_per_leg=0.01,
            symbols=SYMBOLS,months=MONTHS,execution='Both legs each M5 open; TP or SL intrabar; otherwise close at same candle end',
            prices='Archived Exness Bid/Ask M5 OHLC. Spread included by opposing quote',
            ambiguity='SL-first when both extrema touched; tick-order unavailable',
            usd_jpy_conversion='Approximate with entry mid rate; account USD',
            excluded_costs=['commission','slippage','swap']),
            monthly=monthly,by_symbol=by_symbol,totals=totals)
    (OUT/'summary.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print('TP_SWEEP_RESULT_START')
    print(json.dumps(dict(monthly=[dict(symbol=r['symbol'],month=r['month'],tp=r['tp_usd'],
                             trades=r['trades'],win_pct=r['win_pct'],pnl=r['pnl_usd']) for r in monthly],
             by_symbol=[dict(symbol=r['symbol'],tp=r['tp_usd'],trades=r['trades'],win_pct=r['win_pct'],pnl=r['pnl_usd'],pf=r['profit_factor']) for r in by_symbol],
             totals=[dict(tp=r['tp_usd'],trades=r['trades'],win_pct=r['win_pct'],pnl=r['pnl_usd'],pf=r['profit_factor']) for r in totals])))
    print('TP_SWEEP_RESULT_END')

if __name__=='__main__':
    main()
