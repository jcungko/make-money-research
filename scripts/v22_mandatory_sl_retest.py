#!/usr/bin/env python3
"""V22 | Hard Stop Loss full historical and November-to-date backtest for 276 portfolios.

Each EA entry is reproduced from the original V22 script. A mandatory stop is
attached at entry; M5 Bid/Ask extremes determine stop hits, and adverse
gapped-open stop fills execute at the worse quote, never magically at SL.
2025 and Jan-Oct 2026 are replayed; 2026-11 is partial through 2026-11-12
19:55 UTC. Results are exploratory, and a bar extreme does not guarantee a fill.
"""
import csv
import json
import math
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import v22_nov2026_filter as nov

HIST=Path("data/v22_exness")
MONTH_FRAMES=Path("results/v22_nov2026_filter/november_candles")
INPUT=Path("results/v22_nov2026_win_trade_ranking/qualified_win_gt_loss_by_profit.csv")
OUT=Path("results/v22_sl_backtest_2025_2026_nov")
MONTHS=nov.model.MONTHS + [202611]
HIST_MONTHS=nov.model.MONTHS.copy()
NOV=202611
STOP_ATR_WINDOW=14
STOP_ATR_MULT=1.5
STOP_MIN_FRACTION=.003
STOP_MAX_FRACTION=.02
STOP_WARMUP_FRACTION=.01
EPS=1e-8

def load_november(symbol):
    name=MONTH_FRAMES/(f"{symbol}_202611_through_20261112_1955UTC_5TF.zip")
    frames={}
    with zipfile.ZipFile(name) as z:
        for tf in nov.model.TFS:
            with z.open(f"{symbol}_{tf}_202611_UTC.csv") as file:
                data=pd.read_csv(file,parse_dates=['timestamp_utc'],index_col='timestamp_utc')
            data.index=pd.DatetimeIndex(data.index).tz_convert("UTC")
            frames[tf]=data
    return frames

def atr_fraction(df):
    # Lagged by one completed timeframe candle, no current-bar or future prices.
    hi=(df.bid_high+df.ask_high)*.5
    lo=(df.bid_low+df.ask_low)*.5
    cl=(df.bid_close+df.ask_close)*.5
    pc=cl.shift(1)
    tr=pd.concat([hi-lo,(hi-pc).abs(),(lo-pc).abs()],axis=1).max(axis=1)
    atr=tr.rolling(STOP_ATR_WINDOW,min_periods=STOP_ATR_WINDOW).mean().shift(1)
    mid=(df.bid_open+df.ask_open)*.5
    values=(STOP_ATR_MULT*atr/mid).to_numpy('float64')
    fallback=~np.isfinite(values)|(values<=0)
    values=np.where(fallback,STOP_WARMUP_FRACTION,values)
    values=np.clip(values,STOP_MIN_FRACTION,STOP_MAX_FRACTION)
    return values,fallback

def build_source():
    # Same original signals, entry conditions, and temporal exit as the
    # no-stop baseline. 2026-11 values reconstructed from saved Exness ZIP.
    nov.model.MONTHS=list(MONTHS)
    nov.model.MONTH_ID={m:i for i,m in enumerate(MONTHS)}
    frames={}
    m5={}
    for symbol in nov.SYMBOLS:
        future=load_november(symbol)
        for tf in nov.model.TFS:
            historic=nov.model.load(HIST,symbol,tf)
            concat=pd.concat([historic,future[tf]]).sort_index()
            if concat.index.has_duplicates:
                raise AssertionError(f"Duplicate candles for {symbol}/{tf}")
            frames[symbol,tf]=concat
        m5[symbol]=frames[symbol,"M5"]
        print('BARS',symbol,len(m5[symbol]),m5[symbol].index.min(),
              m5[symbol].index.max(),flush=True)
    store={}
    for symbol in nov.SYMBOLS:
        day,week=nov.model.daily_weekly_directions(m5[symbol])
        for tf in nov.model.TFS:
            df=frames[symbol,tf]
            prepared=nov.model.prepare(df,tf,day,week)
            lib=dict(nov.model.signal_library(df,prepared[3],prepared[4]))
            at,fallback=atr_fraction(df)
            store[symbol,tf]=dict(
                dataframe=df,
                prepared=prepared,
                signals=lib,
                atr_fraction=at,
                fallback=fallback)
    return store,m5

