#!/usr/bin/env python3
"""V20-FROZEN-1.0: independent, offline-capable Exness EURUSDm tick research.
NO LIVE TRADING. Requires all completed monthly archives 2025-01..2026-10.
The frozen spec's SHA-256 is verified BEFORE any historical ticks are parsed.
"""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, io, json, math, random, statistics, sys, urllib.request, zipfile
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

SPEC_SHA256 = '61b8ec773a1370dec62d3467d4bd19ffd63643ccf21f608035b10abcaadeae60'
PIP = 0.0001
UNITS = 1000.0  # EURUSD: 0.01 standard lot, 100,000 EUR per 1 lot
USD_PER_PIP = 0.10
BASE = Path(__file__).resolve().parent


def msstamp(raw: str) -> int:
    date = dt.datetime.fromisoformat(raw.strip().replace('Z', '+00:00'))
    if date.tzinfo is None: raise ValueError('timestamp without UTC timezone')
    return int(round(date.timestamp() * 1000))


def month_range(start='2025-01', through='2026-10'):
    yr, mo = map(int, start.split('-'))
    endyr, endmo = map(int, through.split('-'))
    while (yr, mo) <= (endyr, endmo):
        yield f'{yr:04d}-{mo:02d}'
        mo += 1
        if mo > 12: yr, mo = yr + 1, 1


def following_month(x):
    y, m = map(int, x.split('-'))
    return f'{y + (m==12):04d}-{(m%12)+1:02d}'


def prior_months(x, n):
    y, m = map(int, x.split('-'))
    total = y * 12 + m - 1
    return [f'{(total-i)//12:04d}-{(total-i)%12+1:02d}' for i in range(n, 0, -1)]


def name_of_archive(month, symbol='EURUSDm'):
    y, m = month.split('-')
    return f'Exness_{symbol}_{y}_{m}.zip'


def ensure_archives(folder: Path, do_download=False):
    folder.mkdir(parents=True, exist_ok=True)
    mandatory = list(month_range())
    missing = []
    downloaded = []
    for month in mandatory + ['2026-11']:
        path = folder / name_of_archive(month)
        if not path.is_file() and do_download:
            y, m = month.split('-')
            url = f'https://ticks.ex2archive.com/ticks/EURUSDm/{y}/{m}/Exness_EURUSDm_{y}_{m}.zip'
            try:
                with urllib.request.urlopen(url, timeout=50) as response, open(str(path)+'.partial', 'wb') as dest:
                    while block := response.read(1 << 20): dest.write(block)
                Path(str(path)+'.partial').replace(path)
                downloaded.append(month)
            except Exception as exc:
                Path(str(path)+'.partial').unlink(missing_ok=True)
                if month != '2026-11': missing.append({'month': month, 'url': url, 'error': str(exc)[:250]})
                continue
        if not path.is_file():
            if month != '2026-11' and not do_download:
                missing.append({'month': month, 'file': str(path), 'error': 'not available'})
            continue
        if not zipfile.is_zipfile(path):
            if month != '2026-11': missing.append({'month': month, 'file': str(path), 'error': 'not a ZIP'})
    return missing, downloaded


