"""Settings for the OrangeX perpetual paper venue. Frozen; hashed into provenance."""

import hashlib
import json
import math
from dataclasses import asdict, dataclass

from ..config import D


@dataclass(frozen=True)
class PerpSettings:
    venue: str = "orangex-perp"
    instrument: str = "BTC-USDT-PERPETUAL"
    label: str = "BTC-PERP"
    capital: str = "1000"
    leverage: int = 20
    margin_fraction: str = "0.33"
    taker_fee: str = "0.0006"
    # A flip is allowed only when the projected close net minus the re-entry fee is at least this
    # many USDT. "0" = a fee-neutral round trip. Negative allows a bounded loss to be flipped out of.
    flip_min_net: str = "0"
    mmr: str = "0.005"
    funding_fallback: str = "0.0001"
    reward_deadband: str = "1.0"
    interval_seconds: float = 60
    max_quote_age: float = 15
    spread_limit: str = "0.005"
    price_increment: str = "0.1"
    base_increment: str = "0.001"
    minimum_base: str = "0.001"
    minimum_quote: str = "5"
    outage_ticks: int = 10
    neural_ms: float = 500
    neural_bin_ms: float = 10
    pulse_ms: float = 200
    pulse_current: float = 20
    decoder_threshold_hz: float = 2
    learning: bool = True
    fly_name: str = "초파리"

    def __post_init__(self):
        if type(self.leverage) is not int or not 1 <= self.leverage <= 125:
            raise ValueError("Leverage must be an integer in 1..125")
        if not D(0) < D(self.margin_fraction) <= D(1):
            raise ValueError("Margin fraction must be in (0, 1]")
        if not D(0) <= D(self.taker_fee) <= D("0.01"):
            raise ValueError("Taker fee must be in [0, 1%]")
        try:  # any finite USDT amount, including a negative one; D() rejects nan/inf
            D(self.flip_min_net)
        except (ValueError, ArithmeticError):
            raise ValueError("flip_min_net must be a finite USDT amount")
        if not D(0) < D(self.mmr) < D(1) / D(self.leverage):
            raise ValueError("Maintenance margin must be below 1/leverage")
        if D(self.capital) <= 0:
            raise ValueError("Capital must be positive")
        if not D(0) <= D(self.funding_fallback) <= D("0.01"):
            raise ValueError("Funding fallback out of range")
        if D(self.reward_deadband) <= 0:
            raise ValueError("Positive reinforcement deadband required")
        if not math.isfinite(self.interval_seconds) or self.interval_seconds < 60:
            raise ValueError("Rate limit: >=60 s between orders")
        if not D(0) < D(self.spread_limit) <= D("0.01"):
            raise ValueError("Invalid spread limit")
        for k in ["price_increment", "base_increment", "minimum_base", "minimum_quote"]:
            if D(getattr(self, k)) <= 0:
                raise ValueError("Instrument constants must be positive")
        if type(self.outage_ticks) is not int or self.outage_ticks < 1:
            raise ValueError("outage_ticks must be a positive integer")
        for x in [self.max_quote_age, self.neural_ms, self.neural_bin_ms,
                  self.pulse_ms, self.pulse_current, self.decoder_threshold_hz]:
            if not math.isfinite(x) or x <= 0:
                raise ValueError("Positive finite parameter required")
        if self.neural_bin_ms > 10 or self.pulse_ms > self.neural_ms:
            raise ValueError("Use <=10 ms neural bins; pulse must fit a decision window")
        if any(abs(x * 10 - round(x * 10)) > 1e-7
               for x in [self.neural_ms, self.neural_bin_ms, self.pulse_ms]):
            raise ValueError("Neural intervals must be multiples of 0.1 ms")

    def signature(self):
        return hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True).encode()
        ).hexdigest()
