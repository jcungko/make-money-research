"""Only synthetic QA; no historical Exness or MT5 execution claims."""
import unittest
from v23_barrier_core import Quote,replay

def q(t,mid):
    return Quote(t,mid-0.00005,mid+0.00005)

class TestSynthetic(unittest.TestCase):
    def scenario(self,side,rows,**kwargs):
        return replay([q(t,p) for t,p in rows],0,side,hold_ms=1000,**kwargs)
    def test_buy_stop_gap(self):
        x=self.scenario("BUY",[(0,1.1),(100,1.1),(200,1.0994),(300,1.099),(1100,1.099)])
        self.assertEqual(x.reason,"STOP")
        self.assertLess(x.pnl_usd,-0.4)
    def test_sell_stop_gap(self):
        x=self.scenario("SELL",[(0,1.1),(100,1.1),(200,1.1006),(300,1.101),(1100,1.101)])
        self.assertEqual(x.reason,"STOP")
        self.assertLess(x.pnl_usd,-0.4)
    def test_buy_target(self):
        x=self.scenario("BUY",[(0,1.1),(100,1.1),(200,1.101),(300,1.101)])
        self.assertEqual(x.reason,"TARGET")
        self.assertGreater(x.pnl_usd,0)
    def test_sell_target(self):
        x=self.scenario("SELL",[(0,1.1),(100,1.1),(200,1.099),(300,1.099)])
        self.assertEqual(x.reason,"TARGET")
        self.assertGreater(x.pnl_usd,0)
    def test_no_fill_censored(self):
        x=self.scenario("BUY",[(0,1.1),(100,1.1),(200,1.0994)],max_lag_ms=50)
        self.assertEqual((x.status,x.reason),("CENSORED","MISSING_STOP_FILL"))
    def test_risk_reject(self):
        x=self.scenario("BUY",[(0,1.1),(100,1.1)],equity_usd=10)
        self.assertEqual(x.reason,"RISK_LIMIT")
    def test_stale_entry(self):
        x=self.scenario("BUY",[(0,1.1),(3000,1.1)])
        self.assertEqual(x.reason,"MISSING_ENTRY")
    def test_crossed(self):
        self.assertEqual(replay([Quote(100,1.2,1.1)],0,"BUY").reason,"INVALID_QUOTE")
    def test_timeout(self):
        self.assertEqual(self.scenario("BUY",[(0,1.1),(100,1.1),(1100,1.1)]).reason,"TIMEOUT")
    def test_commission_swap(self):
        rows=[(0,1.1),(100,1.1),(1100,1.1)]
        a=self.scenario("BUY",rows).pnl_usd
        b=self.scenario("BUY",rows,commission_usd=0.03,swap_usd=0.02).pnl_usd
        self.assertAlmostEqual(a-b,0.05)
    def test_missing_timeout(self):
        x=self.scenario("BUY",[(0,1.1),(100,1.1),(1200,1.1)],max_lag_ms=50)
        self.assertEqual(x.reason,"MISSING_TIMEOUT_FILL")
    def test_unsorted(self):
        self.assertEqual(replay([q(100,1.1),q(0,1.1)],0,"BUY").reason,"UNSORTED")
    def test_no_lookahead(self):
        x=self.scenario("BUY",[(0,1.5),(100,1.1),(1100,1.1)])
        self.assertEqual(x.reason,"TIMEOUT")
        self.assertLess(abs(x.pnl_usd),0.2)

if __name__=="__main__":
    unittest.main()