def iter_quotes(folder: Path, manifest):
    end_partial = msstamp('2026-11-13T00:00:00Z')
    for month in list(month_range()) + ['2026-11']:
        path = folder / name_of_archive(month)
        if not path.is_file(): continue
        rowcount, errors, prior, duplicate = 0, 0, -1, 0
        first, last, last_bid_ask, subsecond = None, None, None, 0
        with zipfile.ZipFile(path) as z:
            members = [x for x in z.namelist() if x.lower().endswith('.csv')]
            if not members: raise ValueError(f'ZIP {path} has no CSV member')
            for member in members:
                with z.open(member) as raw:
                    reader = csv.DictReader(io.TextIOWrapper(raw, encoding='utf-8-sig', errors='strict'))
                    if not {'Timestamp','Bid','Ask'}.issubset(set(reader.fieldnames or [])):
                        raise ValueError(f'{path}: Missing Timestamp/Bid/Ask')
                    for row in reader:
                        try:
                            t = msstamp(row['Timestamp'])
                            bid = float(row['Bid']); ask = float(row['Ask'])
                            if not (0 < bid <= ask < 10) or not (math.isfinite(bid) and math.isfinite(ask)):
                                raise ValueError('Invalid bid/ask')
                            if t < prior: raise ValueError('Out-of-order ticks')
                            if t == prior and last_bid_ask == (bid,ask):
                                duplicate += 1
                                continue
                            if month == '2026-11' and t >= end_partial: continue
                            # Keep source month honest. No silent inclusion of wrong-month rows.
                            if dt.datetime.fromtimestamp(t/1000, dt.timezone.utc).strftime('%Y-%m') != month:
                                raise ValueError('Tick outside archive month')
                        except Exception as exc:
                            errors += 1
                            if errors > 10: raise ValueError(f'{path}: More than 10 invalid rows, latest={exc}')
                            continue
                        first = first if first is not None else t
                        last = t; prior = t; last_bid_ask=(bid,ask); rowcount += 1
                        if t%1000:subsecond+=1
                        yield t, bid, ask
        manifest[month] = {'file':path.name,'file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                           'ticks':rowcount,'duplicate_timestamps_skipped':duplicate,
                           'invalid_rows':errors,'first_ms':first,'last_ms':last,
                           'subsecond_timestamp_ratio':round(subsecond/rowcount,6) if rowcount else None,
                           'timestamp_has_ms_resolution':subsecond>0}
        if rowcount < 1000 and month != '2026-11': raise ValueError(f'Exness source month {month} has just {rowcount} quotes')


@dataclass
class Bar:
    frame: int
    begin: int
    op: float
    hi: float
    lo: float
    cl: float
    ema9: float = math.nan
    ema21: float = math.nan
    atr: float = math.nan


class Bars:
    def __init__(self, frame):
        self.frame=frame
        self.current=None
        self.history=deque(maxlen=64)
        self.tr=deque(maxlen=14)

    def next_tick(self,t,mid):
        key=t//(self.frame*60_000)*(self.frame*60_000)
        if self.current is None:
            self.current=Bar(self.frame,key,mid,mid,mid,mid)
            return None
        if self.current.begin==key:
            b=self.current
            b.hi=max(b.hi,mid); b.lo=min(b.lo,mid); b.cl=mid
            return None
        old=self.current
        self.current=Bar(self.frame,key,mid,mid,mid,mid)
        if key-old.begin != self.frame*60_000:
            self.history.clear(); self.tr.clear()  # never span a missing bar/weekend
        prev=self.history[-1] if self.history else None
        tr=max(old.hi-old.lo, abs(old.hi-prev.cl),abs(old.lo-prev.cl)) if prev else old.hi-old.lo
        self.tr.append(tr)
        old.ema9=(2/10)*old.cl+(8/10)*prev.ema9 if prev else old.cl
        old.ema21=(2/22)*old.cl+(20/22)*prev.ema21 if prev else old.cl
        if len(self.tr)==14: old.atr=sum(self.tr)/14
        self.history.append(old)
        return (old.begin+self.frame*60_000, old)

    def signal(self, strategy):
        a=list(self.history)
        if len(a)<22 or not math.isfinite(a[-1].atr): return 0
        s=a[-1]; prev=a[-2]
        if s.hi<=s.lo: return 0
        location=(s.cl-s.lo)/(s.hi-s.lo)
        if strategy=='S1':
            b=a[-3:]; total=sum(abs(c.cl-c.op) for c in b)
            pressure=sum(c.cl-c.op for c in b)/total if total > 1e-12 else 0
            body=abs(s.cl-s.op)/(s.hi-s.lo)
            return (1 if pressure>=0.65 and body>=0.55 and location>=0.70
                    else -1 if pressure<=-0.65 and body>=0.55 and location<=0.30 else 0)
        if strategy=='S2':
            upper=max(c.hi for c in a[-13:-1]); lower=min(c.lo for c in a[-13:-1])
            return (1 if s.cl>upper+0.15*s.atr and s.op<=upper and location>=0.70
                    else -1 if s.cl<lower-0.15*s.atr and s.op>=lower and location<=0.30 else 0)
        if strategy=='S3':
            old=a[-4]
            return (1 if s.ema9>s.ema21 and s.ema9>old.ema9 and prev.lo<=prev.ema9
                    and prev.cl>prev.ema21 and s.cl>prev.hi and s.cl>s.ema9
                    else -1 if s.ema9<s.ema21 and s.ema9<old.ema9 and prev.hi>=prev.ema9
                    and prev.cl<prev.ema21 and s.cl<prev.lo and s.cl<s.ema9 else 0)
        raise KeyError(strategy)


