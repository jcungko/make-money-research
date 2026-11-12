#!/usr/bin/env python3
"""V22: rank 308 distinct strategies by November-to-date P&L AND trade frequency,
requiring the raw number of profitable trades to EXCEED losing trades.
Reproduce archived November candles and the original Exness Bid/Ask backtest
using the same source functions; validate every candidate's P&L and trade count.
"""
import csv, json, zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import v22_nov2026_filter as nov

SRC = Path('results/v22_nov2026_deduplicated/unique_strategies.csv')
OUT = Path('results/v22_nov2026_win_trade_ranking')
NOV_CANDLES = Path('results/v22_nov2026_filter/november_candles')
ROOT = Path('data/v22_exness')
EPS = 1e-8

def load_nov_frames(symbol):
    f=NOV_CANDLES/f'{symbol}_202611_through_20261112_1955UTC_5TF.zip'
    with zipfile.ZipFile(f) as z:
        frames={}
        for tf in nov.model.TFS:
            with z.open(f'{symbol}_{tf}_202611_UTC.csv') as raw:
                d=pd.read_csv(raw,parse_dates=['timestamp_utc'],index_col='timestamp_utc')
            d.index=pd.DatetimeIndex(d.index).tz_convert('UTC')
            frames[tf]=d
    return frames

def detailed_replay(component,store):
    sym,tf=component['symbol'],component['tf']
    ordinal,midx,minutes,day,week,holds,signals=store[sym,tf]
    raw=signals[component['family']]
    orient=component['orientation']
    if orient=='FOLLOW': side=raw
    elif orient=='FADE': side=-raw
    elif orient=='LONG_ONLY': side=np.where(raw>0,1,0)
    elif orient=='SHORT_ONLY': side=np.where(raw<0,-1,0)
    else: raise ValueError(orient)
    eligible=(side!=0)
    if component['regime']=='D1_ALIGN': eligible &= side==day
    elif component['regime']=='W1_ALIGN': eligible &= side==week
    begin=component['hour']*60
    window=(minutes>=begin)&(minutes<min(begin+component['window']*60,1440))
    holdbars=component['hold']//nov.model.TFS[tf][0]
    valid,longret,shortret=holds[holdbars]
    good=np.flatnonzero(eligible&window&valid)
    if len(good):
        first=np.r_[True,ordinal[good[1:]]!=ordinal[good[:-1]]]
        good=good[first]
    novmask=(midx[good]==nov.model.MONTH_ID[202611])
    ix=good[novmask]
    ret=np.where(side[ix]>0,longret[ix],shortret[ix])
    wins=int((ret>EPS).sum())
    losses=int((ret<-EPS).sum())
    flat=int((np.abs(ret)<=EPS).sum())
    assert wins+losses+flat==len(ret)
    return {
        'trades':int(len(ret)),'wins':wins,'losses':losses,'breakeven':flat,
        'net_bps':float(ret.sum()),
        'gross_wins_bps':float(ret[ret>EPS].sum()),
        'gross_losses_bps':float(-ret[ret<-EPS].sum()),
        'dates_utc':[str(x) for x in ordinal[ix]],
    }

def short(r):
    return {k:r[k] for k in (
        'id','category','symbols','months_profitable',
        'nov_2026_bps','nov_trades_all_components','nov_wins','nov_losses',
        'nov_breakeven','nov_win_rate_percent','nov_profit_factor',
        'nov_unique_trading_days','nov_last_trade_date_utc','components'
    )}