def select_indices(c,info):
    ordinal,month,minutes,daysig,weeksig,holds=info['prepared']
    family=c['family']
    signal=info['signals'][family]
    ori=c['orientation']
    if ori=='FOLLOW':side=signal
    elif ori=='FADE':side=-signal
    elif ori=='LONG_ONLY':side=np.where(signal>0,1,0)
    elif ori=='SHORT_ONLY':side=np.where(signal<0,-1,0)
    else:raise ValueError(ori)
    elig=(side!=0)
    if c['regime']=='D1_ALIGN':elig &= side==daysig
    elif c['regime']=='W1_ALIGN':elig &= side==weeksig
    elif c['regime']!='ANY':raise ValueError(c['regime'])
    opening=c['hour']*60
    window=(minutes>=opening)&(minutes<min(opening+c['window']*60,1440))
    holdbars=c['hold']//nov.model.TFS[c['tf']][0]
    valid,longret,shortret=holds[holdbars]
    good=np.flatnonzero(elig&window&valid)
    if len(good):
        good=good[np.r_[True,ordinal[good[1:]]!=ordinal[good[:-1]]]]
    original=np.where(side[good]>0,longret[good],shortret[good])
    return good,side,original

def replay_with_sl(c,info,m5):
    df=info['dataframe']
    ix,side,original=select_indices(c,info)
    stamp=df.index.asi8
    tf_min=nov.model.TFS[c['tf']][0]
    holdbars=c['hold']//tf_min
    ends=ix+holdbars-1
    exit_edges=stamp[ends]+tf_min*60*1_000_000_000
    series_ts=m5.index.asi8
    open_bid=m5.bid_open.to_numpy('float64')
    low_bid=m5.bid_low.to_numpy('float64')
    open_ask=m5.ask_open.to_numpy('float64')
    high_ask=m5.ask_high.to_numpy('float64')
    ask_entry=df.ask_open.to_numpy('float64')
    bid_entry=df.bid_open.to_numpy('float64')
    mid=(ask_entry+bid_entry)*.5
    start_idx=np.searchsorted(series_ts,stamp[ix],side='left')
    end_idx=np.searchsorted(series_ts,exit_edges,side='left')
    oldclose=original.copy()
    updated=original.copy()
    stopped=np.zeros(len(ix),dtype=bool)
    fback=np.zeros(len(ix),dtype=bool)
    stop_gaps=np.zeros(len(ix),dtype=bool)
    stop_frac=info['atr_fraction'][ix]
    for j,barindex in enumerate(ix):
        # Always attach SL immediately, including the 14-candle ATR warmup:
        # a 1% hard stop applies when prior ATR is unavailable.
        fback[j]=bool(info['fallback'][barindex])
        side_j=int(side[barindex])
        delta=float(stop_frac[j])*float(mid[barindex])
        if side_j>0:
            sl=float(ask_entry[barindex]-delta)
            for i in range(int(start_idx[j]),int(end_idx[j])):
                if float(low_bid[i])<=sl:
                    # A market gap through the stop fills at the worse
                    # available open, not the requested stop price.
                    fill=min(sl,float(open_bid[i]))
                    stop_gaps[j]=float(open_bid[i])<sl
                    updated[j]=(fill-ask_entry[barindex])/mid[barindex]*10000-nov.model.SLIPPAGE_ROUND_TRIP_BPS
                    stopped[j]=True
                    break
        elif side_j<0:
            sl=float(bid_entry[barindex]+delta)
            for i in range(int(start_idx[j]),int(end_idx[j])):
                if float(high_ask[i])>=sl:
                    fill=max(sl,float(open_ask[i]))
                    stop_gaps[j]=float(open_ask[i])>sl
                    updated[j]=(bid_entry[barindex]-fill)/mid[barindex]*10000-nov.model.SLIPPAGE_ROUND_TRIP_BPS
                    stopped[j]=True
                    break
    month=info['prepared'][1][ix]
    daily=info['prepared'][0][ix]
    return dict(original=oldclose,ret=updated,
        month=month,days=daily,
        stopped=stopped,gap=stop_gaps,atr_warmup=fback,
        stop_fraction=stop_frac,
        count=int(len(ix)))

