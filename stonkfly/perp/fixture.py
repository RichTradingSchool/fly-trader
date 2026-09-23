"""Deterministic perpetual prices for offline verification. Never used with real data."""

import math
import time

from ..config import D, down, up
from ..venues.orangex import OrangeXMarket, PerpQuote

BASE = D("81000")


class FixturePerpMarket:
    def __init__(self, settings):
        self.s = settings
        self.products = (settings.instrument,)
        self.tick = 0
        self.history = {settings.instrument: []}

    def snapshot(self):
        p = self.s.instrument
        # Slow cosine: one step moves the bid <= 0.42 % (inside the 0.5 % re-quote gate),
        # a long opened at tick 0 is liquidated at tick 20, and 40 ticks swing ~10.9 %.
        price = BASE * D(str(round(1 + 0.06 * math.cos(self.tick * 0.07), 8)))
        bid = down(price * D("0.9999"), D(self.s.price_increment))
        ask = up(price * D("1.0001"), D(self.s.price_increment))
        q = PerpQuote(
            p, bid, ask, (bid + ask) / 2, time.time(),
            D(self.s.price_increment), D(self.s.base_increment),
            D(self.s.minimum_base), D(self.s.minimum_quote),
        )
        if not self.history[p]:
            self.history[p] = [
                float(BASE * D(str(round(1 + 0.01 * math.sin(i * 0.4), 8)))) for i in range(80)
            ]
        self.tick += 1
        return {p: q}

    record = OrangeXMarket.record

    def funding(self):
        return D(self.s.funding_fallback), int(time.time() * 1000) + 8 * 3600 * 1000, "fixture"
