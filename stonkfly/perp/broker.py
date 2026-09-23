"""Paper execution for the perpetual venue: fills at the observed book, in one transaction."""

from ..venues.orangex import PerpQuote
from ..config import D
from .risk import Veto


class PerpPaperBroker:
    mode = "paper"

    def __init__(self, settings, ledger):
        self.s = settings
        self.l = ledger

    def preflight(self):
        return {"mode": "paper", "venue": self.s.venue, "network_execution": False}

    def reconcile(self):
        pass  # fills are atomic; nothing can be half-done

    def verify_balances(self):
        pass

    def execute(self, plan, now):
        j = plan["quote"]
        quote = PerpQuote(
            j["product"], D(j["bid"]), D(j["ask"]), D(j["mark"]), float(j["timestamp"]),
            D(j["price_increment"]), D(j["base_increment"]), D(j["minimum_base"]), D(j["minimum_quote"]),
        )
        tick = self.l.get("tick")
        try:
            if plan["action"] == "OPEN":
                fills = [self.l.open_position(plan["side"], quote, tick, now, reason="signal", last_attempt=now)]
            else:
                fills = self.l.flip(plan["side"], quote, tick, now, last_attempt=now)
        except ValueError as e:
            raise Veto(str(e)) from e
        return {"mode": "paper", "status": "FILLED", "action": plan["action"], "side": plan["side"], "fills": fills}
