"""Connectivity and schema probe for public, read-only Binance data archives."""
import io, json, time, zipfile
import requests

U=[
 "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2026-09.zip",
 "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-09.zip",
 "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2026-09.zip",
 "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?list-type=2&prefix=data/futures/um/monthly/klines/BTCUSDT/15m/&max-keys=2",
]
s=requests.Session()
ok=0
for url in U:
 try:
  t=time.perf_counter()
  r=s.get(url,timeout=18)
  print(json.dumps({"url":url,"status":r.status_code,"bytes":len(r.content),"seconds":round(time.perf_counter()-t,2),"content_type":r.headers.get("Content-Type")}),flush=True)
  if r.ok and r.content[:2]==b"PK":
   with zipfile.ZipFile(io.BytesIO(r.content)) as z:
    names=z.namelist()
    print("zip:",names,"first rows:",z.open(names[0]).read(450)[:450],flush=True)
   ok+=1
  elif r.ok:
   print("preview",r.text[:400],flush=True)
 except Exception as e: print("ERROR",type(e).__name__,str(e)[:200],flush=True)
print("AVAILABLE_ARCHIVES",ok,flush=True)
if ok==0: raise SystemExit("No archive available from GitHub runner")
