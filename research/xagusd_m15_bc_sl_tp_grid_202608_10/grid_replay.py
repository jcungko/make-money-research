"""
Exness XAGUSD M15: exact fixed-USD SL/TP grid, 0.01 lot.
Methods B/C unchanged, compare always SHORT. In-sample August-September,
chronological October test of preselected candidates (not globally pristine).
Research only: no live broker orders.
"""
import io, zipfile, json, hashlib, requests
from pathlib import Path
import pandas as pd, numpy as np

DIR=Path('xag_bc_sl_tp_grid_202608_10')
DIR.mkdir(exist_ok=True)
SLS=(5,6,7,8,9,10,15,20)
TPS=(2,3,4,5,6,7,8,9,10)
MONTHS=('2026-08','2026-09','2026-10')
PAIRS=[(sl,tp) for sl in SLS for tp in TPS]
CONTRACT_OZ=5000
LOT=0.01
OZ=CONTRACT_OZ*LOT # 50 oz
assert len(PAIRS)==72 and OZ==50
source = pd.read_csv("v18data/XAGUSD/2026/XAGUSD_M15_2026_UTC.csv.gz",compression='gzip',parse_dates=['timestamp_utc']).sort_values("timestamp_utc").reset_index(drop=True)
source['bucket']=(source.timestamp_utc.astype('int64')//900_000_000_000).astype('int64')
assert source.bucket.is_unique
# B uses highs 2,3,4 candles before entry, never the signal candle itself (entry-1).
source["B"]=np.where(source.bid_close.shift(1)>source.bid_high.shift(2).rolling(3).max(),1,-1)
# C uses highs lows 1,2,3 candles before entry
source["C"]=np.where(source.bid_close.shift(1)>(source.bid_high.shift(1).rolling(3).max()+source.bid_low.shift(1).rolling(3).min())/2,1,-1)
hist=source.set_index('bucket')
session=requests.Session()
rows=[]; provenance=[]; timed_rows=[]
for month in MONTHS:
 mm=month[-2:]
 url=f"https://ticks.ex2archive.com/ticks/XAGUSD/2026/{mm}/Exness_XAGUSD_2026_{mm}.zip"
 res=session.get(url,timeout=120);res.raise_for_status()
 sha=hashlib.sha256(res.content).hexdigest()
 with zipfile.ZipFile(io.BytesIO(res.content)) as z:
  tick=pd.read_csv(z.open(z.namelist()[0]),usecols=['Timestamp','Bid','Ask'])
 stamp=pd.to_datetime(tick.Timestamp,utc=True).astype('int64').to_numpy()
 bid=tick.Bid.to_numpy(dtype=np.float64); ask=tick.Ask.to_numpy(dtype=np.float64)
 backwards=int(np.count_nonzero(stamp[1:]<stamp[:-1]))
 duplicates=int(np.count_nonzero((stamp[1:]==stamp[:-1])&(bid[1:]==bid[:-1])&(ask[1:]==ask[:-1])))
 assert backwards==0 and np.all(ask>=bid)
 buckets=stamp//900_000_000_000
 starts=np.r_[0,np.flatnonzero(np.diff(buckets))+1]
 ends=np.r_[starts[1:],len(buckets)]
 last=ends-1; keys=buckets[starts]
 n=len(stamp); nbar=len(keys)
 src=hist.reindex(keys)
 assert not src.bid_close.isna().any()
 check={'bid_open':bid[starts],'bid_high':np.maximum.reduceat(bid,starts),'bid_low':np.minimum.reduceat(bid,starts),'bid_close':bid[last],
   'ask_open':ask[starts],'ask_high':np.maximum.reduceat(ask,starts),'ask_low':np.minimum.reduceat(ask,starts),'ask_close':ask[last],
   'tick_count':ends-starts}
 mismatch={k:int(np.count_nonzero(~np.isclose(v,src[k].to_numpy(),rtol=0,atol=1e-9))) for k,v in check.items()}
 assert sum(mismatch.values())==0, mismatch
 gaps=int(np.sum(np.diff(keys)>1))
 dates=pd.to_datetime(keys*900,unit='s',utc=True).strftime('%Y-%m-%d').to_numpy()
 open_spread=(ask[starts]-bid[starts])*OZ
 time_before_eoc=(keys+1)*900-stamp[last]/1e9
 prov={'month':month,'ticks':n,'candles':nbar,'zip_bytes':len(res.content),'sha256':sha,'url':url,
     'first_tick':str(pd.to_datetime(stamp[0],unit='ns',utc=True)),
     'last_tick':str(pd.to_datetime(stamp[-1],unit='ns',utc=True)),
     'backwards_timestamps':backwards,'identical_adjacent_duplicates':duplicates,
     'bid_ask_m15_mismatches':mismatch,'gaps_in_bar_sequence':gaps,
     'average_spread_usd_per_trade':float(open_spread.mean()),
     'p99_spread_usd_per_trade':float(np.quantile(open_spread,.99)),
     'last_quote_older_60s':int(np.count_nonzero(time_before_eoc>60))}
 provenance.append(prov)
 print("DATA",json.dumps(prov),flush=True)
 ix=np.arange(n,dtype=np.int32);inf=n+1
 for method in ['B','C','SHORT']:
  side=np.full(nbar,-1,dtype='int8') if method=='SHORT' else src[method].to_numpy(dtype='int8')
  entry=np.where(side==1,ask[starts],bid[starts])
  repeated_side=np.repeat(side,ends-starts)
  exitquote=np.where(repeated_side==1,bid,ask)
  entry_repeat=np.repeat(entry,ends-starts)
  move=(exitquote-entry_repeat)*repeated_side*OZ
  # precompute first observed threshold cross for all targets, all stops.
  # Some stops are jumped: negative outcome uses observed execution quote, NOT nominal -SL.
  hitp={tp:np.minimum.reduceat(np.where(move>=tp-1e-9,ix,inf),starts) for tp in TPS}
  hits={sl:np.minimum.reduceat(np.where(move<=-sl+1e-9,ix,inf),starts) for sl in SLS}
  date_index=pd.Index(dates,name='UTC_trade_day')
  for sl,tp in PAIRS:
   p_ix=hitp[tp];s_ix=hits[sl]
   is_tp=(p_ix<s_ix)&(p_ix<=last)
   is_sl=(s_ix<p_ix)&(s_ix<=last)
   is_eoc=~(is_tp|is_sl)

   close_index=np.where(is_tp,p_ix,np.where(is_sl,s_ix,last))
   # TP limit exact +TP USD, SL first crossed Bid/Ask quote (gaps possible), otherwise last quote
   pnl=np.where(is_tp,float(tp),np.where(is_sl,move[np.minimum(s_ix,n-1)],move[last]))
   # reference OHLC/eoc last tick is hindsight; not guaranteed broker-executable
   daily=pd.Series(pnl,index=date_index).groupby(level=0).sum()
   positive=pnl>1e-8; negative=pnl< -1e-8
   curve=np.r_[0,pnl.cumsum()]
   result={
    'method':method,'month':month,'sl_usd':sl,'tp_usd':tp,'lot':LOT,'trades':nbar,
    'long':int((side==1).sum()),'short':int((side==-1).sum()),
    'wins':int(positive.sum()),'losses':int(negative.sum()),'flats':int(nbar-positive.sum()-negative.sum()),
    'win_rate_pct':float(positive.mean()*100),
    'pnl_usd':float(pnl.sum()),'avg_trade_usd':float(pnl.mean()),
    'gross_win_usd':float(pnl[positive].sum()),'gross_loss_abs_usd':float(-pnl[negative].sum()),
    'profit_factor':float(pnl[positive].sum() / (-pnl[negative].sum())) if negative.any() else None,
    'max_dd_usd':float(np.max(np.maximum.accumulate(curve)-curve)),
    'profitable_days':int((daily>1e-8).sum()),'losing_days':int((daily< -1e-8).sum()),'flat_days':int((daily.abs()<=1e-8).sum()),
    'tp_count':int(is_tp.sum()),'sl_count':int(is_sl.sum()),'time_exit_count':int(is_eoc.sum()),
    'stop_overshoot_count':int(np.count_nonzero(pnl[is_sl]<-sl-1e-6)),
    'spread_at_entry_gt_SL_count':int(np.count_nonzero(open_spread>=sl)),
    'net_if_plus_0p5_usd_cost_per_trade':float(pnl.sum()-nbar*.5),
    'net_if_plus_1_usd_cost_per_trade':float(pnl.sum()-nbar*1.)}
   rows.append(result)
  # timed-exit sensitivity for top grid only, to be selected without October later:
  # already compute universal cutoffs but use them after global selection requires rerun
  print("METHOD",month,method,'n=',nbar,'signals LONG',int((side==1).sum()),'SHORT',int((side==-1).sum()),'grid',len(PAIRS),flush=True)
  del move,exitquote,entry_repeat,repeated_side
 del tick,res,stamp,bid,ask,buckets

frame=pd.DataFrame(rows)
assert len(frame)==3*3*len(PAIRS)
frame.to_csv(DIR/'all_monthly_648_rows.csv',index=False)
allconfigs=[]
for method in ['B','C','SHORT']:
 for sl,tp in PAIRS:
  grp=frame[(frame.method==method)&(frame.sl_usd==sl)&(frame.tp_usd==tp)].set_index('month').loc[list(MONTHS)]
  p=grp.pnl_usd
  allconfigs.append({'method':method,'sl_usd':sl,'tp_usd':tp,
    'aug_usd':float(p.loc['2026-08']),'sep_usd':float(p.loc['2026-09']),
    'train_aug_sep_usd':float(p.loc[['2026-08','2026-09']].sum()),
    'oct_holdout_usd':float(p.loc['2026-10']),'all_3_usd':float(p.sum()),
    'profitable_months':int((p>0).sum()),'all_3_positive':bool((p>0).all()),
    'train_both_positive':bool((p.loc[['2026-08','2026-09']]>0).all()),
    'oct_plus_0p5_cost_usd':float(grp.loc['2026-10','net_if_plus_0p5_usd_cost_per_trade']),
    'oct_plus_1_cost_usd':float(grp.loc['2026-10','net_if_plus_1_usd_cost_per_trade']),
    'overall_plus_0p5_cost_usd':float(grp['net_if_plus_0p5_usd_cost_per_trade'].sum())})
config=pd.DataFrame(allconfigs)
config.to_csv(DIR/'all_config_train_oos_216_rows.csv',index=False)
selected=[]
for method in ['B','C','SHORT']:
 t=config[config.method==method].sort_values(['train_aug_sep_usd','tp_usd','sl_usd'],ascending=[False,True,True])
 selected.append(t.iloc[0].to_dict())
pd.DataFrame(selected).to_csv(DIR/'locked_selection_aug_sep.csv',index=False)
base=frame[(frame.sl_usd==5)&(frame.tp_usd==10)].sort_values(['method','month'])
report={
 'asset':'XAGUSD','contract_oz_per_lot':CONTRACT_OZ,'lot':LOT,
 'sl_usd':list(SLS),'tp_usd':list(TPS),'pairs_per_method':len(PAIRS),
 'months':list(MONTHS),'price_feed':'Exness XAGUSD public Bid/Ask tick archive no suffix',
 'costs':'Observed spread included; commission=0, extra slippage=0 in base; sensitivity +$0.50 and +$1 per order; Backcom excluded.',
 'execution_model':'buy ASK/sell BID first tick each M15, TP filled exact at limit, stop first quoted crossed (gap may exceed nominal), time exit last quote of M15 (hindsight approximation; not guaranteed live fill)',
 'selection_rule':'highest Aug+Sep combined PnL among 72 USD pairs, no October info in selection; comparison Oct tested only after selection',
 'data_provenance':provenance,'selected':selected,
 'positive_both_train_count_by_method':{m:int(config[(config.method==m)&config.train_both_positive].shape[0]) for m in ['B','C','SHORT']},
 'positive_oct_count_by_method':{m:int(config[(config.method==m)&(config.oct_holdout_usd>0)].shape[0]) for m in ['B','C','SHORT']},
 'positive_three_months_count_by_method':{m:int(config[(config.method==m)&config.all_3_positive].shape[0]) for m in ['B','C','SHORT']},
 'positive_any_three_count':int(config.all_3_positive.sum()),
 'configs':len(config),
 'base_original_tp10_sl5':base.to_dict('records'),
 'best_overall_in_sample_descriptive_only':config.sort_values('all_3_usd',ascending=False).head(12).to_dict('records'),
 'top_train_per_method':{m:config[config.method==m].sort_values('train_aug_sep_usd',ascending=False).head(10).to_dict('records') for m in ['B','C','SHORT']}
}
(DIR/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str))
print('SELECTED',json.dumps(selected,ensure_ascii=False),flush=True)
print('COUNTS',report['positive_both_train_count_by_method'],report['positive_oct_count_by_method'],report['positive_three_months_count_by_method'],flush=True)
print('BEST_OVERALL_DESCRIPTIVE',json.dumps(report['best_overall_in_sample_descriptive_only'],ensure_ascii=False),flush=True)
print('FILES',[(f.name,f.stat().st_size) for f in DIR.iterdir()],flush=True)
