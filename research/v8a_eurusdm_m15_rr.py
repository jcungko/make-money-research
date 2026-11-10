#!/usr/bin/env python3
"""V8-A EURUSDm M15 historical locked-box breakout. NO LIVE TRADING."""
import argparse,csv,hashlib,io,json,math,os,re,statistics,zipfile
from collections import Counter
from datetime import datetime,timezone
STEP=900; PIP=.0001; NBOX=20; N=14
RRS=[.5,1,1.5,2,2.5,3,4,5,6]; LOCK=8; HOLD=96
SLIP_ENTRY=.1;SLIP_EXIT=.1;F=.0025

def norm(x): return re.sub('[^a-z0-9]','',x.lower())
def parse_time(s):
 s=s.strip()
 if re.fullmatch(r'\d{10,13}',s): return int(s)//(1000 if len(s)==13 else 1)
 try:d=datetime.fromisoformat(s.replace('Z','+00:00'))
 except ValueError:
  for fmt in ('%Y.%m.%d %H:%M:%S','%Y/%m/%d %H:%M:%S','%Y-%m-%d %H:%M:%S'):
   try:d=datetime.strptime(s,fmt);break
   except ValueError:continue
  else:raise ValueError('Unsupported datetime '+repr(s))
 return int(d.replace(tzinfo=timezone.utc).timestamp() if d.tzinfo is None else d.timestamp())

def data(path):
 with open(path,'rb') as f:print('SHA256',hashlib.file_digest(f,'sha256').hexdigest(),flush=True)
 out={}
 with zipfile.ZipFile(path) as z:
  names=[n for n in z.namelist() if n.lower().endswith('.csv') and 'm15' in n.lower()]
  print('M15_FILES',json.dumps(names),flush=True)
  if not names:raise ValueError('No M15 CSV; ZIP members='+repr(z.namelist()[:50]))
  for filename in names:
   with z.open(filename) as f:
    r=csv.DictReader(io.TextIOWrapper(f,encoding='utf-8-sig',newline=''))
    fields=list(r.fieldnames or [])
    print('CSV_FIELDS',filename,fields,flush=True)
    keys={norm(k):k for k in fields}
    def get(*choices):
     return next((keys[norm(k)] for k in choices if norm(k) in keys),None)
    tkey=get('time_utc','open_time_utc','timestamp_utc','timestamp','datetime_utc','datetime','time','open_time','ts_utc','bar_open_utc') or fields[0]
    nums=[]
    for side in ('bid','ask'):
     for f in ('open','high','low','close'):nums.append(get(side+'_'+f,f+'_'+side,side+f,f+side))
    if not all(nums):raise ValueError('MISSING BID ASK OHLC '+repr(fields))
    for row in r:
     if not row.get(tkey):continue
     ts=parse_time(row[tkey])
     v=tuple(float(row[k]) for k in nums)
     if min(v)<=0 or not all(math.isfinite(x) for x in v):continue
     if ts in out and out[ts]!=v:raise ValueError('Conflicting timestamp '+str(ts))
     out[ts]=v
 b=[(t,*out[t]) for t in sorted(out)]
 print('BARS',len(b),'START',datetime.fromtimestamp(b[0][0],timezone.utc),'END',datetime.fromtimestamp(b[-1][0],timezone.utc),flush=True)
 return b

def features(b):
 n=len(b);tr=[None]*n;pdm=[0.]*n;ndm=[0.]*n;atr=[None]*n;adx=[None]*n;er=[None]*n;dx=[None]*n
 for i in range(1,n):
  if b[i][0]-b[i-1][0]!=STEP:continue
  high,low=b[i][2],b[i][3];h0,l0,c0=b[i-1][2],b[i-1][3],b[i-1][4]
  tr[i]=max(high-low,abs(high-c0),abs(low-c0))
  up=high-h0;down=l0-low
  pdm[i]=up if up>down and up>0 else 0
  ndm[i]=down if down>up and down>0 else 0
 i=1
 while i<n:
  if tr[i] is None:i+=1;continue
  j=i
  while j<n and tr[j] is not None:j+=1
  if j-i>=2*N:
   k=i+N-1;t=sum(tr[i:k+1]);p=sum(pdm[i:k+1]);m=sum(ndm[i:k+1])
   atr[k]=t/N;di=100*p/t if t else 0;ni=100*m/t if t else 0
   dx[k]=100*abs(di-ni)/(di+ni) if di+ni else 0
   for k in range(i+N,j):
    t+=tr[k]-t/N;p+=pdm[k]-p/N;m+=ndm[k]-m/N
    atr[k]=t/N;di=100*p/t if t else 0;ni=100*m/t if t else 0
    dx[k]=100*abs(di-ni)/(di+ni) if di+ni else 0
   seed=i+2*N-2
   if seed<j:
    adx[seed]=sum(dx[i+N-1:seed+1])/N
    for k in range(seed+1,j):adx[k]=(adx[k-1]*(N-1)+dx[k])/N
  i=j+1
 for i in range(20,n):
  if b[i][0]-b[i-20][0]!=20*STEP:continue
  travel=sum(abs(b[k][4]-b[k-1][4]) for k in range(i-19,i+1))
  er[i]=abs(b[i][4]-b[i-20][4])/travel if travel else 0
 return atr,adx,er

