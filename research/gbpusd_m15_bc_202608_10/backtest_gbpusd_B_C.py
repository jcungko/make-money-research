
import io,zipfile,json,hashlib,requests
import pandas as pd,numpy as np
from pathlib import Path
PIP_VALUE=0.1
SLS=[2,3,4,5,6,8,10]; TPS=[2,3,4,5,6,8,10]
CONFIGS=[(s,t) for s in SLS for t in TPS if t>=s]
MONTHS=['2026-08','2026-09','2026-10']
OUT=Path('gbpusd_bc_outputs'); OUT.mkdir(exist_ok=True)
ses=requests.Session()
src_url='https://raw.githubusercontent.com/jcungko/make-money-research/main/data/v17_exness_2026/GBPUSD_2026_UTC_7TF.zip'
r=ses.get(src_url,timeout=60);r.raise_for_status()
with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    old=pd.read_csv(z.open('GBPUSD_M15_2026_UTC.csv'),parse_dates=['timestamp_utc'])
old=old[old.timestamp_utc<pd.Timestamp('2026-08-01',tz='UTC')]
old=old[['timestamp_utc','bid_open','bid_high','bid_low','bid_close']].copy()
old['bar_id']=(old.timestamp_utc.astype('int64')//900_000_000_000).astype('int64')
raw_groups={};agg_frames=[];meta=[]
for mon in ['08','09','10']:
    url=f'https://ticks.ex2archive.com/ticks/GBPUSD/2026/{mon}/Exness_GBPUSD_2026_{mon}.zip'
    raw=ses.get(url,timeout=120);raw.raise_for_status()
    digest=hashlib.sha256(raw.content).hexdigest()
    with zipfile.ZipFile(io.BytesIO(raw.content)) as z:
        tick=pd.read_csv(z.open(z.namelist()[0]),usecols=['Timestamp','Bid','Ask'])
    tns=pd.to_datetime(tick.Timestamp,utc=True).astype('int64').to_numpy()
    bid=tick.Bid.to_numpy(dtype=float);ask=tick.Ask.to_numpy(dtype=float)
    ooo=int(np.sum(tns[1:]<tns[:-1]))
    if ooo:
        ix=np.argsort(tns,kind='stable');tns,bid,ask=tns[ix],bid[ix],ask[ix]
    assert (ask>=bid).all(),'Invalid negative spread'
    bn=tns//900_000_000_000
    starts=np.r_[0,np.flatnonzero(bn[1:]!=bn[:-1])+1];ends=np.r_[starts[1:],len(bn)]
    keys=bn[starts]
    agg=pd.DataFrame({'bar_id':keys,'timestamp_utc':pd.to_datetime(keys*900,unit='s',utc=True),
                      'bid_open':bid[starts],'bid_high':np.maximum.reduceat(bid,starts),
                      'bid_low':np.minimum.reduceat(bid,starts),'bid_close':bid[ends-1]})
    agg_frames.append(agg)
    raw_groups['2026-'+mon]={'tns':tns,'bid':bid,'ask':ask,'starts':starts,'ends':ends,'keys':keys}
    close_early=keys*900+900-tns[ends-1]/1e9
    meta.append({'month':'2026-'+mon,'source':url,'sha256':digest,
      'zip_bytes':len(raw.content),'ticks':len(tns),'bars':len(keys),'out_of_order_ticks':ooo,
      'first_tick':str(pd.to_datetime(tns[0],utc=True)),
      'last_tick':str(pd.to_datetime(tns[-1],utc=True)),
      'last_tick_seconds_before_bar_end_median':float(np.median(close_early)),
      'last_tick_seconds_before_bar_end_p99':float(np.quantile(close_early,.99)),
      'close_proxy_older_than_60s_bars':int((close_early>60).sum()),
      'entry_spread_avg_pips':float(np.mean((ask[starts]-bid[starts])*10000)),
      'entry_spread_p99_pips':float(np.quantile((ask[starts]-bid[starts])*10000,.99))})
    print('READ_MONTH',meta[-1],flush=True)
    del tick,raw

raw_agg=pd.concat(agg_frames,ignore_index=True)
full=pd.concat([old,raw_agg[old.columns]],ignore_index=True).sort_values('bar_id').drop_duplicates('bar_id',keep='last').reset_index(drop=True)
last_close=full.bid_close.shift(1)
full['B']=np.where(last_close>full.bid_high.shift(2).rolling(3).max(),1,-1)
max3=full.bid_high.shift(1).rolling(3).max()
min3=full.bid_low.shift(1).rolling(3).min()
full['C']=np.where(last_close>(max3+min3)/2,1,-1)
full=full.set_index('bar_id')
ROWS=[]; LEDGERS=[]
def stats(pips,dates):
    pips=np.asarray(pips,dtype=float);n=len(pips);tol=1e-7
    w=int(np.sum(pips>tol));l=int(np.sum(pips<-tol))
    eq=np.r_[0.,np.cumsum(pips)]
    d=pd.DataFrame({'date':np.asarray(dates),'pips':pips}).groupby('date').pips.sum()
    positive=pips[pips>tol].sum();negative=-pips[pips<-tol].sum()
    return {'trades':n,'wins':w,'losses':l,'flat':n-w-l,'win_pct':w/n*100 if n else None,
            'pnl_pips':float(pips.sum()),'pnl_usd_001':float(pips.sum()*PIP_VALUE),
            'profit_factor':float(positive/negative) if negative>0 else None,
            'max_dd_pips':float(np.max(np.maximum.accumulate(eq)-eq)),
            'max_dd_usd_001':float(np.max(np.maximum.accumulate(eq)-eq)*PIP_VALUE),
            'avg_pips':float(np.mean(pips)) if n else None,
            'profitable_days':int((d>tol).sum()),'loss_days':int((d<-tol).sum()),'flat_days':int((d.abs()<=tol).sum())}
for mon in MONTHS:
    g=raw_groups[mon];starts,ends,keys=g['starts'],g['ends'],g['keys']
    bid,ask,tns=g['bid'],g['ask'],g['tns']
    nd=len(bid);boundary=ends-1
    dates=pd.to_datetime(keys*900,unit='s',utc=True).strftime('%Y-%m-%d').to_numpy()
    q=full.reindex(keys)
    assert not q.B.isna().any()
    for method in ['B','C','always_SHORT']:
        side=np.full(len(keys),-1,dtype='int8') if method=='always_SHORT' else q[method].to_numpy(dtype='int8')
        longs=int((side==1).sum());shorts=int((side==-1).sum())
        entry=np.where(side==1,ask[starts],bid[starts])
        spr=(ask[starts]-bid[starts])*10000
        tr_side=np.repeat(side,ends-starts);tr_entry=np.repeat(entry,ends-starts)
        curve=np.where(tr_side==1,(bid-tr_entry)*10000,(tr_entry-ask)*10000)
        eoc=curve[boundary]
        ix=np.arange(nd,dtype=np.int32);sentinel=nd+1;tol=1e-7
        first_stop={s:np.minimum.reduceat(np.where(curve<=-s+tol,ix,sentinel),starts) for s in SLS}
        first_take={t:np.minimum.reduceat(np.where(curve>=t-tol,ix,sentinel),starts) for t in TPS}
        for sl,tp in CONFIGS:
            slix=first_stop[sl];tpix=first_take[tp]
            is_tp=(tpix<slix)&(tpix<=boundary)
            is_sl=(slix<tpix)&(slix<=boundary)
            is_eoc=~(is_tp|is_sl)
            slpx=curve[np.minimum(slix,nd-1)]
            pnl=np.where(is_tp,float(tp),np.where(is_sl,slpx,eoc))
            row=stats(pnl,dates)
            row.update({'method':method,'month':mon,'sl':sl,'tp':tp,'longs':longs,'shorts':shorts,
                'touch_tp':int(is_tp.sum()),'touch_sl':int(is_sl.sum()),'close_eoc':int(is_eoc.sum()),
                'entry_spread_ge_sl':int((spr>=sl).sum()),
                'sl_gap_overshoot_max_pips':float(np.maximum(0,-pnl[is_sl]-sl).max()) if is_sl.any() else 0.,
                'extra_0p3_pips_total':float(pnl.sum()-0.3*len(keys)),
                'extra_0p7_pips_total':float(pnl.sum()-0.7*len(keys)),
                'extra_1p0_pips_total':float(pnl.sum()-1.0*len(keys)),
                'extra_2p0_pips_total':float(pnl.sum()-2.0*len(keys))})
            ROWS.append(row)
            if sl==5 and tp==5:
                chosen_ix=np.where(is_tp,tpix,np.where(is_sl,slix,boundary))
                exit_p=np.where(side==1,bid[np.minimum(chosen_ix,nd-1)],ask[np.minimum(chosen_ix,nd-1)])
                exit_p=np.where(is_tp,entry+side*(tp/10000),exit_p)
                LEDGERS.append(pd.DataFrame({'method':method,'month':mon,
                    'entry_tick_utc':pd.to_datetime(tns[starts],utc=True),
                    'bar_start_utc':pd.to_datetime(keys*900,unit='s',utc=True),
                    'side':np.where(side==1,'LONG','SHORT'),'entry_price':entry,
                    'entry_spread_pips':spr,'exit_quote_time_utc':pd.to_datetime(tns[np.minimum(chosen_ix,nd-1)],utc=True),
                    'exit_price':exit_p,'exit_reason':np.where(is_tp,'TP',np.where(is_sl,'SL','EOC')),
                    'pnl_pips':pnl,'pnl_usd_001':pnl*PIP_VALUE}))
        print('EVALUATED',mon,method,'LONG',longs,'SHORT',shorts,'CONFIGS',len(CONFIGS),flush=True)
res=pd.DataFrame(ROWS)
ledger=pd.concat(LEDGERS,ignore_index=True)
res.to_csv(OUT/'all_configs_monthly.csv',index=False)
ledger.to_csv(OUT/'trades_5_5_all_methods.csv',index=False)
comb=[];selected=[]
for method in ['B','C','always_SHORT']:
    for sl,tp in CONFIGS:
        a=res[(res.method==method)&(res.sl==sl)&(res.tp==tp)].set_index('month').loc[MONTHS]
        comb.append({'method':method,'sl':sl,'tp':tp,
            'aug_pips':float(a.loc['2026-08','pnl_pips']),'sep_pips':float(a.loc['2026-09','pnl_pips']),
            'oct_oos_pips':float(a.loc['2026-10','pnl_pips']),
            'train_aug_sep_pips':float(a.loc[['2026-08','2026-09'],'pnl_pips'].sum()),
            'total_pips':float(a.pnl_pips.sum()),'positive_months':int((a.pnl_pips>0).sum()),
            'all_3_months_positive':bool((a.pnl_pips>0).all()),
            'aug_sep_both_positive':bool((a.loc[['2026-08','2026-09'],'pnl_pips']>0).all()),
            'oct_oos_plus_0p3':float(a.loc['2026-10','extra_0p3_pips_total']),
            'oct_oos_plus_0p7':float(a.loc['2026-10','extra_0p7_pips_total']),
            'oct_oos_plus_1p0':float(a.loc['2026-10','extra_1p0_pips_total'])})
    f=pd.DataFrame([c for c in comb if c['method']==method])
    selected.append(f.sort_values(['train_aug_sep_pips','tp','sl'],ascending=[False,True,True]).iloc[0].to_dict())
grid=pd.DataFrame(comb);grid.to_csv(OUT/'config_grid_train_oos.csv',index=False)
pd.DataFrame(selected).to_csv(OUT/'selected_by_aug_sep_only.csv',index=False)
totals=[]
for method in ['B','C','always_SHORT']:
    sub=ledger[ledger.method==method].sort_values('entry_tick_utc')
    row=stats(sub.pnl_pips.to_numpy(),sub.bar_start_utc.dt.strftime('%Y-%m-%d').to_numpy())
    row.update({'method':method,'sl':5,'tp':5,'longs':int((sub.side=='LONG').sum()),
                'shorts':int((sub.side=='SHORT').sum()),'touch_tp':int((sub.exit_reason=='TP').sum()),
                'touch_sl':int((sub.exit_reason=='SL').sum()),'close_eoc':int((sub.exit_reason=='EOC').sum())})
    totals.append(row)
report={'price_source':'Exness public tick archive Bid/Ask','archive_meta':meta,'pip_value_usd_001':0.1,
        'signal_history':'GitHub V17 M15 prior to August; August-October signals built directly from tick highs/lows/last bid',
        'execution_model':'at first tick of each bar: actual bid or ask; tick-by-tick TP limit; stop filled at first observed crossed quote; EOC approximated by last tick in the M15 bar',
        'limitation':'EOC last tick known only historically, cannot guarantee live execution at that quote; commission/slippage zero in base, no swap, stop levels/rejections not modeled',
        'adverse_cost_scenarios':'0.3/0.7/1.0/2.0 additional pips per trade after spread, approximated after exit',
        'base_5_5_monthly':res[(res.sl==5)&(res.tp==5)].to_dict(orient='records'),
        'base_5_5_total':totals,'selected_by_aug_sep_only':selected,'configs_per_method':len(CONFIGS),
        'positive_all_three_method_config_count':int(grid.all_3_months_positive.sum()),
        'raw_github_m15_sha256':hashlib.sha256(r.content).hexdigest() if False else None}
(OUT/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str))
print('REPORT_SUMMARY',json.dumps({'base_5_5_monthly':report['base_5_5_monthly'],
    'base_5_5_total':report['base_5_5_total'],
    'selected_by_aug_sep_only':selected,
    'positive_all_three_method_config_count':report['positive_all_three_method_config_count']},ensure_ascii=False,default=str),flush=True)
print('FILES',[(x.name,x.stat().st_size) for x in OUT.iterdir()],flush=True)
