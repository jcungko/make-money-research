"""Independent audit selected Aug-Sep locked XAGUSD B/C USD grid and timed exit."""
from pathlib import Path
import requests,io,zipfile,hashlib,pandas as pd,numpy as np,json
D=Path("xag_bc_sl_tp_grid_202608_10")
H=pd.read_csv("v18data/XAGUSD/2026/XAGUSD_M15_2026_UTC.csv.gz",compression="gzip",parse_dates=["timestamp_utc"]).sort_values("timestamp_utc").reset_index(drop=True)
H['bucket']=(H.timestamp_utc.astype('int64')//900_000_000_000).astype('int64')
H['B']=np.where(H.bid_close.shift(1)>H.bid_high.shift(2).rolling(3).max(),1,-1)
H['C']=np.where(H.bid_close.shift(1)>(H.bid_high.shift(1).rolling(3).max()+H.bid_low.shift(1).rolling(3).min())/2,1,-1)
H=H.set_index('bucket')
variants=[('B',9,6),('C',9,6),('SHORT',9,9),('B',5,10),('C',5,10)]
results={str((m,s,t)):[] for m,s,t in variants}
journal={str((m,s,t)):[] for m,s,t in variants}
S=requests.Session()
for month in ['2026-08','2026-09','2026-10']:
 mm=month[-2:];url=f'https://ticks.ex2archive.com/ticks/XAGUSD/2026/{mm}/Exness_XAGUSD_2026_{mm}.zip'
 r=S.get(url,timeout=120);r.raise_for_status()
 with zipfile.ZipFile(io.BytesIO(r.content)) as z:
  ticks=pd.read_csv(z.open(z.namelist()[0]),usecols=['Timestamp','Bid','Ask'])
 ns=pd.to_datetime(ticks.Timestamp,utc=True).astype('int64').to_numpy();bid=ticks.Bid.to_numpy();ask=ticks.Ask.to_numpy()
 keys=ns//900_000_000_000
 begins=np.r_[0,np.flatnonzero(keys[1:]!=keys[:-1])+1]
 ends=np.r_[begins[1:],len(keys)];last=ends-1;bar=keys[begins]
 frame=H.reindex(bar)
 j=np.arange(len(ns),dtype=np.int32);sentinel=len(ns)+1
 timing_threshold=(bar+1)*900*1_000_000_000-10*1_000_000_000
 first_near=np.searchsorted(ns,timing_threshold,'left')
 has_late_tick=first_near<ends
 lastnear=np.minimum(first_near,last)
 assert np.all(lastnear>=begins)
 for method,sl,tp in variants:
  lab=str((method,sl,tp))
  sig=np.full(len(bar),-1) if method=='SHORT' else frame[method].to_numpy()
  startprice=np.where(sig==1,ask[begins],bid[begins])
  side=np.repeat(sig,ends-begins)
  quotes=np.where(side==1,bid,ask)
  change=(quotes-np.repeat(startprice,ends-begins))*side*50
  hs=np.minimum.reduceat(np.where(change<=-sl+1e-9,j,sentinel),begins)
  ht=np.minimum.reduceat(np.where(change>=tp-1e-9,j,sentinel),begins)
  tpHit=(ht<hs)&(ht<=last)
  slHit=(hs<ht)&(hs<=last)
  pnl=np.where(tpHit,tp,np.where(slHit,change[np.minimum(hs,len(ns)-1)],change[last]))
  # Last tick in bar = retrospective bar close proxy.
  eq=np.r_[0,np.cumsum(pnl)]
  dates=pd.to_datetime(bar*900,unit='s',utc=True).strftime('%Y-%m-%d')
  wins=pnl>1e-9;losses=pnl< -1e-9
  days=pd.Series(pnl,index=dates).groupby(level=0).sum()
  # "Timed" alternative stop at first tick on/after 14m50s if available, never select future last tick on viable bars.
  t_tp=(ht<hs)&(ht<=lastnear)
  t_sl=(hs<ht)&(hs<=lastnear)
  t_pnl=np.where(t_tp,tp,np.where(t_sl,change[np.minimum(hs,len(ns)-1)],change[lastnear]))
  rows={'month':month,'method':method,'sl_usd':sl,'tp_usd':tp,'trades':len(bar),
    'pnl_usd':float(pnl.sum()),'tp_count':int(tpHit.sum()),'sl_count':int(slHit.sum()),'time_count':int((~(tpHit|slHit)).sum()),
    'wins':int(wins.sum()),'losses':int(losses.sum()),'flat':int((~(wins|losses)).sum()),
    'gross_wins_usd':float(pnl[wins].sum()),'gross_loss_abs_usd':float(-pnl[losses].sum()),
    'max_dd_usd':float(np.max(np.maximum.accumulate(eq)-eq)),
    'green_days':int((days>0).sum()),'red_days':int((days<0).sum()),
    'overshoot_SL_count':int(((pnl<-sl-1e-9)&slHit).sum()),
    'timed_14m50s_pnl_usd_fallback_lastquote_if_none':float(t_pnl.sum()),
    'time_exit_no_quote_last_10_seconds_count':int(np.sum(~has_late_tick))}
  results[lab].append(rows)
  journal[lab].append(pnl)
  print("AUDIT",month,method,sl,tp,"NET",round(pnl.sum(),2),"time",round(t_pnl.sum(),2),flush=True)
 del ticks,r,ns,bid,ask
totals=[]
for (method,sl,tp) in variants:
 lab=str((method,sl,tp))
 values=np.concatenate(journal[lab])
 curve=np.r_[0,np.cumsum(values)]
 wins=values>1e-9;losses=values< -1e-9
 rec={'method':method,'sl_usd':sl,'tp_usd':tp,'n':len(values),
   'pnl_usd':float(values.sum()),'wins':int(wins.sum()),'losses':int(losses.sum()),'flat':int((~(wins|losses)).sum()),
   'win_pct':float(wins.mean()*100),'pf':float(values[wins].sum()/-values[losses].sum()),
   'max_dd_usd':float(np.max(np.maximum.accumulate(curve)-curve)),
   'avg_trade_usd':float(values.mean()),
   'tp':sum(int(x['tp_count']) for x in results[lab]),
   'sl':sum(int(x['sl_count']) for x in results[lab]),
   'time_exit':sum(int(x['time_count']) for x in results[lab]),
   'profitable_days':sum(int(x['green_days']) for x in results[lab]),
   'losing_days':sum(int(x['red_days']) for x in results[lab]),
   'sl_overshoot_count':sum(int(x['overshoot_SL_count']) for x in results[lab]),
   'total_timed_14m50s_usd':sum(x['timed_14m50s_pnl_usd_fallback_lastquote_if_none'] for x in results[lab]),
   'no_quote_last10s':sum(int(x['time_exit_no_quote_last_10_seconds_count']) for x in results[lab]),
   'monthly':results[lab]}
 totals.append(rec)
(D/'selected_locked_audit.json').write_text(json.dumps(totals,indent=2,default=str))
pd.DataFrame([{k:v for k,v in x.items() if k!='monthly'} for x in totals]).to_csv(D/'selected_locked_totals.csv',index=False)

print("TOTALS",json.dumps(totals,ensure_ascii=False),flush=True)
