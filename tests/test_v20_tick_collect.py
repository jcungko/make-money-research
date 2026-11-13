"""Synthetic fixture to test only ingestion, never counted as Exness trading results."""
import csv, datetime as dt, io, json, tempfile, zipfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v20_tick_collect import parse_utc_ms,source_url,audit_zip

def test_url_monthly_and_daily():
    assert source_url('2025-01').endswith('/2025/01/Exness_EURUSDm_2025_01.zip')
    assert source_url('2026-11','2026-11-12').endswith('/2026/11/12/Exness_EURUSDm_2026_11_12.zip')

def test_timestamp_ms_and_utc():
    assert parse_utc_ms('2025-01-02 10:00:00.123Z')%1000==123
    try:parse_utc_ms('2025-01-02 10:00:00')
    except ValueError:pass
    else:assert False

def fixture(path,wrong=False):
    s=io.StringIO();w=csv.writer(s);w.writerow(['Exness','Symbol','Timestamp','Bid','Ask'])
    for i in range(10):
        w.writerow(['exness','EURUSDm' if not wrong else 'EURUSD','2025-01-02 10:00:%02d.%03dZ'%(i,i+1),1.10000+i*1e-5,1.10012+i*1e-5])
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('quotes.csv',s.getvalue())

def test_audit_real_zip_parser():
    with tempfile.TemporaryDirectory() as p:
        path=Path(p)/'a.zip';fixture(path)
        r=audit_zip(path,'2025-01',min_ticks=10)
        assert r['tick_count']==10 and r['subsecond_ratio']==1
        assert r['spread_pips_approx_quantiles_from_reservoir_10000']['p50']==1.2
        assert r['first_timestamp_ms']<r['last_timestamp_ms']

def test_wrong_symbol_rejected():
    with tempfile.TemporaryDirectory() as p:
        path=Path(p)/'a.zip';fixture(path,wrong=True)
        try:audit_zip(path,'2025-01',min_ticks=10)
        except ValueError as e:assert 'not EURUSDm' in str(e)
        else:assert False