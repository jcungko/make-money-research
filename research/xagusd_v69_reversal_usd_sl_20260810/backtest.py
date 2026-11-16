"""Corrected XAGUSD M15 V6.9-REVERSAL — SL fixed $5 or $10, TP half previous candle volatility.
Research ONLY. Never close by candle/time; TP or SL until a quote crosses, else mark open at dataset end.
Tick signal MID, execution Bid/Ask, XAGUSD 5000 oz/lot, 0.01 lot.
"""
import requests, io,zipfile,hashlib,json
import pandas as pd,numpy as np
from pathlib import Path
from numba import njit

OUT=Path('v69_reversal_usd_sl_outputs');OUT.mkdir(exist_ok=True)
CONTRACT_SIZE=5000.0
LOT=0.01
OZ=50.0
PREV_MIN_VOL_PCT=.35
INIT_PCT=.05
REV_PCT=.05
TP_PREV_MULT=.50
SL_VALUES=(5.,10.)
MONTHS=('2026-08','2026-09','2026-10')
session=requests.Session()
old=pd.read_csv('v18data/XAGUSD/2026/XAGUSD_M15_2026_UTC.csv.gz',compression='gzip',parse_dates=['timestamp_utc']).set_index('timestamp_utc')
metadata=[];arr=[]
for month in MONTHS:
 mm=month[-2:]
 url=f'https://ticks.ex2archive.com/ticks/XAGUSD/2026/{mm}/Exness_XAGUSD_2026_{mm}.zip'
 resp=session.get(url,timeout=120);resp.raise_for_status()
 sha=hashlib.sha256(resp.content).hexdigest()
 with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
  tick=pd.read_csv(z.open(z.namelist()[0]),usecols=['Timestamp','Bid','Ask'])
 ts=pd.to_datetime(tick.Timestamp,utc=True).astype('int64').to_numpy()
 bid=tick.Bid.to_numpy(dtype=np.float64)
 ask=tick.Ask.to_numpy(dtype=np.float64)
 assert len(ts)>0 and np.all(np.diff(ts)>=0) and (ask>=bid).all()
 bars=ts//900_000_000_000
 st=np.r_[0,np.flatnonzero(bars[1:]!=bars[:-1])+1]
 en=np.r_[st[1:],len(ts)]
 dt=pd.to_datetime(bars[st]*900,unit='s',utc=True)
 cmp=old.reindex(dt)
 assert cmp['bid_close'].notna().all()
 check={'bid_open':bid[st],'bid_high':np.maximum.reduceat(bid,st),
   'bid_low':np.minimum.reduceat(bid,st),'bid_close':bid[en-1],
   'ask_open':ask[st],'ask_high':np.maximum.reduceat(ask,st),
   'ask_low':np.minimum.reduceat(ask,st),'ask_close':ask[en-1],
   'tick_count':en-st}
 errors={k:int(np.count_nonzero(~np.isclose(v,cmp[k].to_numpy(),rtol=0,atol=1e-9))) for k,v in check.items()}
 assert not any(errors.values()),(month,errors)
 metadata.append({'month':month,'url':url,'sha256':sha,'tick_count':int(len(ts)),'candle_count':int(len(st)),
   'first_tick':str(pd.to_datetime(ts[0],utc=True)),'last_tick':str(pd.to_datetime(ts[-1],utc=True)),
   'duplicates_exact_adjacent':int(np.sum((ts[1:]==ts[:-1])&(bid[1:]==bid[:-1])&(ask[1:]==ask[:-1]))),
   'nonmonotonic_tick_count':int(np.sum(ts[1:]<ts[:-1])),'negative_spread_tick_count':int(np.sum(bid>ask)),
   'M15_BidAsk_OHLC_mismatch':errors,'mean_entry_spread_usd_001':float(np.mean((ask[st]-bid[st])*OZ)),
   'bars_gap_gt15m':int(np.sum(np.diff(bars[st])>1))})
 print('DATA',json.dumps(metadata[-1]),flush=True)
 arr.append((ts,bid,ask))
 del tick,resp
