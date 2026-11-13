"""Synthetic only: tests for unresolved exposure accounting, not Exness backtests."""
import unittest
from v23_barrier_core import Quote
from v23_exposure_ledger import ResearchLedger


def q(ms, mid):
    return Quote(ms, mid - 0.00005, mid + 0.00005)


class TestExposureLedger(unittest.TestCase):
    def test_missing_stop_fill_blocks_future_entries(self):
        ledger = ResearchLedger()
        out = ledger.attempt([q(0, 1.1), q(100, 1.1), q(200, 1.099)],
                             0, "BUY", max_lag_ms=50)
        self.assertEqual(out.reason, "MISSING_STOP_FILL")
        self.assertTrue(ledger.has_unresolved_exposure)
        self.assertFalse(ledger.can_open_new_position)
        self.assertFalse(ledger.eligible_for_performance_claim)
        self.assertEqual(ledger.verified_closed_pnl_usd, 0)
        self.assertIsNone(ledger.records[0].realized_pnl_usd)
        with self.assertRaisesRegex(RuntimeError, "NEW_ENTRY_BLOCKED"):
            ledger.attempt([q(0, 1.1), q(100, 1.1)], 0, "BUY")

    def test_missing_timeout_fill_remains_unresolved(self):
        ledger = ResearchLedger()
        out = ledger.attempt([q(0, 1.1), q(100, 1.1), q(5000, 1.1)],
                             0, "SELL", hold_ms=1000)
        self.assertEqual(out.reason, "MISSING_TIMEOUT_FILL")
        self.assertEqual(ledger.summary()["unresolved_count"], 1)
        self.assertFalse(ledger.summary()["open_equity_accounted"])

    def test_missing_entry_does_not_create_exposure(self):
        ledger = ResearchLedger()
        out = ledger.attempt([q(0, 1.1), q(5000, 1.1)], 0, "BUY")
        self.assertEqual(out.reason, "MISSING_ENTRY")
        self.assertEqual(len(ledger.records), 0)
        self.assertTrue(ledger.can_open_new_position)

    def test_simulated_close_not_broker_certified(self):
        ledger = ResearchLedger()
        out = ledger.attempt([q(0, 1.1), q(100, 1.1), q(1100, 1.1)],
                             0, "BUY", hold_ms=1000)
        self.assertEqual(out.status, "FILLED")
        self.assertEqual(ledger.summary()["closed_simulated_count"], 1)
        self.assertFalse(ledger.summary()["broker_fills_verified"])
        self.assertTrue(ledger.can_open_new_position)

    def test_last_quote_is_not_fake_mark_or_exit(self):
        ledger = ResearchLedger()
        ledger.attempt([q(0, 1.1), q(100, 1.1), q(200, 1.099)],
                       0, "BUY", max_lag_ms=50)
        r = ledger.records[0]
        self.assertEqual(r.last_mark_ms, 200)
        self.assertIsNone(r.last_mark_pnl_usd)
        self.assertIsNone(r.exit_ms)


if __name__ == "__main__":
    unittest.main()
