"""Execution limits for the perpetual paper venue. They veto; they never choose.

A flip is gated on the whole round trip: the projected close net minus the re-entry fee must be
>= `flip_min_net` (see `PerpLedger.projected_flip_net`).

Veto strings (the runner records them and the dashboard's REASON table maps them):
"STOP file present", the `halted` reason, "Incomplete market snapshot", "Quote identity mismatch",
"Stale or future quote", "Spread limit", "Invalid neural proposal", "Order cooldown",
"Already positioned", "Below breakeven", "Below minimum".
"""

import time

from ..config import D
from ..risk import Veto  # re-exported so callers catch one exception type

SIDES = ("LONG", "SHORT")


class PerpGuard:
    def __init__(self, settings, ledger, stop_file):
        self.s = settings
        self.l = ledger
        self.stop_file = stop_file

    def check(self, quotes, now):
        if self.stop_file.exists():
            raise Veto("STOP file present")
        if self.l.get("halted"):
            raise Veto(self.l.get("halted"))
        if set(quotes) != {self.s.instrument}:
            raise Veto("Incomplete market snapshot")
        q = quotes[self.s.instrument]
        if q.product != self.s.instrument:
            raise Veto("Quote identity mismatch")
        if not -0.5 <= now - q.timestamp <= self.s.max_quote_age:
            raise Veto("Stale or future quote")
        if (q.ask - q.bid) / q.bid > D(self.s.spread_limit):
            raise Veto("Spread limit")

    def plan(self, product, side, quotes, now=None):
        now = time.time() if now is None else now
        self.check(quotes, now)
        if product != self.s.instrument or side not in SIDES:
            raise Veto("Invalid neural proposal")
        if now - float(self.l.get("last_attempt") or 0) < self.s.interval_seconds:
            raise Veto("Order cooldown")
        q = quotes[product]
        p = self.l.position
        if p is not None and p["side"] == side:
            raise Veto("Already positioned")
        # A flip pays two taker fees on top of the one already sunk opening the position. The 4 h
        # rehearsal flipped 20 times for 147 USDT of fees against +7.8 realized, so the rule is:
        # the close net minus the re-entry fee must be >= flip_min_net. Charging the re-entry fee
        # too is what makes an allowed flip a fee-neutral round trip.
        if p is not None and self.l.projected_flip_net(q) < D(self.s.flip_min_net):
            raise Veto("Below breakeven")
        action = "OPEN" if p is None else "FLIP"
        # Size check uses post-close equity for a flip; the ledger recomputes at fill time.
        if p is None:
            e = self.l.entry_size(q, side)
            if e["qty"] < q.minimum_base or e["notional"] < q.minimum_quote:
                raise Veto("Below minimum")
        return {
            "product": product,
            "side": side,
            "action": action,
            "quote": q.json(),
            "quote_timestamp": q.timestamp,
            "settings": self.s.signature(),
        }
