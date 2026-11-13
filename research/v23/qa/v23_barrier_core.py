"""Research-only deterministic quote-side synthetic replay. Not broker-certified, not a full V23 runner."""
from dataclasses import dataclass
from math import isfinite

POINT = 0.00001
USD_PER_POINT = 0.01

@dataclass(frozen=True)
class Quote:
    ms: int
    bid: float
    ask: float

@dataclass(frozen=True)
class Outcome:
    status: str
    side: str
    pnl_usd: float | None = None
    reason: str = ""
    entry_ms: int | None = None
    exit_ms: int | None = None

def replay(quotes, signal_ms, side, *, stop_points=40, target_points=68,
           latency_ms=100, fill_delay_ms=100, slip_points=1,
           hold_ms=300000, max_lag_ms=2000, equity_usd=100,
           commission_usd=0, swap_usd=0):
    if side not in ("BUY", "SELL"):
        raise ValueError("side")
    if not quotes:
        return Outcome("CENSORED", side, reason="NO_QUOTES")
    if any(x.bid<=0 or x.ask<x.bid or not all(map(isfinite,(x.bid,x.ask))) for x in quotes):
        return Outcome("REJECTED", side, reason="INVALID_QUOTE")
    if any(a.ms>b.ms for a,b in zip(quotes,quotes[1:])):
        return Outcome("REJECTED", side, reason="UNSORTED")
    if min(stop_points,target_points)<=0 or min(latency_ms,fill_delay_ms,slip_points,hold_ms,max_lag_ms,commission_usd)<0:
        raise ValueError("invalid parameter")
    due=signal_ms+latency_ms
    entry=next((x for x in quotes if x.ms>=due),None)
    if entry is None or entry.ms-due>max_lag_ms:
        return Outcome("REJECTED",side,reason="MISSING_ENTRY")
    if (stop_points+2*slip_points)*USD_PER_POINT+commission_usd>equity_usd*0.02:
        return Outcome("REJECTED",side,reason="RISK_LIMIT")
    price=entry.ask+slip_points*POINT if side=="BUY" else entry.bid-slip_points*POINT
    stop=price-stop_points*POINT if side=="BUY" else price+stop_points*POINT
    target=price+target_points*POINT if side=="BUY" else price-target_points*POINT
    deadline=entry.ms+hold_ms
    def fill_after(due,reason):
        x=next((y for y in quotes if y.ms>=due),None)
        if x is None or x.ms-due>max_lag_ms:
            return Outcome("CENSORED",side,reason="MISSING_"+reason+"_FILL",entry_ms=entry.ms)
        exit_price=x.bid-slip_points*POINT if side=="BUY" else x.ask+slip_points*POINT
        pnl=((exit_price-price) if side=="BUY" else (price-exit_price))/POINT*USD_PER_POINT-commission_usd-swap_usd
        return Outcome("FILLED",side,round(pnl,8),reason,entry.ms,x.ms)
    for x in quotes:
        if x.ms<=entry.ms: continue
        if x.ms>deadline: break
        trigger=x.bid if side=="BUY" else x.ask
        stop_hit=trigger<=stop if side=="BUY" else trigger>=stop
        target_hit=trigger>=target if side=="BUY" else trigger<=target
        if stop_hit or target_hit:
            return fill_after(x.ms+fill_delay_ms,"STOP" if stop_hit else "TARGET")
    return fill_after(deadline,"TIMEOUT")
