"""V23 research-only conservative accounting adapter for partial quote-side replay.

Not a broker fill assertion. Unresolved exposure remains OPEN and disqualifies
performance; no implicit zero-PnL close. No network, broker, or trading actions.
"""
from dataclasses import dataclass, field
from math import isfinite
from v23_barrier_core import Quote, Outcome, POINT, USD_PER_POINT, replay


@dataclass
class PositionRecord:
    side: str
    entry_ms: int | None
    exit_ms: int | None
    status: str
    reason: str
    realized_pnl_usd: float | None
    last_mark_pnl_usd: float | None = None
    last_mark_ms: int | None = None
    mark_is_stale: bool = True


@dataclass
class ResearchLedger:
    equity_usd: float = 100.0
    records: list[PositionRecord] = field(default_factory=list)
    blocked_reason: str | None = None

    @property
    def has_unresolved_exposure(self):
        return any(r.status == "UNRESOLVED" for r in self.records)

    @property
    def can_open_new_position(self):
        return not self.has_unresolved_exposure and self.blocked_reason is None

    @property
    def verified_closed_pnl_usd(self):
        return round(sum(r.realized_pnl_usd for r in self.records
                         if r.status == "CLOSED_SIMULATED" and r.realized_pnl_usd is not None), 8)

    @property
    def eligible_for_performance_claim(self):
        return (not self.has_unresolved_exposure
                and self.blocked_reason is None
                and all(r.status != "UNRESOLVED" for r in self.records))

    def attempt(self, quotes: list[Quote], signal_ms: int, side: str, **kwargs):
        """One-position conservative adapter; synthetic fixtures only.

        Do not infer a broker fill from replay's FILLED status.
        """
        if not self.can_open_new_position:
            raise RuntimeError("NEW_ENTRY_BLOCKED_UNRESOLVED_EXPOSURE")
        outcome = replay(quotes, signal_ms, side, equity_usd=self.equity_usd, **kwargs)
        if outcome.status == "REJECTED":
            return outcome
        if outcome.status == "FILLED":
            self.records.append(PositionRecord(side, outcome.entry_ms, outcome.exit_ms,
                "CLOSED_SIMULATED", outcome.reason, outcome.pnl_usd))
            self.equity_usd = round(self.equity_usd + outcome.pnl_usd, 8)
            return outcome
        if outcome.entry_ms is None:
            # No executed entry was established by this synthetic replay.
            return outcome
        # The core cannot prove broker execution at missing stop/timeout fill.
        record = PositionRecord(side, outcome.entry_ms, None, "UNRESOLVED",
                                outcome.reason, None)
        self.records.append(record)
        self.blocked_reason = "UNRESOLVED_EXIT_NO_BROKER_FILL_EVIDENCE"
        self.mark_last_quote(record, quotes)
        return outcome

    def mark_last_quote(self, record: PositionRecord, quotes: list[Quote]):
        """Indicative open-equity diagnostic only; NOT a realized exit.

        Entry price is not exposed by partial core, so do not invent an exact
        mark-to-market dollar PnL. Last quote timestamp is retained for review.
        """
        candidates = [q for q in quotes if record.entry_ms is not None
                      and q.ms >= record.entry_ms and q.bid > 0
                      and q.ask >= q.bid and isfinite(q.bid) and isfinite(q.ask)]
        if candidates:
            record.last_mark_ms = candidates[-1].ms
        record.last_mark_pnl_usd = None
        record.mark_is_stale = True

    def summary(self):
        return {
            "closed_simulated_count": sum(r.status == "CLOSED_SIMULATED" for r in self.records),
            "unresolved_count": sum(r.status == "UNRESOLVED" for r in self.records),
            "verified_closed_simulated_pnl_usd": self.verified_closed_pnl_usd,
            "open_equity_accounted": not self.has_unresolved_exposure,
            "eligible_for_performance_claim": self.eligible_for_performance_claim,
            "new_entries_blocked": not self.can_open_new_position,
            "broker_fills_verified": False,
        }
