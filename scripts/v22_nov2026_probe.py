#!/usr/bin/env python3
import requests, json, datetime, os
from pathlib import Path
syms=('NVDA','AMD','AVGO','XOM','GOOGL')
base='https://ticks.ex2archive.com/ticks'
records=[]
with requests.Session() as sess:
 sess.headers['User-Agent']='Mozilla/5.0 (compatible; V22-Research/1.0)'
 for sym in syms:
  urls=[
   (f'{base}/{sym}/2026/10/Exness_{sym}_2026_10.zip','control_oct'),
   (f'{base}/{sym}/2026/11/Exness_{sym}_2026_11.zip','nov_month'),
   (f'{base}/{sym}/2026/11/12/Exness_{sym}_2026_11_12.zip','nov_day_12_subdir'),
   (f'{base}/{sym}/2026/11/Exness_{sym}_2026_11_12.zip','nov_day_12'),
   (f'{base}/{sym}/2026/11/11/Exness_{sym}_2026_11_11.zip','nov_day_11_subdir'),
  ]
  for url,kind in urls:
   try:
    r=sess.head(url,timeout=15,allow_redirects=True)
    status=r.status_code
    msg={'symbol':sym,'kind':kind,'url':url,'http_head':status,'length':r.headers.get('content-length'),
      'type':r.headers.get('content-type'),'last_modified':r.headers.get('Last-Modified')}
    if status in (403,405):
     try:
      with sess.get(url,timeout=(15,20),stream=True) as g: msg['http_get']=g.status_code;msg['get_length']=g.headers.get('content-length')
     except Exception as e:msg['get_error']=str(e)[:100]
   except Exception as e:
    msg={'symbol':sym,'kind':kind,'url':url,'error':str(e)[:200]}
   records.append(msg)
   print('PROBE',json.dumps(msg),flush=True)
out=Path('results/v22_nov2026_probe')
out.mkdir(parents=True,exist_ok=True)
(out/'probe.json').write_text(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'results':records},indent=2)+'\n')