@dataclass(frozen=True)
class Scenario:
    label: str
    spread: float
    slip: float
    latency: int

SCENARIOS=[Scenario('base_2ms',1,0.1,2),Scenario('latency_100ms',1,0.1,100),
           Scenario('latency_300ms',1,0.1,300),Scenario('stress_1p5x',1.5,0.2,2),
           Scenario('stress_2x',2,0.3,2),Scenario('worst_300ms_2x',2,0.3,300)]


class Engine:
    def __init__(self, key, strategy, frame, stop_k, rr, scenario):
        self.key=key;self.strategy=strategy;self.frame=frame;self.stop_k=stop_k
        self.rr=rr;self.scenario=scenario
        self.cash=100.0; self.peak=100.0; self.max_dd=0.0
        self.enabled=True  # OOS portfolio engines are disabled until a frozen WF selection
        self.entry_pending=None; self.pos=None; self.trades=[];self.stats=defaultdict(int)

    def mark(self,bid,ask):
        equity=self.cash
        if self.pos:
            p=self.pos
            delta=(bid-p['price'] if p['side']==1 else p['price']-ask)*UNITS
            equity+=delta
            p['path_min']=min(p['path_min'],delta)
            p['path_max']=max(p['path_max'],delta)
            p['path_peak']=max(p['path_peak'],delta)
            p['path_max_dd']=max(p['path_max_dd'],p['path_peak']-delta)
        self.peak=max(self.peak,equity)
        self.max_dd=max(self.max_dd,self.peak-equity)
        return equity

    def propose(self,side,close_time,atr,signal_spread):
        if not self.enabled or side==0 or self.pos or self.entry_pending: return
        h=dt.datetime.fromtimestamp(close_time/1000,dt.timezone.utc).hour
        if not 7<=h<16: return
        atrpip=atr/PIP
        if atrpip < (0.4 if self.frame==1 else 0.7): return
        if signal_spread > 0.4*atrpip:
            self.stats['signal_spread_rejected']+=1;return
        self.entry_pending={'t':close_time,'side':side,'atr':atrpip}

    def tick(self,t,orig_bid,orig_ask):
        sc=self.scenario
        mid=(orig_bid+orig_ask)/2
        half=(orig_ask-orig_bid)*sc.spread/2
        bid=mid-half;ask=mid+half
        spread=(ask-bid)/PIP
        eq=self.mark(bid,ask)
        p=self.pos
        if p:
            if 'close_due' in p:
                if t>=p['close_due']:
                    x=(bid-sc.slip*PIP) if p['side']==1 else (ask+sc.slip*PIP)
                    pnl=(x-p['price'])*UNITS*p['side']-2*(0.0/100.0) # commission Standard=0
                    held_days=dt.datetime.fromtimestamp(t/1000,dt.timezone.utc).date()!=dt.datetime.fromtimestamp(p['opened']/1000,dt.timezone.utc).date()
                    if held_days: self.stats['unexpected_overnight']+=1
                    p['path_min']=min(p['path_min'],pnl)
                    p['path_max']=max(p['path_max'],pnl)
                    p['path_max_dd']=max(p['path_max_dd'],p['path_peak']-pnl)
                    self.cash+=pnl
                    self.trades.append({'key':self.key,'scenario':sc.label,'entry_ms':p['opened'],'exit_ms':t,
                        'month':dt.datetime.fromtimestamp(t/1000,dt.timezone.utc).strftime('%Y-%m'),
                        'day':dt.datetime.fromtimestamp(t/1000,dt.timezone.utc).strftime('%Y-%m-%d'),
                        'side':p['side'],'entry':p['price'],'exit':x,'stop_pips':p['stop_pips'],
                        'target_pips':p['target_pips'],'spread_at_entry_pips':p['spread'],
                        'pnl_usd':pnl,'commission_usd':0.0,'swap_usd':0.0,
                        'valid_same_day':not held_days,'reason':p['reason'],
                        'path_min_usd':p['path_min'],'path_max_usd':p['path_max'],
                        'path_max_dd_usd':p['path_max_dd']})
                    self.pos=None;self.mark(bid,ask)
                return
            when=dt.datetime.fromtimestamp(t/1000,dt.timezone.utc)
            force=(when.hour>=17)
            hold=t>=p['opened'] + p['max_minutes']*60000
            if p['side']==1:
                stop=bid<=p['price']-p['stop_pips']*PIP
                target=bid>=p['price']+p['target_pips']*PIP
            else:
                stop=ask>=p['price']+p['stop_pips']*PIP
                target=ask<=p['price']-p['target_pips']*PIP
            if stop or target or hold or force or eq<=0:
                p['reason']='SL' if stop or eq<=0 else 'TP' if target else 'TIME' if hold else 'FLAT'
                p['close_due']=t+sc.latency
            return
        o=self.entry_pending
        if not o: return
        if t<o['t']+sc.latency: return
        if t>o['t']+2000:
            self.stats['late_entry_rejected']+=1;self.entry_pending=None;return
        if dt.datetime.fromtimestamp(t/1000,dt.timezone.utc).hour>=16:
            self.entry_pending=None;return
        if spread>0.4*o['atr']:
            self.stats['entry_spread_rejected']+=1;self.entry_pending=None;return
        stop=max(self.stop_k*o['atr'],2.5*spread,0.8)
        target=max(self.rr*stop,4*(spread+2*sc.slip))
        if spread>0.30*target:
            self.stats['cost_ratio_rejected']+=1;self.entry_pending=None;return
        if (stop+2*sc.slip+spread)*USD_PER_PIP >0.02*self.cash:
            self.stats['risk_rejected']+=1;self.entry_pending=None;return
        side=o['side']
        price=(ask+sc.slip*PIP) if side==1 else (bid-sc.slip*PIP)
        margin=UNITS*price/200
        if self.cash-(spread+sc.slip)*USD_PER_PIP<margin or self.cash <= 0:
            self.stats['margin_rejected']+=1;self.entry_pending=None;return
        holds={'S1':{1:5,5:3},'S2':{1:8,5:4},'S3':{1:10,5:5}}
        self.pos={'opened':t,'side':side,'price':price,'stop_pips':stop,'target_pips':target,
                  'spread':spread,'max_minutes':self.frame*holds[self.strategy][self.frame],
                  'path_min':0.0,'path_max':0.0,'path_peak':0.0,'path_max_dd':0.0}
        self.entry_pending=None
        self.mark(bid,ask)