def rank_candidates(rows):
    return {
      'by_net_profit': sorted(rows,key=lambda r:(-float(r['nov_2026_bps']),
                        -int(r['nov_trades_all_components']),
                        -float(r['nov_win_rate_percent']),r['id'])),
      'by_trade_count': sorted(rows,key=lambda r:(-int(r['nov_trades_all_components']),
                        -float(r['nov_2026_bps']),-float(r['nov_win_rate_percent']),r['id'])),
      'by_win_count': sorted(rows,key=lambda r:(-int(r['nov_wins']),
                        -float(r['nov_2026_bps']),-int(r['nov_trades_all_components']),r['id'])),
    }

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with SRC.open(newline='',encoding='utf-8-sig') as f:
        original=list(csv.DictReader(f))
    assert len(original)==308,f'Baseline changed: {len(original)}'
    spec={r['id']:[nov.parse_component(x) for x in r['components'].split(' | ')] for r in original}
    nov.model.MONTHS.append(202611)
    nov.model.MONTH_ID={m:i for i,m in enumerate(nov.model.MONTHS)}
    newframes={s:load_nov_frames(s) for s in nov.SYMBOLS}
    needed={(s['symbol'],s['tf']) for arr in spec.values() for s in arr}
    store={}
    for symbol in nov.SYMBOLS:
        historic_m5=nov.model.load(ROOT,symbol,'M5')
        both_m5=pd.concat([historic_m5,newframes[symbol]['M5']]).sort_index()
        if both_m5.index.has_duplicates:raise AssertionError('M5 duplicate')
        ds,ws=nov.model.daily_weekly_directions(both_m5)
        for sym,tf in sorted(needed):
            if sym!=symbol: continue
            historical=nov.model.load(ROOT,symbol,tf)
            both=pd.concat([historical,newframes[symbol][tf]]).sort_index()
            if both.index.has_duplicates:raise AssertionError(f'dup {symbol} {tf}')
            prepared=nov.model.prepare(both,tf,ds,ws)
            signals=dict(nov.model.signal_library(both,prepared[3],prepared[4]))
            store[sym,tf]=(*prepared,signals)
        print('DATA_READY',symbol,flush=True)
    perbot={}
    for r in original:
        for c in spec[r['id']]:
            key=nov.component_key(c)
            if key not in perbot:perbot[key]=detailed_replay(c,store)
    print('DISTINCT_COMPONENTS',len(perbot),flush=True)
    rows=[]
    validation=[]
    for r in original:
        b=[perbot[nov.component_key(c)] for c in spec[r['id']]]
        count=sum(x['trades'] for x in b)
        wins=sum(x['wins'] for x in b)
        losses=sum(x['losses'] for x in b)
        flats=sum(x['breakeven'] for x in b)
        portfolio_bps=float(np.mean([x['net_bps'] for x in b]))
        if count!=int(r['nov_trades_all_components']) or abs(portfolio_bps-float(r['nov_2026_bps']))>0.001:
            raise AssertionError(f"November backtest mismatch: {r['id']} "
                f"trades:{count}/{r['nov_trades_all_components']} "
                f"bps:{portfolio_bps}/{r['nov_2026_bps']}")
        if count!=wins+losses+flats:raise AssertionError(r['id'])
        # For a portfolio of N bots, component net returns are equal-weight
        # means; the appropriate total gross win/loss scale is divided by N.
        gross_profit=sum(x['gross_wins_bps'] for x in b)/len(b)
        gross_loss=sum(x['gross_losses_bps'] for x in b)/len(b)
        pf=(gross_profit/gross_loss if gross_loss>EPS else float('inf'))
        o=dict(r)
        o.update(
            nov_wins=wins,nov_losses=losses,nov_breakeven=flats,
            nov_win_rate_percent=round(100*wins/count,3) if count else 0.,
            nov_win_loss_ratio=round(wins/losses,4) if losses else ('INF' if wins else '0'),
            nov_profit_factor=round(pf,4) if np.isfinite(pf) else 'INF',
            nov_gross_wins_bps=round(gross_profit,5),
            nov_gross_losses_bps=round(gross_loss,5),
            nov_avg_net_bps_per_component_trade=round(
                sum(x['net_bps'] for x in b)/count,5) if count else 0.,
            win_count_greater_than_loss_count=str(wins>losses),
        )
        rows.append(o)
    accepted=[r for r in rows if r['nov_wins']>r['nov_losses']]
    rejected=[r for r in rows if r['nov_wins']<=r['nov_losses']]
    ranks=rank_candidates(accepted)
    # Joint ranking: minimum of the two percentile ranks guards against a
    # high P&L strategy with very few trades or vice versa.
    pnl_rank={r['id']:i+1 for i,r in enumerate(ranks['by_net_profit'])}
    trade_rank={r['id']:i+1 for i,r in enumerate(ranks['by_trade_count'])}
    for r in accepted:
        r['nov_profit_rank']=pnl_rank[r['id']]
        r['nov_trade_count_rank']=trade_rank[r['id']]
        r['joint_rank_score']=round(
            (r['nov_profit_rank']+r['nov_trade_count_rank'])/2,2)
    ranks['by_joint_rank']=sorted(accepted,key=lambda r:(
        r['joint_rank_score'],max(r['nov_profit_rank'],r['nov_trade_count_rank']),
        -int(r['nov_wins']),r['id']))
    # Exact two-objective Pareto frontier: no other strategy has at least as
    # many trades AND as much profit with one strict advantage.
    best_so_far=float('-inf')
    frontier=[]
    for r in ranks['by_trade_count']:
        value=float(r['nov_2026_bps'])
        if value>best_so_far+EPS:
            frontier.append(r)
            best_so_far=value
    # collapse ties at identical trade counts: first retains higher profit.
    unique_frontier=[]
    seen_trades=set()
    for r in frontier:
        nt=int(r['nov_trades_all_components'])
        if nt in seen_trades:continue
        seen_trades.add(nt)
        unique_frontier.append(r)
    fields=list(rows[0])
    def output_csv(name,arr):
        with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
            writer.writeheader();writer.writerows(arr)
    output_csv('qualified_win_gt_loss_by_profit.csv',ranks['by_net_profit'])
    output_csv('qualified_win_gt_loss_by_trades.csv',ranks['by_trade_count'])
    output_csv('qualified_win_gt_loss_joint_ranking.csv',ranks['by_joint_rank'])
    output_csv('rejected_win_lte_loss.csv',rejected)
    output_csv('all_308_with_trade_statistics.csv',rows)
    report={
        'version':'V22-NOV2026-WINS-LOSSES',
        'analysis_as_of':'2026-11-12T19:55:00Z',
        'as_of_vietnam':'2026-11-13 02:55 GMT+7',
        'period_incomplete':True,
        'historical_month_period':'2025-01 through 2026-10',
        'data_source':'results/v22_nov2026_filter/november_candles + original V22 2025-2026 Exness Bid/Ask data',
        'checks':'All 308 strategies reproduced Nov P&L within 0.001bps and their total November trade count exactly',
        'count_definition':'Each closed EA trade is counted separately. Same-day trades from different EAs are counted separately.',
        'win_definition':'Trade net basis point P&L > 0 after observed Bid/Ask spread and 2bps round-trip additional assumed slippage',
        'portfolio_return_definition':'Arithmetic average of EA monthly P&L in bps at equal notionals, NOT real account ROI or USD',
        'requested_rule':'win_count > loss_count; breakeven trades do not count as wins or losses',
        'input_distinct_strategy_configs':len(rows),
        'unique_individual_ea_components':len(perbot),
        'eligible':len(accepted),
        'ineligible':len(rejected),
        'eligible_by_type':dict(Counter(x['category'] for x in accepted)),
        'eligible_by_historical_months':{str(m):sum(int(x['months_profitable'])==m for x in accepted) for m in (17,18,19,20)},
        'ineligible_by_type':dict(Counter(x['category'] for x in rejected)),
        'top15_by_profit':[short(r) for r in ranks['by_net_profit'][:15]],
        'top15_by_trade_count':[short(r) for r in ranks['by_trade_count'][:15]],
        'top15_by_joint_rank':[dict(short(r),profit_rank=r['nov_profit_rank'],
                                    trade_count_rank=r['nov_trade_count_rank']) for r in ranks['by_joint_rank'][:15]],
        'pareto_frontier_profit_trades':[short(r) for r in unique_frontier],
        'some_rejected':[short(r) for r in rejected[:25]],
        'created_at_utc':datetime.now(timezone.utc).isoformat()
    }
    (OUT/'ranking_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('RANKING_FINAL',json.dumps({k:report[k] for k in (
        'input_distinct_strategy_configs','unique_individual_ea_components',
        'eligible','ineligible','eligible_by_type',
        'eligible_by_historical_months')},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