t=np.concatenate([x[0] for x in arr])
b=np.concatenate([x[1] for x in arr])
a=np.concatenate([x[2] for x in arr])
assert np.all(np.diff(t)>=0)
key=t//900_000_000_000
starts=np.r_[0,np.flatnonzero(key[1:]!=key[:-1])+1].astype('int64')
ends=np.r_[starts[1:],len(t)].astype('int64')
ids=key[starts]
mid=(a+b)/2.
bar_open=mid[starts]
bar_hi=np.maximum.reduceat(mid,starts)
bar_lo=np.minimum.reduceat(mid,starts)
bar_vol=(bar_hi-bar_lo)/bar_open*100.
prev=np.r_[np.nan,bar_vol[:-1]]
contiguous=np.r_[False,np.diff(ids)==1]
eligible=contiguous & (prev>=PREV_MIN_VOL_PCT-1e-12)
dates=pd.to_datetime(ids*900,unit='s',utc=True)
months=dates.strftime('%Y-%m').to_numpy()
date_utc=dates.strftime('%Y-%m-%d').to_numpy()

@njit
def signal_engine(mid,starts,ends,initial,reversal):
 n=len(starts)
 longidx=np.full(n,-1,dtype=np.int64)
 shortidx=np.full(n,-1,dtype=np.int64)
 for i in range(n):
  start=starts[i];end=ends[i]
  op=mid[start]
  low=op;high=op
  armed_l=False;armed_s=False
  for k in range(start+1,end):
   px=mid[k]
   if longidx[i]<0:
    if not armed_l:
     if px<=op*(1-initial):
      armed_l=True;low=px
    else:
     if px<low:low=px
     elif px>=low*(1+reversal):
      longidx[i]=k
   if shortidx[i]<0:
    if not armed_s:
     if px>=op*(1+initial):
      armed_s=True;high=px
    else:
     if px>high:high=px
     elif px<=high*(1-reversal):
      shortidx[i]=k
   if longidx[i]>=0 and shortidx[i]>=0:break
 return longidx,shortidx

@njit
def trade_replay(t,bid,ask,starts,ends,ids,eligible,prev,longidx,shortidx,stopUSD,oz):
 n=len(starts)
 entries=np.empty(n,dtype=np.int64)
 exits=np.full(n,-1,dtype=np.int64)
 candle_idx=np.empty(n,dtype=np.int64)
 sides=np.empty(n,dtype=np.int8)
 entry_quotes=np.empty(n,dtype=np.float64)
 exit_quotes=np.empty(n,dtype=np.float64)
 slprices=np.empty(n,dtype=np.float64)
 tpprices=np.empty(n,dtype=np.float64)
 pnl=np.empty(n,dtype=np.float64)
 causes=np.empty(n,dtype=np.int8) # 1 TP, 2 SL, 3 CENSORED
 scheduled_signal=0
 skipped_while_open=0
 same_tick_ties=0
 opened=0
 blocked_until=-1
 for i in range(n):
  if not eligible[i]:continue
  jl=longidx[i];js=shortidx[i]
  if jl<0 and js<0:continue
  scheduled_signal+=1
  if jl>=0 and js>=0 and jl==js:same_tick_ties+=1
  if jl>=0 and (js<0 or jl<=js):
   idx=jl;sgn=1
  else:
   idx=js;sgn=-1
  if idx<=blocked_until:
   skipped_while_open+=1
   continue
  entry=ask[idx] if sgn==1 else bid[idx]
  # TP = previous bar range percent * 50%, applied as price fraction from true fill
  tp_frac=prev[i]*.5/100.
  target_delta=entry*tp_frac
  stop_delta=stopUSD/oz
  stop_px=entry-sgn*stop_delta
  target_px=entry+sgn*target_delta
  close_idx=-1;close_px=np.nan;cash=np.nan;reason=3
  for k in range(idx,len(t)):
   q=bid[k] if sgn==1 else ask[k]
   movement=sgn*(q-entry)
   # No TP or SL ambiguity at a single quote.
   if movement>=target_delta-1e-10:
    close_idx=k;close_px=target_px;cash=target_delta*oz;reason=1
    break
   if movement<=-stop_delta+1e-10:
    close_idx=k;close_px=q;cash=movement*oz;reason=2
    break
  candle_idx[opened]=i
  entries[opened]=idx
  exits[opened]=close_idx
  entry_quotes[opened]=entry
  exit_quotes[opened]=close_px
  slprices[opened]=stop_px
  tpprices[opened]=target_px
  sides[opened]=sgn
  pnl[opened]=cash
  causes[opened]=reason
  blocked_until=close_idx if close_idx>=0 else len(t)+1
  opened+=1
 return (candle_idx[:opened],entries[:opened],exits[:opened],sides[:opened],
   entry_quotes[:opened],exit_quotes[:opened],slprices[:opened],tpprices[:opened],
   pnl[:opened],causes[:opened],scheduled_signal,skipped_while_open,same_tick_ties)