def run_engines(folder):
    frames={1:Bars(1),5:Bars(5)}
    candidate_engines=[]
    for s in ['S1','S2','S3']:
        for frame in [1,5]:
            for stop_k in [1.2,1.8]:
                for rr in [1.5,2.2]:
                    key=f'{s}_M{frame}_SL{stop_k}_RR{rr}'
                    for sc in SCENARIOS:
                        candidate_engines.append(Engine(key,s,frame,stop_k,rr,sc))
    idx={(e.key,e.scenario.label):e for e in candidate_engines}
    portfolios=[]
    for s in ['S1','S2','S3']:
        for frame in [1,5]:
            for sc in SCENARIOS:
                e=Engine(f'{s}_M{frame}',s,frame,1.2,1.5,sc)
                e.enabled=False
                portfolios.append(e)
    by_frame=defaultdict(list)
    for e in candidate_engines+portfolios:by_frame[e.frame].append(e)
    all_engines=candidate_engines+portfolios
    selections={};fold_rows=[]
    manifest={};prior=-1;count=0;month_seen=None
    for t,bid,ask in iter_quotes(folder,manifest):
        if t<prior:raise ValueError('Archive timestamps not globally ordered')
        prior=t;count+=1
        month=dt.datetime.fromtimestamp(t/1000,dt.timezone.utc).strftime('%Y-%m')
        if month!=month_seen:
            month_seen=month
            # Selection happens at first quote of month, using ONLY 6 past complete months.
            if '2025-07'<=month<='2026-11':
                train=set(prior_months(month,6))
                for s in ['S1','S2','S3']:
                    for frame in [1,5]:
                        sf=f'{s}_M{frame}'
                        options=[]
                        for sl in [1.2,1.8]:
                            for rr in [1.5,2.2]:
                                key=f'{sf}_SL{sl}_RR{rr}'
                                en=idx[(key,'base_2ms')]
                                t_train=[x for x in en.trades if x['month'] in train and x['valid_same_day']]
                                m=metrics(t_train)
                                if m['trades']>=30 and m['pf'] is not None and m['pf']>1 and m['expectancy_usd']>0:
                                    options.append((m['expectancy_usd'],m['pf'],key,sl,rr))
                        choice=max(options) if options else None
                        selections[(sf,month)]=choice[2] if choice else None
                        fold_rows.append({'family_frame':sf,'month':month,'selected_grid':choice[2] if choice else 'NO_TRADE',
                                          'train_expectancy_usd':choice[0] if choice else None,
                                          'train_pf':choice[1] if choice else None})
                        for e in portfolios:
                            if e.key==sf:
                                if e.pos or e.entry_pending:raise ValueError('Cross-month open order detected')
                                e.enabled=bool(choice)
                                if choice:e.stop_k,e.rr=choice[3],choice[4]
            else:
                for e in portfolios:e.enabled=False
        mid=(bid+ask)/2
        for frame,bars in frames.items():
            ev=bars.next_tick(t,mid)
            if ev:
                end,_=ev
                for strategy in ['S1','S2','S3']:
                    direction=bars.signal(strategy)
                    if direction:
                        # First observed quote on new bar is the earliest quoted spread at decision.
                        signal_spread=(ask-bid)/PIP
                        for e in by_frame[frame]:
                            if e.strategy==strategy:
                                e.propose(direction,end,bars.history[-1].atr,signal_spread*e.scenario.spread)
        for e in all_engines:
            if e.pos or e.entry_pending:e.tick(t,bid,ask)
        if count%10_000_000==0:print(f'Processed {count:,} genuine Exness quotes',file=sys.stderr,flush=True)
    if count<1000:raise ValueError('No tick data')
    for e in all_engines:
        if e.pos:e.stats['uncleared_position_at_end']+=1
    return candidate_engines,portfolios,manifest,count,selections,fold_rows