def simulate(b,atr,adx,er,rr):
 trades=[];reasons=Counter();box=None;busy=-1;i=40
 while i<len(b)-1:
  if i<=busy:i+=1;continue
  if box is None:
   if adx[i] is not None and atr[i] and er[i] is not None and b[i][0]-b[i-19][0]==19*STEP:
    hi=max(x[2] for x in b[i-19:i+1]);lo=min(x[3] for x in b[i-19:i+1])
    width=(hi-lo)/atr[i]
    if adx[i]<20 and er[i]<.35 and 1.5<=width<=3.5:
     box=(hi,lo,atr[i],i);reasons['boxes']+=1
   i+=1;continue
  hi,lo,a,start=box
  if i-start>LOCK or b[i][0]-b[i-1][0]!=STEP or b[i+1][0]-b[i][0]!=STEP:
   box=None;i+=1;continue
  c=b[i];rng=c[2]-c[3]
  if rng<=0 or abs(c[4]-c[1])/rng<.5:i+=1;continue
  side=1 if c[4]>hi+.15*a else -1 if c[4]<lo-.15*a else 0
  if side==0:i+=1;continue
  e=i+1;entry=b[e][5]+SLIP_ENTRY*PIP if side==1 else b[e][1]-SLIP_ENTRY*PIP
  stop=lo-.1*a if side==1 else hi+.1*a+b[e][5]-b[e][1]
  risk=(entry-stop) if side==1 else (stop-entry)
  if risk<=0 or risk>.01:reasons['bad_risk']+=1;box=None;i+=1;continue
  target=entry+side*rr*risk
  for j in range(e,len(b)):
   x=b[j];timed=x[0]-b[e][0]>=HOLD*STEP
   if side==1:
    if x[1]<=stop or x[3]<=stop:price=min(x[1],stop)-SLIP_EXIT*PIP;reason='SL';break
    if x[1]>=target or x[2]>=target:price=target-SLIP_EXIT*PIP;reason='TP';break
   else:
    if x[5]>=stop or x[7]>=stop:price=max(x[5],stop)+SLIP_EXIT*PIP;reason='SL';break
    if x[5]<=target or x[8]<=target:price=target+SLIP_EXIT*PIP;reason='TP';break
   if timed or j==len(b)-1:
    price=x[4]-SLIP_EXIT*PIP if side==1 else x[8]+SLIP_EXIT*PIP
    reason='TIME' if timed else 'END';break
  net=side*(price-entry)/risk
  trades.append(dict(rr=rr,entry_utc=datetime.fromtimestamp(b[e][0],timezone.utc).isoformat(),
    exit_utc=datetime.fromtimestamp(b[j][0],timezone.utc).isoformat(),side='BUY' if side==1 else 'SELL',
    entry=round(entry,6),stop=round(stop,6),target=round(target,6),exit=round(price,6),
    stop_pips=round(risk/PIP,2),net_R=round(net,6),exit_reason=reason))
  busy=j;box=None;i=j+1
 return trades,dict(reasons)

def metrics(trades):
 n=len(trades);win=sum(t['net_R']>0 for t in trades)
 pos=sum(max(0,t['net_R']) for t in trades);neg=-sum(min(0,t['net_R']) for t in trades)
 eq=1;peak=1;dd=0
 for t in trades:
  eq*=1+F*t['net_R'];peak=max(peak,eq);dd=max(dd,100*(peak-eq)/peak)
 return dict(N=n,win_rate=round(100*win/n,2) if n else None,net_R=round(sum(t['net_R'] for t in trades),3),
    avg_R=round(sum(t['net_R'] for t in trades)/n,4) if n else None,
    profit_factor=round(pos/neg,3) if neg else None,drawdown_pct=round(dd,2),
    compounded_return_pct=round(100*(eq-1),2),
    stop_pips_median=round(statistics.median(t['stop_pips'] for t in trades),2) if n else None,
    TP=sum(t['exit_reason']=='TP' for t in trades),SL=sum(t['exit_reason']=='SL' for t in trades),
    TIME=sum(t['exit_reason']=='TIME' for t in trades),BUY=sum(t['side']=='BUY' for t in trades),SELL=sum(t['side']=='SELL' for t in trades))

def main():
 p=argparse.ArgumentParser();p.add_argument('--zip',required=True);p.add_argument('--out',default='v8a_output');a=p.parse_args()
 os.makedirs(a.out,exist_ok=True)
 bars=data(a.zip);atr,adx,er=features(bars)
 results=[];all_trades=[]
 for rr in RRS:
  trades,diag=simulate(bars,atr,adx,er,rr)
  rec=dict(rr=rr,full=metrics(trades),
    jan_jul=metrics([t for t in trades if t['entry_utc'][:7]<='2026-07']),
    aug_oct=metrics([t for t in trades if '2026-08'<=t['entry_utc'][:7]<='2026-10']),
    nov_partial=metrics([t for t in trades if t['entry_utc'][:7]=='2026-11']),
    by_month={m:metrics([t for t in trades if t['entry_utc'][:7]==m]) for m in sorted(set(t['entry_utc'][:7] for t in trades))},diagnostic=diag)
  results.append(rec);all_trades.extend(trades)
  print('RR_RESULT',json.dumps({k:rec[k] for k in ('rr','full','jan_jul','aug_oct','nov_partial','diagnostic')}),flush=True)
 with open(os.path.join(a.out,'summary.json'),'w') as f:
  json.dump(dict(settings=dict(NBOX=NBOX,ADX_LT=20,ER_LT=.35,WIDTH_ATR=[1.5,3.5],BREAK_ATR=.15,
  BODY_MIN=.5,LOCK=LOCK,HOLD_BARS=HOLD,ENTRY_SLIP_PIPS=SLIP_ENTRY,EXIT_SLIP_PIPS=SLIP_EXIT,
  RISK_FRACTION=F),results=results),f,indent=2)
 with open(os.path.join(a.out,'trades.csv'),'w',newline='') as f:
  cols=list(all_trades[0]) if all_trades else ['rr','entry_utc','net_R']
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(all_trades)
 print('DONE',len(all_trades),'trades across R:R configurations',flush=True)
if __name__=='__main__':main()
