"""V23 research-only regression: unresolved execution must not be a profit claim."""
import unittest
from v23_barrier_core import Quote, replay
from v23_exposure_ledger import ResearchLedger

def q(ms, mid):
    return Quote(ms, mid - 0.00005, mid + 0.00005)

class TestUnresolvedConservative(unittest.TestCase):
    def test_stop_fill_missing_never_becomes_zero_pnl(self):
        ledger = ResearchLedger()
        outcome = ledger.attempt([q(0, 1.1), q(100, 1.1), q(200, 1.099)],
                                 0, "BUY", max_lag_ms=50)
        self.assertEqual(outcome.reason, "MISSING_STOP_FILL")
        self.assertIsNone(outcome.pnl_usd)
        self.assertEqual(ledger.summary()["unresolved_count"], 1)
        self.assertFalse(ledger.summary()["open_equity_accounted"])
        self.assertFalse(ledger.eligible_for_performance_claim)
        self.assertFalse(ledger.can_open_new_position)
        self.assertIsNone(ledger.records[0].realized_pnl_usd)

    def test_missing_timeout_fill_blocks_new_entries(self):
        ledger = ResearchLedger()
        ledger.attempt([q(0, 1.1), q(100, 1.1), q(5000, 1.1)],
                       0, "SELL", hold_ms=1000)
        self.assertEqual(ledger.summary()["unresolved_count"], 1)
        with self.assertRaises(RuntimeError):
            ledger.attempt([q(0, 1.1), q(100, 1.1), q(1100, 1.1)],
                           0, "SELL", hold_ms=1000)

    def test_synthetic_closed_pnl_not_broker_verified(self):
        ledger = ResearchLedger()
        ledger.attempt([q(0, 1.1), q(100, 1.1), q(1100, 1.1)],
                       0, "BUY", hold_ms=1000)
        self.assertEqual(ledger.summary()["closed_simulated_count"], 1)
        self.assertFalse(ledger.summary()["broker_fills_verified"])

    def test_reject_does_not_fabricate_exposure(self):
        ledger = ResearchLedger()
        result = ledger.attempt([q(0, 1.1), q(5000, 1.1)], 0, "BUY")
        self.assertEqual(result.reason, "MISSING_ENTRY")
        self.assertEqual(ledger.summary()["unresolved_count"], 0)
        self.assertEqual(ledger.summary()["closed_simulated_count"], 0)

if __name__ == "__main__":
    unittest.main()