def stats(returns):
    returns=np.asarray(returns,dtype='float64')
    win=int((returns>EPS).sum())
    loss=int((returns<-EPS).sum())
    flat=int(len(returns)-win-loss)
    return dict(trades=len(returns),wins=win,losses=loss,flats=flat,
                win_rate=round(100*win/len(returns),3) if len(returns) else 0)

def summarize_all():
    OUT.mkdir(parents=True,exist_ok=True)
    with INPUT.open(encoding='utf-8-sig',newline='') as stream:
        originals=list(csv.DictReader(stream))
    if len(originals)!=276:raise AssertionError(f"Expected 276, got {len(originals)}")
    allspec={}
    for rec in originals:
        parts=[nov.parse_component(s) for s in rec['components'].split(' | ')]
        if len(parts)!=int(rec['n_strategies']):
            raise AssertionError(f"Unexpected bot count: {rec['id']}")
        allspec[rec['id']]=parts
    sources,m5=build_source()
    cache={}
    for x in originals:
        for c in allspec[x['id']]:
            key=nov.component_key(c)
            if key not in cache:
                cache[key]=replay_with_sl(c,sources[c['symbol'],c['tf']],m5[c['symbol']])
    print('UNIQUE_EA_REPLAYED',len(cache),flush=True)

    rows=[]
    audit=[]
    trade_records=[]
    for rec in originals:
        components=[cache[nov.component_key(c)] for c in allspec[rec['id']]]
        m_pnl=np.zeros(len(MONTHS),dtype='float64')
        m_without=np.zeros(len(MONTHS),dtype='float64')
        m_counts=np.zeros(len(MONTHS),dtype='int64')
        for i,(c,values) in enumerate(zip(allspec[rec['id']],components)):
            part=np.bincount(values['month'],weights=values['ret'],minlength=len(MONTHS))
            oldpart=np.bincount(values['month'],weights=values['original'],minlength=len(MONTHS))
            counts=np.bincount(values['month'],minlength=len(MONTHS))
            m_pnl+=part/len(components)
            m_without+=oldpart/len(components)
            m_counts+=counts
            if len(components)>=1:
                for j in np.flatnonzero(values['month']==len(MONTHS)-1):
                    trade_records.append(dict(id=rec['id'],
                        symbol=c['symbol'],tf=c['tf'],
                        family=c['family'],orientation=c['orientation'],
                        date_utc=int(values['days'][j]),closed_trades=1,
                        sl_fraction=round(float(values['stop_fraction'][j]),6),
                        sl_hit=int(values['stopped'][j]),
                        gap_through_sl=int(values['gap'][j]),
                        net_bps_after_sl=round(float(values['ret'][j]),5),
                        net_bps_without_sl=round(float(values['original'][j]),5)))
        # Prove correct data and precise match to the old non-SL model.
        oct_index=nov.model.MONTH_ID[202610]
        nov_index=nov.model.MONTH_ID[202611]
        deltas=dict(
            pnl_2025=abs(float(m_without[:12].sum())-float(rec['profit_2025_bps'])),
            pnl_2026=abs(float(m_without[12:22].sum())-float(rec['profit_2026_bps'])),
            oct=abs(float(m_without[oct_index])-float(rec['pnl_202610_bps'])),
            nov=abs(float(m_without[nov_index])-float(rec['nov_2026_bps'])),
        )
        if max(deltas.values())>.02:
            raise AssertionError(f"No-SL replay differs for {rec['id']}: {deltas}")
        novret=np.concatenate([p['ret'][p['month']==nov_index] for p in components])
        novoriginal=np.concatenate([p['original'][p['month']==nov_index] for p in components])
        if len(novoriginal)!=int(rec['nov_trades_all_components']):
            raise AssertionError("Prior trade-count mismatch: "+rec['id'])
        ss=stats(novret)
        if len(novret)!=int(m_counts[nov_index]):
            raise AssertionError("Mismatched November counts")
        nov_stops=int(sum(int(p['stopped'][p['month']==nov_index].sum()) for p in components))
        nov_gaps=int(sum(int(p['gap'][p['month']==nov_index].sum()) for p in components))
        stops_historical=int(sum(int(p['stopped'][p['month']<nov_index].sum()) for p in components))
        annual2025=float(m_pnl[:12].sum())
        annual2026=float(m_pnl[12:22].sum())
        profitable_hist=int((m_pnl[:22]>EPS).sum())
        oct=float(m_pnl[oct_index])
        nov_pnl=float(m_pnl[nov_index])
        retained=(annual2025>EPS and annual2026>EPS and profitable_hist>=17 and
            oct>EPS and nov_pnl>EPS and ss['trades']>1 and ss['wins']>ss['losses'])
        reasons=[]
        if annual2025<=EPS: reasons.append('2025_nonprofitable')
        if annual2026<=EPS: reasons.append('2026_JanOct_nonprofitable')
        if profitable_hist<17: reasons.append('under_17_of_22_profitable_months')
        if oct<=EPS: reasons.append('Oct2026_nonprofitable')
        if nov_pnl<=EPS: reasons.append('Nov2026_to_date_nonprofitable')
        if ss['trades']<=1: reasons.append('Nov2026_under_2_trades')
        if ss['wins']<=ss['losses']: reasons.append('Nov2026_win_count_not_above_loss_count')
        o=dict(rec)
        o.update(
            sl_rule='ATR14_1p5_min0p3pct_max2pct_prev_completed_bar',
            sl_2025_bps=round(annual2025,6),
            sl_2026_JanOct_bps=round(annual2026,6),
            sl_oct2026_bps=round(oct,6),
            sl_nov2026_to_date_bps=round(nov_pnl,6),
            sl_profitable_months_22=profitable_hist,
            sl_nov_trades=ss['trades'],
            sl_nov_wins=ss['wins'],sl_nov_losses=ss['losses'],
            sl_nov_flats=ss['flats'],
            sl_nov_win_rate_pct=ss['win_rate'],
            sl_nov_hit_count=nov_stops,
            sl_nov_gapped_stop_count=nov_gaps,
            sl_historical_hit_count=stops_historical,
            sl_passes_all_filters=retained,
            sl_failure_reasons=';'.join(reasons),
            **{f'sl_pnl_{x}_bps':round(float(m_pnl[i]),6) for i,x in enumerate(MONTHS)}
        )
        rows.append(o)
        audit.append(dict(id=rec['id'],**{k:round(v,6) for k,v in deltas.items()}))
        if len(rows)%50==0:print('PROCESSED',len(rows),flush=True)
    kept=[r for r in rows if r['sl_passes_all_filters']]
    removed=[r for r in rows if not r['sl_passes_all_filters']]
    kept.sort(key=lambda r:(-int(r['sl_profitable_months_22']),
        -float(r['sl_nov2026_to_date_bps']),
        -int(r['sl_nov_trades']),r['id']))
    removed.sort(key=lambda r:(-len(r['sl_failure_reasons'].split(';')),
        -float(r['sl_nov2026_to_date_bps']),r['id']))
    bynovprofit=sorted(kept,key=lambda r:(-float(r['sl_nov2026_to_date_bps']),
                                     -int(r['sl_nov_trades']),r['id']))
    bynovtrades=sorted(kept,key=lambda r:(-int(r['sl_nov_trades']),
                                     -float(r['sl_nov2026_to_date_bps']),r['id']))
    fields=list(rows[0])
    def write_csv(name,group,columns=fields):
        with (OUT/name).open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore')
            w.writeheader();w.writerows(group)
    write_csv('surviving_after_mandatory_SL.csv',kept)
    write_csv('removed_after_mandatory_SL.csv',removed)
    write_csv('all_276_SL_backtest_results.csv',rows)
    write_csv('survivors_by_Nov_profit.csv',bynovprofit)
    write_csv('survivors_by_Nov_trades.csv',bynovtrades)
    if trade_records:
        write_csv('nov2026_per_trade_audit.csv',trade_records,list(trade_records[0]))
    def top(r):
        return {k:r[k] for k in (
          'id','category','symbols','sl_profitable_months_22','sl_2025_bps',
          'sl_2026_JanOct_bps','sl_oct2026_bps','sl_nov2026_to_date_bps',
          'sl_nov_trades','sl_nov_wins','sl_nov_losses','sl_nov_win_rate_pct',
          'sl_nov_hit_count','sl_historical_hit_count','components')}
    fail_counts=Counter(reason for r in removed for reason in r['sl_failure_reasons'].split(';') if reason)
    report=dict(
        version='V22-MANDATORY-SL-CFD-REPLAY',
        as_of_utc='2026-11-12T19:55:00Z',
        as_of_vietnam='2026-11-13 02:55 UTC+07',
        data_november_incomplete=True,
        original_qualified_276=len(originals),
        unique_ea_configurations=len(cache),
        passed_all=len(kept),
        eliminated=len(removed),
        sl_definition=dict(
            trigger='Long stop if M5 bid_low <= price; short stop if M5 ask_high >= price',
            stop_at_entry='entry Ask for long; entry Bid for short, minus/plus ATR-derived price distance',
            atr='14 candle SMA true range on entry timeframe shifted one complete bar',
            atr_multiplier=STOP_ATR_MULT,
            min_stop_pct=100*STOP_MIN_FRACTION,
            max_stop_pct=100*STOP_MAX_FRACTION,
            warmup_default_pct=100*STOP_WARMUP_FRACTION,
            entry_model='Ask open for long, Bid open for short, first eligible trade per day',
            stop_slippage='on 5min gap over stop fill at worse 5min open; otherwise quoted stop price',
            standard_cost='observed bid/ask plus 2 bps roundtrip assumed extra slippage',
            trade_duration='original time-based exit used unless SL triggered sooner',
            caution='M5 high/low interpolation, cannot guarantee real gap/stop fill in live execution; no fees/commissions'),
        preserved_filters=[
            '2025 total pnl >0','Jan-Oct2026 total pnl >0',
            'at least 17 of 22 profitable historical months',
            'October 2026 pnl >0','November 2026-to-date pnl >0',
            'November >1 closed trades across EA components',
            'November strictly more net-positive trades than net-negative trades'],
        counts_by_type={t:dict(before=sum(r['category']==t for r in rows),
                               passed=sum(r['category']==t for r in kept),
                               removed=sum(r['category']==t for r in removed))
                        for t in ('single','pair','triple','quad','quint')},
        counts_by_sl_positive_months={str(m):sum(r['sl_profitable_months_22']==m for r in kept)
                                       for m in range(17,23)},
        failure_reasons=dict(fail_counts),
        november_trades_in_survivors=sum(int(r['sl_nov_trades']) for r in kept),
        november_stops_in_survivors=sum(int(r['sl_nov_hit_count']) for r in kept),
        all_nov_stop_hits_across_276=sum(int(r['sl_nov_hit_count']) for r in rows),
        max_baseline_reproduction_error_bps={k:round(max(x[k] for x in audit),6)
                                              for k in ('pnl_2025','pnl_2026','oct','nov')},
        top_survivors_by_nov_profit=[top(r) for r in bynovprofit[:30]],
        top_survivors_by_nov_trades=[top(r) for r in bynovtrades[:30]],
        top_survivors_by_historical_months=[top(r) for r in kept[:30]],
        created_at_utc=datetime.now(timezone.utc).isoformat())
    (OUT/'sl_retest_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('SL_BACKTEST_FINAL',json.dumps({k:report[k] for k in (
        'original_qualified_276','unique_ea_configurations','passed_all',
        'eliminated','counts_by_type','counts_by_sl_positive_months',
        'failure_reasons','all_nov_stop_hits_across_276',
        'max_baseline_reproduction_error_bps')},ensure_ascii=False),flush=True)

if __name__=="__main__":
    summarize_all()