def metrics(trades):
    vals=[float(t['pnl_usd']) for t in trades if t['valid_same_day']]
    if not vals: return {'trades':0,'net_usd':0,'win_rate':None,'pf':None,'expectancy_usd':None,'max_consecutive_losses':0}
    profit=sum(max(0,x) for x in vals);loss=-sum(min(0,x) for x in vals)
    consec=longest=0
    for x in vals:
        consec=consec+1 if x<0 else 0;longest=max(longest,consec)
    return {'trades':len(vals),'net_usd':round(sum(vals),6),
        'win_rate':round(sum(x>0 for x in vals)/len(vals),6),
        'pf':round(profit/loss,6) if loss else None,
        'expectancy_usd':round(statistics.mean(vals),6),
        'max_consecutive_losses':longest}


def boot_ci(trades, rounds=2000):
    # Resample calendar-day clusters, preserving within-day trade correlation.
    days=defaultdict(list)
    for tr in trades:
        if tr['valid_same_day']:days[tr['day']].append(float(tr['pnl_usd']))
    if len(days)<15:return None
    blocks=[(sum(v),len(v)) for v in days.values()];rnd=random.Random(200613)
    values=[]
    for _ in range(rounds):
        sample=[blocks[rnd.randrange(len(blocks))] for _ in blocks]
        count=sum(k for _,k in sample)
        values.append(sum(s for s,_ in sample)/count if count else 0)
    values.sort()
    return values[int(0.025*len(values))]