L,S=signal_engine(mid,starts,ends,INIT_PCT/100.,REV_PCT/100.)
signal_opps=[]
for mon in MONTHS:
 sel=(months==mon)&eligible
 signal_opps.append({'month':mon,'qualifying_prev_bars':int(sel.sum()),
  'bars_long_signal':int(np.sum(sel & (L>=0))),
  'bars_short_signal':int(np.sum(sel & (S>=0))),
  'bars_both_signals':int(np.sum(sel & (L>=0)&(S>=0))),
  'bars_one_or_both':int(np.sum(sel & ((L>=0)|(S>=0)))),
  'both_same_timestamp_tick_count':int(np.sum(sel&(L>=0)&(L==S)))})
print('OPPORTUNITIES',json.dumps(signal_opps),flush=True)

summaries=[];total_summaries=[];all_trades=[]
for sl in SL_VALUES:
 replay=trade_replay(t,b,a,starts,ends,ids,eligible,prev,L,S,sl,OZ)
 (bar_index,entries,exits,side,entrprice,exprice,slprice,tpprice,pnl,causes,n_candidate,n_blocked,n_tied)=replay
 # This signal is always permitted only in bar; closure can span many bars/months; no timed exit.
 exit_time=np.full(len(entries),np.datetime64('NaT'),dtype='datetime64[ns]')
 has_exit=exits>=0
 exit_time[has_exit]=t[exits[has_exit]].astype('datetime64[ns]')
 closed=has_exit
 spread_entry=(a[entries]-b[entries])*OZ
 spread_exit=np.zeros(len(entries),dtype=np.float64)
 spread_exit[has_exit]=(a[exits[has_exit]]-b[exits[has_exit]])*OZ
 spread_proxy=(spread_entry+spread_exit)/2
 entries_month=months[bar_index]
 # Exits on October data; available trades may be open/censored at final October tick.
 ledger=pd.DataFrame({
  'sl_target_usd':sl,'lot':LOT,'signal_month':entries_month,
  'signal_day_utc':date_utc[bar_index],
  'candle_start_utc':dates[bar_index],
  'prior_candle_volatility_pct':prev[bar_index],
  'entry_timestamp_utc':pd.to_datetime(t[entries],unit='ns',utc=True),
  'exit_timestamp_utc':pd.to_datetime(exit_time,utc=True),
  'signal':np.where(side==1,'LONG','SHORT'),
  'entry_price':entrprice,
  'sl_price':slprice,'tp_price':tpprice,
  'tp_target_usd':(np.abs(tpprice-entrprice)*OZ),
  'exit_price':exprice,
  'reason':np.where(causes==1,'TP',np.where(causes==2,'SL','OPEN_AT_END_OF_DATA')),
  'realized_usd_spread_included':pnl,
  'entry_spread_usd':spread_entry,
  'spread_cost_proxy_usd':spread_proxy,
  'commission_base_usd':np.zeros(len(pnl))})
 ledger['close_month']=ledger.exit_timestamp_utc.dt.strftime('%Y-%m')
 ledger['holding_minutes']=(ledger.exit_timestamp_utc-ledger.entry_timestamp_utc).dt.total_seconds()/60
 ledger.to_csv(OUT/f'trades_sl{int(sl)}.csv',index=False)
 all_trades.append(ledger)
 # FIFO rows are already chronological; calculate equity drawdown from realized exits as cash position closes
 for mon in MONTHS:
  subset=ledger[ledger.signal_month==mon]
  done=subset[subset.reason!='OPEN_AT_END_OF_DATA']
  p=done.realized_usd_spread_included.to_numpy()
  win=p>1e-8;loss=p<-1e-8;eq=np.r_[0,np.cumsum(p)]
  byday=done.groupby('signal_day_utc').realized_usd_spread_included.sum()
  summaries.append({'sl_usd':sl,'month':mon,'eligible_prev_bars':next(x['qualifying_prev_bars'] for x in signal_opps if x['month']==mon),
   'long_signals':next(x['bars_long_signal'] for x in signal_opps if x['month']==mon),
   'short_signals':next(x['bars_short_signal'] for x in signal_opps if x['month']==mon),
   'both_signals':next(x['bars_both_signals'] for x in signal_opps if x['month']==mon),
   'opened':len(subset),'longs':int((subset.signal=='LONG').sum()),'shorts':int((subset.signal=='SHORT').sum()),
   'closed':len(p),'unclosed_censored':int((subset.reason=='OPEN_AT_END_OF_DATA').sum()),
   'wins':int(win.sum()),'losses':int(loss.sum()),'flats':int(len(p)-win.sum()-loss.sum()),
   'win_pct':float(win.mean()*100) if len(p) else None,
   'pnl_usd':float(p.sum()),'avg_trade_usd':float(np.mean(p)) if len(p) else None,
   'gross_win':float(p[win].sum()),'gross_loss_abs':float(-p[loss].sum()),
   'pf':float(p[win].sum()/-p[loss].sum()) if loss.any() else None,
   'max_dd_usd':float(np.max(np.maximum.accumulate(eq)-eq)) if len(p) else 0,
   'tp':int((done.reason=='TP').sum()),'sl':int((done.reason=='SL').sum()),
   'green_days':int((byday>1e-8).sum()),'red_days':int((byday<-1e-8).sum()),
   'spread_proxy_usd':float(done.spread_cost_proxy_usd.sum()),
   'raw_commission_scenario_usd':float(p.sum()-0.07*len(p)),
   'extra_0p5_per_trade_usd':float(p.sum()-0.5*len(p)),
   'extra_1_per_trade_usd':float(p.sum()-1.0*len(p)),
   'max_holding_minutes':float(done.holding_minutes.max()) if len(p) else 0})
 done=ledger[ledger.reason!='OPEN_AT_END_OF_DATA']
 p=done.realized_usd_spread_included.to_numpy()
 win=p>1e-8;loss=p<-1e-8;eq=np.r_[0,np.cumsum(p)]
 byday=done.groupby('signal_day_utc').realized_usd_spread_included.sum()
 rec={'sl_usd':sl,'entries':len(ledger),'closed':len(done),
  'censored':int(len(ledger)-len(done)),
  'longs':int((ledger.signal=='LONG').sum()),'shorts':int((ledger.signal=='SHORT').sum()),
  'wins':int(win.sum()),'losses':int(loss.sum()),'flats':int(len(p)-win.sum()-loss.sum()),
  'win_pct':float(win.mean()*100) if len(p) else None,
  'pnl_usd':float(p.sum()),'pf':float(p[win].sum()/-p[loss].sum()) if loss.any() else None,
  'avg_usd':float(p.mean()) if len(p) else None,
  'average_win_usd':float(p[win].mean()) if win.any() else None,
  'average_loss_usd':float(p[loss].mean()) if loss.any() else None,
  'realized_reward_risk':float(p[win].mean()/-p[loss].mean()) if win.any() and loss.any() else None,
  'max_drawdown_usd':float(np.max(np.maximum.accumulate(eq)-eq)),
  'tp':int((done.reason=='TP').sum()),'sl':int((done.reason=='SL').sum()),
  'green_days':int((byday>1e-8).sum()),'red_days':int((byday<-1e-8).sum()),
  'max_holding_minutes':float(done.holding_minutes.max()) if len(done) else 0,
  'mean_holding_minutes':float(done.holding_minutes.mean()) if len(done) else 0,
  'spread_cost_proxy_usd':float(done.spread_cost_proxy_usd.sum()),
  'entry_spread_mean_usd':float(done.entry_spread_usd.mean()) if len(done) else 0,
  'raw_commission_scenario_usd':float(p.sum()-len(p)*.07),
  'extra_0p5_scenario_usd':float(p.sum()-len(p)*.5),
  'extra_1_scenario_usd':float(p.sum()-len(p)),
  'signal_bars_total':n_candidate,'skipped_signals_while_holding':n_blocked,
  'both_tied_same_tick':n_tied,
  'sl_breaches_usd_beyond_target':int(np.sum(done[done.reason=='SL'].realized_usd_spread_included.to_numpy()<-sl-1e-7))}
 total_summaries.append(rec)
 print('BACKTEST',json.dumps(rec,ensure_ascii=False),flush=True)
