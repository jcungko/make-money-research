#!/usr/bin/env python3
"""V22 sequential bottom-half filtering of the October-2026-positive universe.

Step 1: remove the 50% with smallest 22-month modeled total_bps.
Step 2: of survivors, remove the 50% with smallest number of individual EA
orders (sum across all constituent strategies). Stable ID is tie-break.
The underlying 2,728 candidates are replayed exactly; no fresh optimisation.
"""
import argparse, csv, json, tempfile
from pathlib import Path
from datetime import datetime, timezone
import v22_oct2026_filter as octfilter

_original_row=octfilter.row

def row_with_orders(item, category):
    record=_original_row(item,category)
    legs=item.get('components',[item])
    counts=[int(leg['trades']) for leg in legs]
    if len(counts)!=int(record['n_strategies']) or min(counts)<=0:
        raise AssertionError('Missing constituent trade count')
    record['total_orders_2025_2026']=sum(counts)
    record['component_orders']=';'.join(
        f"{leg['symbol']}:{count}" for leg,count in zip(legs,counts)
    )
    return record

def write_csv(path,rows,columns):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns,extrasaction='raise')
        writer.writeheader()
        writer.writerows(rows)

def statistics(rows):
    if not rows:return {'count':0}
    vals=sorted([int(x['total_orders_2025_2026']) for x in rows])
    profits=sorted([float(x['total_bps']) for x in rows])
    return dict(count=len(rows),min_orders=vals[0],median_orders=(vals[(len(vals)-1)//2]+vals[len(vals)//2])/2,
                max_orders=vals[-1],min_total_bps=profits[0],max_total_bps=profits[-1])

def main(root,out):
    out.mkdir(parents=True,exist_ok=True)
    octfilter.row=row_with_orders
    with tempfile.TemporaryDirectory(prefix='v22_seqfilter_') as td:
        tmp=Path(td)
        octfilter.screen(root,tmp)
        with (tmp/'filter_summary.json').open('r') as f: original=json.load(f)
        with (tmp/'kept_not_losing_2026_10.csv').open('r',encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f))

    if original['kept']!=2728 or len(rows)!=2728:
        raise AssertionError(f"Expected 2728 October-positive V22 candidates; got {len(rows)}")
    if len(set(r['id'] for r in rows))!=len(rows): raise AssertionError('Duplicate original ID')
    for r in rows:
        if not float(r['oct_2026_bps'])>0: raise AssertionError('October negative slipped into pool')
        if int(r['total_orders_2025_2026'])<1: raise AssertionError('Bad count')
        if not(float(r['profit_2025_bps'])>0 and float(r['profit_2026_bps'])>0):
            raise AssertionError('Annual profitability lost')

    # Stable ascending order; ties broken with original V22 ID (not arbitrary sort order).
    by_profit=sorted(rows,key=lambda r:(float(r['total_bps']),r['id']))
    n_remove_low_profit=len(rows)//2
    removed_profit=by_profit[:n_remove_low_profit]
    after_profit=by_profit[n_remove_low_profit:]
    assert len(after_profit)==1364

    by_orders=sorted(after_profit,key=lambda r:(int(r['total_orders_2025_2026']),r['id']))
    n_remove_low_orders=len(after_profit)//2
    removed_orders=by_orders[:n_remove_low_orders]
    survivors=by_orders[n_remove_low_orders:]
    assert len(survivors)==682

    survivors.sort(key=lambda r:(-int(r['months_profitable']),-float(r['total_bps']),
                                 -int(r['total_orders_2025_2026']),r['id']))
    fields=['final_id']+list(rows[0])
    for n,r in enumerate(survivors,1):
        r['final_id']=f'V22-F{n:04}'
    for n,r in enumerate(removed_profit,1):
        r['final_id']=f'V22-PDROP{n:04}'
    for n,r in enumerate(removed_orders,1):
        r['final_id']=f'V22-ODROP{n:04}'
    write_csv(out/'v22_final_682_strategies.csv',survivors,fields)
    write_csv(out/'stage1_1364_removed_lowest_profit.csv',removed_profit,fields)
    write_csv(out/'stage2_682_removed_fewest_orders.csv',removed_orders,fields)
    for year in ('2025','2026'):
        if not all(float(x[f'profit_{year}_bps'])>0 for x in survivors):
            raise AssertionError('Annual profit invariant')

    levels=[17,18,19,20,21,22]
    counts_months={str(t):dict(before=sum(int(r['months_profitable'])>=t for r in rows),
        after_profit=sum(int(r['months_profitable'])>=t for r in after_profit),
        final=sum(int(r['months_profitable'])>=t for r in survivors)) for t in levels}
    categories=['single','pair','triple','quad','quint']
    counts_categories={cat:dict(before=sum(r['category']==cat for r in rows),
        after_profit=sum(r['category']==cat for r in after_profit),
        final=sum(r['category']==cat for r in survivors)) for cat in categories}
    top=[{k:r[k] for k in ('final_id','id','category','symbols','months_profitable',
        'total_orders_2025_2026','component_orders','total_bps','oct_2026_bps',
        'profit_2025_bps','profit_2026_bps','losing_months','components')}
        for r in survivors[:25]]
    summary=dict(version='V22-SEQUENTIAL-PROFIT-ORDERS-HALVING',
        rule1='Drop the bottom half (1364/2728) by ascending 22-month modeled total_bps',
        rule2='Drop the bottom half (682/1364) of survivors by ascending sum of constituent EA orders',
        tie_break='Original V22-Knnnn ID ascending',
        portfolio_order_count='Sum of executed backtest trades of independent components; simultaneous orders each count once',
        profit_comparison='Total modeled bps over 22 months using existing portfolio equal-notional average for composites, not dollars',
        note='All simulations in sample and subject to modeled bid/ask spread and slippage; may fail outside sample',
        original_oct_positive=len(rows),removed_low_profit=len(removed_profit),
        after_profit=len(after_profit),removed_few_orders=len(removed_orders),final=len(survivors),
        thresholds=counts_months,types=counts_categories,
        statistics=dict(original=statistics(rows),after_profit=statistics(after_profit),
            final=statistics(survivors),removed_profit=statistics(removed_profit),
            removed_orders=statistics(removed_orders)),
        top25=top,created_at_utc=datetime.now(timezone.utc).isoformat())
    (out/'filter_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('V22_FINAL',json.dumps({k:summary[k] for k in ('original_oct_positive','removed_low_profit',
        'after_profit','removed_few_orders','final','thresholds','types','statistics')},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path('data/v22_exness'))
    p.add_argument('--out',type=Path,default=Path('results/v22_profit_orders_filter'))
    a=p.parse_args()
    main(a.root,a.out)