def equity_max_drawdown_from_path(trades, initial_cash=100.0):
    """Exact max peak-to-trough DD under sequential, non-overlapping trade MTM paths.
    Each trade stores its own ordered-path max DD plus its path-wide min/max.
    """
    cash=peak=initial_cash
    max_dd=0.0
    for t in sorted(trades,key=lambda x:x['entry_ms']):
        if not t['valid_same_day']:continue
        max_dd=max(max_dd,peak-(cash+float(t['path_min_usd'])),float(t['path_max_dd_usd']))
        peak=max(peak,cash+float(t['path_max_usd']))
        cash+=float(t['pnl_usd'])
        max_dd=max(max_dd,peak-cash)
        peak=max(peak,cash)
    return round(max_dd,6)


def evaluate(portfolios,selections,nov_available=False):
    sf_names=sorted(set(e.key for e in portfolios))
    pi={(e.key,e.scenario.label):e for e in portfolios}
    oos=list(month_range('2025-07','2026-10'))
    results={};monthly=[];nov_preview={}
    for sf in sf_names:
        scenarios={}
        for sc in SCENARIOS:
            e=pi[(sf,sc.label)]
            for month in oos:
                t_month=[t for t in e.trades if t['month']==month]
                monthly.append({'family_frame':sf,'scenario':sc.label,'month':month,
                    'selected_grid':selections[(sf,month)] or 'NO_TRADE',
                    **metrics(t_month)})
            if nov_available:
                nov=[t for t in e.trades if t['month']=='2026-11']
                nov_preview.setdefault(sf,{})[sc.label]=metrics(nov)
            t_all=[t for t in e.trades if t['month'] in oos]
            result=metrics(t_all)
            result['max_equity_dd_usd']=equity_max_drawdown_from_path(t_all)
            result['boot_95_lower_mean_usd']=boot_ci(t_all)
            positives=sum(metrics([t for t in t_all if t['month']==m])['net_usd']>0 for m in oos)
            result['positive_months']=positives
            result['months_total']=len(oos)
            result['profit_2025_usd']=metrics([t for t in t_all if t['month'].startswith('2025')])['net_usd']
            result['profit_2026_usd']=metrics([t for t in t_all if t['month'].startswith('2026')])['net_usd']
            result['invalid_overnight_trades']=sum(not t['valid_same_day'] for t in t_all)
            result['unclosed_position_flags']=e.stats.get('uncleared_position_at_end',0)
            scenarios[sc.label]=result
        b=scenarios['base_2ms']
        passed=(b['trades']>=200 and b['net_usd']>0 and b['pf'] is not None and b['pf']>=1.15
            and b['profit_2025_usd']>0 and b['profit_2026_usd']>0
            and b['positive_months']>=math.ceil(.6*b['months_total'])
            and b['boot_95_lower_mean_usd'] is not None and b['boot_95_lower_mean_usd']>0
            and b['invalid_overnight_trades']==0 and b['unclosed_position_flags']==0
            and all(scenarios[x]['net_usd']>0 for x in ['stress_1p5x','stress_2x','latency_300ms','worst_300ms_2x']))
        results[sf]={'pass':passed,'scenarios':scenarios}
    eligible=[(v['scenarios']['worst_300ms_2x']['net_usd'],k) for k,v in results.items() if v['pass']]
    picked=max(eligible)[1] if eligible else None
    return {'decision':'ONE_CANDIDATE' if picked else 'NO_EDGE','selected':picked,
        'walk_forward_results':results,'nov_2026_partial_preview_not_for_selection':nov_preview},monthly


