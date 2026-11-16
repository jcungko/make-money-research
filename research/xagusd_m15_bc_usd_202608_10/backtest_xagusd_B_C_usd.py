# XAGUSD B/C public Exness tick research. Fixed USD brackets, Aug-Oct 2026.
# Research-only. True quote timestamps, no future information for direction.
import requests, zipfile, io, hashlib, json, gzip
import numpy as np, pandas as pd
from pathlib import Path
BASE=Path('xag_bc_usd_outputs'); BASE.mkdir(exist_ok=True)
SYMBOL='XAGUSD'
CONTRACT=5000.0
LOTS=[0.01,0.02,0.05,0.10]
MONTHS=['2026-08','2026-09','2026-10']
TP_USD=10.; SL_USD=5.
S=requests.Session()
stored=pd.read_csv('v18data/XAGUSD/2026/XAGUSD_M15_2026_UTC.csv.gz',compression='gzip',
    parse_dates=['timestamp_utc']).sort_values('timestamp_utc').reset_index(drop=True)
stored['bar_id']=(stored.timestamp_utc.astype('int64')//(900*1_000_000_000)).astype('int64')
assert stored.bar_id.is_unique
# Signal uses only pre-entry bars, and additionally verifies bars are chronologically earlier.
stored['B'] = np.where(stored.bid_close.shift(1)>stored.bid_high.shift(2).rolling(3).max(),1,-1)
mid=(stored.bid_high.shift(1).rolling(3).max()+stored.bid_low.shift(1).rolling(3).min())/2
stored['C'] = np.where(stored.bid_close.shift(1)>mid,1,-1)
hist=stored.set_index('bar_id')
rows=[];ledgers=[];arch=[];timed_rows=[]
for mm in ['08','09','10']:
 mon='2026-'+mm
 url=f'https://ticks.ex2archive.com/ticks/XAGUSD/2026/{mm}/Exness_XAGUSD_2026_{mm}.zip'
 response=S.get(url,timeout=120);response.raise_for_status()
 sha=hashlib.sha256(response.content).hexdigest()
 with zipfile.ZipFile(io.BytesIO(response.content)) as z:
  tick=pd.read_csv(z.open(z.namelist()[0]),usecols=['Timestamp','Bid','Ask'])
 ts=pd.to_datetime(tick.Timestamp,utc=True).astype('int64').to_numpy()
 bid=tick.Bid.to_numpy(dtype='float64');ask=tick.Ask.to_numpy(dtype='float64')
 unsorted=int(np.sum(ts[1:]<ts[:-1]))
 if unsorted:
  ii=np.argsort(ts,kind='stable');ts,bid,ask=ts[ii],bid[ii],ask[ii]
 negspread=int(np.sum(ask<bid))
 assert negspread==0
 # Count repeated time stamps without indiscriminately discarding distinct bidask quotes.
 duplicate_ts=int(np.sum(ts[1:]==ts[:-1]))
 duplicate_exact=int(np.sum((ts[1:]==ts[:-1])&(bid[1:]==bid[:-1])&(ask[1:]==ask[:-1])))
 bidx=ts//(900*1_000_000_000)
 first=np.r_[0,np.flatnonzero(bidx[1:]!=bidx[:-1])+1]
 end=np.r_[first[1:],len(bidx)];last=end-1;keys=bidx[first]
 ne=len(keys);n=len(bidx)
 month_hist=hist.reindex(keys)
 assert not month_hist.bid_open.isna().any()
 # Audit tick vs preexisting saved M15 OHLC including both quotes.
 prices={
 'bid_open':bid[first], 'bid_high':np.maximum.reduceat(bid,first),
 'bid_low':np.minimum.reduceat(bid,first),'bid_close':bid[last],
 'ask_open':ask[first],'ask_high':np.maximum.reduceat(ask,first),
 'ask_low':np.minimum.reduceat(ask,first),'ask_close':ask[last],
 'tick_count':end-first}
 mismatch={k:int(np.count_nonzero(~np.isclose(v,month_hist[k].to_numpy(),atol=1e-9,rtol=0))) for k,v in prices.items()}
 maxdiff={k:float(np.max(np.abs(v-month_hist[k].to_numpy()))) for k,v in prices.items()}
 bad=any(mismatch.values())
 secondsBeforeEnd=(keys+1)*900-ts[last]/1e9
 gap_bars=np.diff(keys)
 gaps_more_15=int(np.sum(gap_bars>1))
 # timestamp audit: saved M15 and raw tick M15 distinct matching
 dates=pd.to_datetime(keys*900,unit='s',utc=True).strftime('%Y-%m-%d').to_numpy()
 spr=ask[first]-bid[first]
 meta={'month':mon,'url':url,'zip_sha256':sha,'zip_bytes':len(response.content),
       'ticks':int(n),'candles':ne,'first_tick':str(pd.to_datetime(ts[0],utc=True)),
       'last_tick':str(pd.to_datetime(ts[-1],utc=True)),
       'nonmonotonic_ticks':unsorted,'duplicate_timestamp_neighbors':duplicate_ts,
       'exact_duplicate_neighbor_ticks':duplicate_exact,'negative_spreads':negspread,
       'missing_m15_mismatches':mismatch,'max_ohlc_diffs':maxdiff,
       'bar_gaps_over_15_minutes':gaps_more_15,'max_bar_gap_minutes':int(gap_bars.max()*15),
       'average_spread_usd_per_oz':float(np.mean(spr)),'median_spread_usd_per_oz':float(np.median(spr)),
       'p99_spread_usd_per_oz':float(np.quantile(spr,.99)),
       'max_spread_usd_per_oz':float(np.max(spr)),
       'EOC_last_tick_seconds_prior_median':float(np.median(secondsBeforeEnd)),
       'EOC_last_tick_seconds_prior_p99':float(np.quantile(secondsBeforeEnd,.99)),
       'EOC_last_tick_older_60sec':int(np.sum(secondsBeforeEnd>60))}
 arch.append(meta); print("DATA",json.dumps(meta),flush=True)
 assert not bad,'Tick aggregation differs from previous M15, stop test'
 # Each tick pnl is marked to actionable quote (long close Bid, short close Ask).
 # Fill: immediate at first bar tick, TP at fixed limit price on first crossing,
 # SL at first tick observed beyond stop including gaps, otherwise last bar tick.
 ix=np.arange(n,dtype=np.int32);maxix=n+1
 for method in ['B','C','SHORT']:
  side=np.full(ne,-1,dtype='int8') if method=='SHORT' else month_hist[method].to_numpy(dtype='int8')
  quote_entry=np.where(side==1,ask[first],bid[first])
  quote_exit=np.where(np.repeat(side,end-first)==1,bid,ask)
  entry_repeated=np.repeat(quote_entry,end-first)
  sign_repeated=np.repeat(side,end-first)
  unit_quote=(quote_exit-entry_repeated)*sign_repeated
  for lot in LOTS:
   nominal=CONTRACT*lot
   u=unit_quote*nominal
   hit_tp=np.minimum.reduceat(np.where(u>=TP_USD-1e-10,ix,maxix),first)
   hit_sl=np.minimum.reduceat(np.where(u<=-SL_USD+1e-10,ix,maxix),first)
   is_tp=(hit_tp<hit_sl)&(hit_tp<=last)
   is_sl=(hit_sl<hit_tp)&(hit_sl<=last)
   is_eoc=~(is_tp|is_sl)
   ei=np.where(is_tp,hit_tp,np.where(is_sl,hit_sl,last))
   # target limit filled at exact +10 USD, stop market at first tick crossing, EOC quote last tick.
   p=np.where(is_tp,TP_USD,np.where(is_sl,u[np.minimum(hit_sl,n-1)],u[last]))
   # Timed exit robustness: execute first quote at/after 14m50s where available;
   # if none in the final 10s, fallback last tick and count as non-executable.
   if lot==0.01:
    cutoff_ns=((keys+1)*900-10)*1_000_000_000
    candidate=np.searchsorted(ts,cutoff_ns,side='left')
    has_cutoff=candidate<end
    cutoff=np.minimum(candidate,last)
    j_tp=(hit_tp<hit_sl)&(hit_tp<=cutoff)
    j_sl=(hit_sl<hit_tp)&(hit_sl<=cutoff)
    j_p=np.where(j_tp,TP_USD,np.where(j_sl,u[np.minimum(hit_sl,n-1)],u[cutoff]))
    timed_rows.append({'month':mon,'method':method,'lot':lot,
      'timed_exit_10s_before_close_net_usd':float(j_p.sum()),
      'reference_last_tick_net_usd':float(p.sum()),
      'bars_without_quote_last10s':int(np.sum(~has_cutoff)),
      'timed_exit_tp':int(j_tp.sum()),'timed_exit_sl':int(j_sl.sum()),
      'timed_exit_eoc':int(np.sum(~(j_tp|j_sl)))})

   spread_cost_entry=spr*nominal
   commission_raw_per_trade=7*lot     # Exness: $3.50 per lot per side, for Raw Spread only; not matching quote feed
   commission_zero_per_trade=100*lot   # Exness: $50 per lot per side, for Zero only; not matching quote feed
   # Additional adverse execution 0.005 USD/oz per side = 0.010 round trip, simulated as fee,
   # accounts for plausible slippage, rather than claiming measured slippage.
   extra_slippage_case=0.01*nominal
   dates_g=pd.Series(p,index=dates).groupby(level=0).sum()
   eq=np.r_[0,np.cumsum(p)]
   win=p>1e-8;loss=p< -1e-8
   pf=float(p[win].sum()/-p[loss].sum()) if loss.any() else None
   row={'month':mon,'method':method,'lot':lot,'trades':ne,
        'long':int((side==1).sum()),'short':int((side==-1).sum()),
        'wins':int(win.sum()),'losses':int(loss.sum()),'flats':int(ne-win.sum()-loss.sum()),
        'win_rate_pct':float(np.mean(win)*100),'profit_factor':pf,'pnl_usd':float(p.sum()),
        'avg_pnl_usd':float(np.mean(p)),'max_dd_usd':float(np.max(np.maximum.accumulate(eq)-eq)),
        'tp_count':int(is_tp.sum()),'sl_count':int(is_sl.sum()),'eoc_count':int(is_eoc.sum()),
        'profitable_days':int((dates_g>1e-8).sum()),'losing_days':int((dates_g< -1e-8).sum()),
        'flat_days':int((abs(dates_g)<=1e-8).sum()),
        'entry_spread_gte_stop_usd_count':int(np.sum(spread_cost_entry>=SL_USD)),
        'stop_worse_than_minus5_count':int(np.sum(p[is_sl]<-5.0000001)),
        'worst_trade_usd':float(np.min(p)),
        'net_usd_extra_0p01_per_oz_roundtrip':float(p.sum()-ne*extra_slippage_case),
        'net_usd_raw_commission_scenario':float(p.sum()-ne*commission_raw_per_trade),
        'net_usd_zero_commission_scenario':float(p.sum()-ne*commission_zero_per_trade),
        'net_usd_extra_0p5_per_trade':float(p.sum()-0.5*ne),
        'net_usd_extra_1p0_per_trade':float(p.sum()-1.0*ne),
        'nominal_units_oz':nominal,
        'tp_delta_price':TP_USD/nominal,'sl_delta_price':SL_USD/nominal}
   rows.append(row)
   if lot==0.01:
    # Full ledger for both methods, baseline as comparator
    ledgers.append(pd.DataFrame({
      'month':mon,'method':method,'lot':lot,
      'bar_start_utc':pd.to_datetime(keys*900,unit='s',utc=True),
      'entry_tick_utc':pd.to_datetime(ts[first],utc=True),
      'exit_quote_utc':pd.to_datetime(ts[np.minimum(ei,n-1)],utc=True),
      'side':np.where(side==1,'LONG','SHORT'),'entry_quote':quote_entry,
      'spread_entry':spr,'exit_quote':quote_exit[np.minimum(ei,n-1)],
      'exit_reason':np.where(is_tp,'TP',np.where(is_sl,'SL','EOC')),
      'exit_fill_model_price':np.where(is_tp,quote_entry+side*(TP_USD/nominal),quote_exit[np.minimum(ei,n-1)]),
      'pnl_usd':p,'commission_usd_assumed':np.zeros(ne)}))
   print('DONE',mon,method,lot,'PNL_USD',round(float(p.sum()),3),
         'TP_SL_EOC',(int(is_tp.sum()),int(is_sl.sum()),int(is_eoc.sum())),flush=True)
 del tick,response,ts,bid,ask,bidx,quote_exit,unit_quote
grid=pd.DataFrame(rows)
grid.to_csv(BASE/'all_lots_monthly.csv',index=False)
pd.DataFrame(timed_rows).to_csv(BASE/'timed_exit_10sec_robustness.csv',index=False)
ledger=pd.concat(ledgers,ignore_index=True)
ledger.to_csv(BASE/'trades_lot001_all_methods.csv',index=False)
total=[]
for method in ['B','C','SHORT']:
 for lot in LOTS:
  t=grid[(grid.method==method)&(grid.lot==lot)].set_index('month').loc[MONTHS]
  p=ledger[ledger.method==method].pnl_usd.to_numpy() if lot==0.01 else None
  vals={c:float(t[c].sum()) for c in ['pnl_usd','net_usd_extra_0p01_per_oz_roundtrip','net_usd_raw_commission_scenario','net_usd_zero_commission_scenario','net_usd_extra_0p5_per_trade','net_usd_extra_1p0_per_trade']}
  row={'method':method,'lot':lot,'trades':int(t.trades.sum()),
   'long':int(t.long.sum()),'short':int(t.short.sum()),
   'profit_months':int((t.pnl_usd>0).sum()),'losing_months':int((t.pnl_usd<0).sum()),
   'win_rate_pct':float(t.wins.sum()/t.trades.sum()*100),
   'wins':int(t.wins.sum()),'losses':int(t.losses.sum()),'flats':int(t.flats.sum()),
   'tp_count':int(t.tp_count.sum()),'sl_count':int(t.sl_count.sum()),'eoc_count':int(t.eoc_count.sum()),
   'profitable_days':int(t.profitable_days.sum()),'losing_days':int(t.losing_days.sum()),
   'entry_spread_gte_stop_usd_count':int(t.entry_spread_gte_stop_usd_count.sum()),
   'months':{m:float(t.loc[m,'pnl_usd']) for m in MONTHS},
   'sum_monthly_max_dd_usd':float(t.max_dd_usd.sum()),**vals}
  if lot==0.01:
   eq=np.r_[0,np.cumsum(p)]
   row['max_dd_usd']=float(np.max(np.maximum.accumulate(eq)-eq))
   win=p>1e-8;lose=p< -1e-8
   row['profit_factor']=float(p[win].sum()/-p[lose].sum())
   row['average_trade_usd']=float(p.mean())
  total.append(row)
results={'symbol':'XAGUSD','contract_size_oz_per_1_lot':5000,'target_tp_usd':10.,'target_sl_usd':-5.,
 'quote_feed':'Exness_XAGUSD no suffix, BID/ASK, public tick archives','source_M15':'existing Deepnote v18 XAGUSD 2026 M15',
 'method_B':'prev M15 BID CLOSE > max BID HIGH of preceding three M15 bars BEFORE signal bar => LONG, else SHORT',
 'method_C':'prev M15 BID CLOSE > midpoint(max BID HIGH, min BID LOW of 3 closed recent bars) => LONG, else SHORT',
 'entry_exit':'First bidask quote in M15, stops first crossed tick, TP exactly +10 USD limit, SL at crossed quote, EOC last tick within M15.',
 'EOC_caveat':'Using last tick within each M15 for timed exit is hindsight; cannot guarantee live order could know to close there.',
 'cost_model':'quoted spread included; 0 commission and no additional slippage in base. Extra cost scenario as labeled. No backcom, no swaps.',
 'stop_level_caveat':'Trading platform exact stop level/freeze level and market-order rejections are not tested; some stops may violate broker rules.',
 'months_meta':arch,'timed_exit_10sec_robustness':timed_rows,'totals':total,'monthly_001':grid[grid.lot==.01].to_dict('records')}
(BASE/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str))
print('TIMED_EXIT',json.dumps(timed_rows,ensure_ascii=False),flush=True)
print('FINAL_001',json.dumps([x for x in total if x['lot']==0.01],ensure_ascii=False),flush=True)
print('FINAL_OTHER_LOTS',json.dumps([x for x in total if x['lot']!=0.01],ensure_ascii=False),flush=True)
print('FILES',[(p.name,p.stat().st_size) for p in BASE.iterdir()],flush=True)
