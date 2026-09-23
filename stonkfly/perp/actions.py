"""Bridges the fixed neural decoder (BUY/SELL) to perpetual sides (LONG/SHORT). No LLM, no wallet."""

import time

from .risk import Veto

SIDE_MAP = {"BUY": "LONG", "SELL": "SHORT"}


class PerpActions:
    def __init__(self, guard, broker):
        self.guard = guard
        self.broker = broker
        self.quotes = {}

    def invoke(self, args):
        side = SIDE_MAP.get(args.get("side"))
        if side is None:
            raise Veto("Invalid neural proposal")
        now = time.time()
        plan = self.guard.plan(args.get("product"), side, self.quotes, now)
        plan["neural_observation"] = self.guard.l.get("observation")
        plan["checkpoint"] = self.guard.l.get("checkpoint")
        return self.broker.execute(plan, now)