pd.DataFrame(summaries).to_csv(OUT/'monthly_by_entry_month.csv',index=False)
pd.DataFrame(total_summaries).to_csv(OUT/'totals.csv',index=False)
# Month of realization (cash-based) to avoid confusing cohort accounting.
closed_all=pd.concat(all_trades,ignore_index=True)
closed_all=closed_all[closed_all.reason!='OPEN_AT_END_OF_DATA']
cash_month=closed_all.groupby(['sl_target_usd','close_month']).realized_usd_spread_included.agg(['sum','size']).reset_index()
cash_month.to_csv(OUT/'monthly_by_exit_month.csv',index=False)
report={'contract_oz_per_lot':CONTRACT_SIZE,'lot':LOT,'sl_usd_scenarios':SL_VALUES,
        'tp_rule':'50% of previous M15 MID (high-low)/open percent, applied to actual entry quote',
        'signal_rule':'prior MID M15 volatility >=0.35%; current MID initial excursion 0.05% and reversal from extreme 0.05%',
        'exit':'ONLY TP or SL. No end-of-candle close and NO 60-minute timeout. No future fills for open position when dataset ends.',
        'nontrading_session':'skip first active M15 candle immediately after gaps >15min because previous candle is not immediately preceding',
        'precision':'Milliseconds timestamps, file order preserved for same-timestamp distinct ticks',
        'spread':'Real Bid/Ask included in quote-based realized PnL; proxy additional spread impact is mean entry/exit half spread as diagnostic only, not deducted twice',
        'fees':'Commission zero and extra slippage zero in base; sensitivity -$0.07 per trade (hypothetical raw spread commission), -$0.50 and -$1 additional per trade',
        'sources':metadata,'signal_opportunities':signal_opps,'monthly_by_entry_month':summaries,
        'three_month_totals':total_summaries,
        'monthly_by_exit_month':cash_month.to_dict('records')}
(OUT/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str))
print('MONTHLY',json.dumps(summaries,ensure_ascii=False),flush=True)
print('CASH_MONTH',cash_month.to_json(orient='records'),flush=True)
print('FILES',[(p.name,p.stat().st_size) for p in OUT.iterdir()],flush=True)
