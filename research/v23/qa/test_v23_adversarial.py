"""Adversarial synthetic diagnostics for frozen partial V23 QA core; no historical market data."""
import unittest
from v23_barrier_core import Quote, replay

def q(ms, mid, spread=0.0001):
    return Quote(ms, mid-spread/2, mid+spread/2)

class TestAdversarial(unittest.TestCase):
    def test_missing_stop_fill_is_unresolved_not_zero_profit(self):
        r=replay([q(0,1.1),q(100,1.1),q(200,1.0990)],0,'BUY',max_lag_ms=50)
        self.assertEqual((r.status,r.reason),('CENSORED','MISSING_STOP_FILL'))
        self.assertIsNone(r.pnl_usd)
        self.assertIsNone(r.exit_ms)
    def test_timeout_gap_is_charged_when_quote_within_tolerance(self):
        r=replay([q(0,1.1),q(100,1.1),q(1500,1.095)],0,'BUY',hold_ms=1000)
        self.assertEqual((r.status,r.reason),('FILLED','TIMEOUT'))
        self.assertLess(r.pnl_usd,-4.0)
    def test_timeout_gap_censored_when_lag_exceeds_tolerance(self):
        r=replay([q(0,1.1),q(100,1.1),q(5000,1.095)],0,'BUY',hold_ms=1000)
        self.assertEqual(r.status,'CENSORED')
        self.assertIsNone(r.pnl_usd)
    def test_same_ms_order_changes_first_entry_quote(self):
        rows=[q(0,1.1),q(100,1.1),q(100,1.101),q(1100,1.1)]
        r=replay(rows,0,'BUY',hold_ms=1000)
        self.assertEqual(r.reason,'TIMEOUT')
        self.assertAlmostEqual(r.pnl_usd,-0.12,places=5)
    def test_spread_widening_decreases_buy_net_pnl(self):
        a=replay([q(0,1.1),q(100,1.1),q(1100,1.1)],0,'BUY',hold_ms=1000)
        b=replay([q(0,1.1,0.0002),q(100,1.1,0.0002),q(1100,1.1,0.0002)],0,'BUY',hold_ms=1000)
        self.assertLess(b.pnl_usd,a.pnl_usd)
    def test_negative_swap_is_not_validated(self):
        r=replay([q(0,1.1),q(100,1.1),q(1100,1.1)],0,'BUY',hold_ms=1000,swap_usd=-0.5)
        self.assertEqual(r.status,'FILLED')
        self.assertGreater(r.pnl_usd,0)
        # Diagnostic: negative swap is accepted by partial core; broker swap must be calibrated.

if __name__=='__main__': unittest.main()
