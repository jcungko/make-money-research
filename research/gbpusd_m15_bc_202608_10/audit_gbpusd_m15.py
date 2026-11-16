
# Independent data and chronology reconciliation.
import io,zipfile,pandas as pd,numpy as np,json
with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    gh=pd.read_csv(z.open('GBPUSD_M15_2026_UTC.csv'),parse_dates=['timestamp_utc'])
gh=gh[(gh.timestamp_utc>=pd.Timestamp('2026-08-01',tz='UTC'))&(gh.timestamp_utc<pd.Timestamp('2026-11-01',tz='UTC'))]
merged=raw_agg.merge(gh,on='timestamp_utc',suffixes=('_tick','_github'),how='outer',indicator=True)
out={'tick_bars':len(raw_agg),'stored_m15_bars':len(gh),'matched':int((merged._merge=='both').sum()),'only_tick':int((merged._merge=='left_only').sum()),'only_github':int((merged._merge=='right_only').sum())}
for f in ['bid_open','bid_high','bid_low','bid_close']:
    d=(merged[f+'_tick']-merged[f+'_github']).abs()
    out[f+'_unequal_ge_0p1pip']=int((d>=0.00001-1e-9).sum())
    out[f+'_unequal_gt_0p000001']=int((d>0.000001).sum())
    out[f+'_max_delta_pips']=float(d.max()*10000)
# audit chronologically no position carries between candles
for method in ['B','C','always_SHORT']:
    sub=ledger[ledger.method==method].sort_values('entry_tick_utc')
    duration=(sub.exit_quote_time_utc-sub.entry_tick_utc).dt.total_seconds().to_numpy()
    next_entry=sub.entry_tick_utc.shift(-1)
    out[f'{method}_exit_after_next_entry_count']=int((sub.exit_quote_time_utc>next_entry).sum())
    out[f'{method}_max_position_seconds']=float(duration.max())
    out[f'{method}_negative_position_duration_count']=int((duration<0).sum())
(OUT/'audit.json').write_text(json.dumps(out,indent=2))
print('AUDIT',json.dumps(out,ensure_ascii=False),flush=True)