def writecsv(out, filename,rows):
    if not rows:return
    headers=list(rows[0])
    with (out/filename).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=headers,extrasaction='ignore');w.writeheader();w.writerows(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',default=str(BASE/'data'))
    p.add_argument('--out',default=str(BASE/'results'))
    p.add_argument('--download',action='store_true',help='Try to obtain official Exness monthly ZIP archives')
    args=p.parse_args()
    specfile=BASE/'frozen_rules_v1.json'
    sha=hashlib.sha256(specfile.read_bytes()).hexdigest()
    if sha!=SPEC_SHA256:raise ValueError('FROZEN RULES SHA256 MISMATCH. Refusing backtest.')
    spec=json.loads(specfile.read_text())
    assert spec['version']=='V20-FROZEN-1.0' and spec['instrument']=='EURUSDm'
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    missing,downloaded=ensure_archives(Path(args.data_dir),args.download)
    if missing:
        result={'status':'DATA_UNAVAILABLE','frozen_sha256':sha,'missing_months_count':len(missing),
                'missing':missing,'downloaded_months':downloaded,
                'official_data_analysed':False,'metrics':'NOT_COMPUTED',
                'note':'No performance results are produced when completed source archives are missing.'}
        (out/'status.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
        print(json.dumps(result,indent=2,ensure_ascii=False));return 2
    try:
        candidates,portfolios,manifest,count,selections,fold_rows=run_engines(Path(args.data_dir))
        # Mandatory integrity; any invalid archive or abnormal processing makes results invalid.
        if any(manifest[m]['invalid_rows'] for m in month_range()):
            raise ValueError('Invalid input rows in mandatory archives')
        if any(not manifest[m]['timestamp_has_ms_resolution'] for m in month_range()):
            raise ValueError('Sub-second timestamps missing; cannot compare 2/100/300ms')
        report,monthly=evaluate(portfolios,selections,nov_available=('2026-11' in manifest))
        report.update({'status':'COMPUTED','ticks':count,'frozen_sha256':sha,'data_manifest':manifest,
                       'nov2026_data_status':'PARTIAL' if '2026-11' in manifest else 'DATA_UNAVAILABLE',
                       'important_limitations':['Indicative quote data, NOT historical deal executions',
                       'Quote-time latency is a counterfactual next-tick model, NOT observed broker execution speed',
                       'HMR and actual MT5 stop-level restrictions require account-side verification',
                       'Risk calculations assume exact broker contract/commission agreement']})
        (out/'summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
        (out/'data_manifest.json').write_text(json.dumps(manifest,indent=2))
        writecsv(out,'oos_monthly.csv',monthly)
        writecsv(out,'fold_selections.csv',fold_rows)
        train_rows=[]
        for e in candidates:
            if e.scenario.label!='base_2ms':continue
            for month in month_range('2025-01','2025-06'):
                train_rows.append({'candidate':e.key,'month':month,
                    **metrics([t for t in e.trades if t['month']==month])})
        writecsv(out,'training_candidates_monthly.csv',train_rows)
        trade_rows=[]
        for e in candidates+portfolios:
            trade_rows += e.trades
        writecsv(out,'all_candidate_trades.csv',trade_rows)
        print(json.dumps({'status':report['status'],'ticks':count,'decision':report['decision'],
            'selected':report['selected']},indent=2));return 0
    except Exception as exc:
        result={'status':'VALIDATION_ERROR','error':str(exc),'frozen_sha256':sha,'metrics':'NOT_COMPUTED'}
        (out/'status.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2),file=sys.stderr);return 3

if __name__=='__main__':sys.exit(main())