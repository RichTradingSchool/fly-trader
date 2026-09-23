"""OrangeX public perpetual observations (no key). History is seeded from Bybit 1m closes."""

import json
import math
import time
import urllib.request
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation

from ..config import D

ORANGEX = "https://api.orangex.com/api/v1/public"
BYBIT_KLINE = "https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval=1&limit=121"
SEED_ATTEMPTS = 3
SEED_RETRY_SECONDS = 2  # a refused connection fails instantly; without a pause all 3 tries burn in ~100 ms
FUNDING_RATE_LIMIT = D("0.01")  # same bound PerpSettings puts on funding_fallback (1% per interval)


class MarketUnavailable(RuntimeError):
    """Transient market-data failure; the runner records the tick and moves on."""


class SeedUnavailable(RuntimeError):
    """Startup history seed failed; the runner exits and systemd restarts it (spec §10). Not a MarketUnavailable."""


def _dec(value):
    """Parse a number from untrusted payload data. decimal.InvalidOperation (None, "", "N/A", ...) is
    normalized to ValueError so every call site's existing `except ValueError` clause covers it, instead
    of an ArithmeticError escaping uncaught."""
    try:
        return D(value)
    except InvalidOperation as e:
        raise ValueError(f"not a number: {value!r}") from e


@dataclass(frozen=True)
class PerpQuote:
    product: str
    bid: Decimal
    ask: Decimal
    mark: Decimal
    timestamp: float
    price_increment: Decimal
    base_increment: Decimal
    minimum_base: Decimal
    minimum_quote: Decimal

    def __post_init__(self):
        if (
            not self.bid.is_finite()
            or not self.ask.is_finite()
            or not self.mark.is_finite()
            or not 0 < self.bid <= self.ask
            or self.mark <= 0
            or not math.isfinite(self.timestamp)
        ):
            raise ValueError("Invalid quote")
        for k in ["price_increment", "base_increment", "minimum_base", "minimum_quote"]:
            if not getattr(self, k).is_finite() or getattr(self, k) <= 0:
                raise ValueError("Invalid market increment")

    def json(self):
        return {k: str(v) if isinstance(v, Decimal) else v for k, v in asdict(self).items()}


def default_http(url):
    req = urllib.request.Request(url, headers={"User-Agent": "stonkfly-perp/0.1"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


class OrangeXMarket:
    def __init__(self, settings, http=None):
        self.s = settings
        self.http = http or default_http
        self.products = (settings.instrument,)
        self.history = {settings.instrument: []}
        self._seeded = False

    # ---- helpers -------------------------------------------------------
    def _get(self, url):
        try:
            data = self.http(url)
        except Exception as e:  # network, JSON, timeout
            raise MarketUnavailable(f"request failed: {type(e).__name__}") from e
        if not isinstance(data, dict):
            raise MarketUnavailable("non-object response")
        return data

    def _rpc(self, method, **params):
        query = "&".join(f"{k}={v}" for k, v in params.items())
        data = self._get(f"{ORANGEX}/{method}?{query}")
        if "error" in data or "result" not in data:
            raise MarketUnavailable(f"{method}: {data.get('error', 'no result')}")
        return data["result"]

    def _seed_history(self):
        last = None
        for attempt in range(SEED_ATTEMPTS):
            if attempt:
                time.sleep(SEED_RETRY_SECONDS)  # give a restarting router/DNS a chance between tries
            try:
                data = self._get(BYBIT_KLINE)
                rows = data["result"]["list"]
                break
            except (MarketUnavailable, KeyError, TypeError) as e:
                last = e
        else:
            raise SeedUnavailable(f"seed failed: {last}")
        # Bybit returns newest first; the first row is the still-open minute.
        # Any failure past this point (malformed close, too-short list) is fatal for
        # startup seeding — never transient — so it raises SeedUnavailable directly,
        # without burning the remaining seed attempts on a deterministic payload.
        try:
            closes = [float(_dec(r[4])) for r in reversed(rows[1:])]
            if not closes or any(not math.isfinite(v) or v <= 0 for v in closes):
                raise ValueError("invalid seed candles")
        except (IndexError, TypeError, ValueError) as e:
            raise SeedUnavailable(f"seed failed: {e}") from e
        self.history[self.s.instrument] = closes[-120:]
        self._seeded = True

    # ---- public API ----------------------------------------------------
    def snapshot(self):
        if not self._seeded and not self.history[self.s.instrument]:
            self._seed_history()
        self._seeded = True
        book = self._rpc("get_order_book", instrument_name=self.s.instrument, depth=1)
        try:
            bid = _dec(book["bids"][0][0])
            ask = _dec(book["asks"][0][0])
            ts = int(book["timestamp"]) / 1000.0
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise MarketUnavailable("malformed order book") from e
        try:
            ticker = self._rpc("tickers", instrument_name=self.s.instrument)
            mark = _dec(ticker[0]["mark_price"])
        except (MarketUnavailable, KeyError, IndexError, TypeError, ValueError):
            mark = (bid + ask) / 2  # ticker is display-only; never block a tick on it
        try:
            quote = PerpQuote(
                self.s.instrument, bid, ask, mark, ts,
                D(self.s.price_increment), D(self.s.base_increment),
                D(self.s.minimum_base), D(self.s.minimum_quote),
            )
        except ValueError as e:
            raise MarketUnavailable(str(e)) from e
        return {self.s.instrument: quote}

    def record(self, quotes):
        for p, q in quotes.items():
            self.history[p].append(float((q.bid + q.ask) / 2))
            self.history[p] = self.history[p][-120:]

    def funding(self):
        """(rate, expire_ms, source). Falls back to the configured constant.

        A rate outside ±1% per interval is not a market condition, it is a bad payload (a units
        change, a placeholder, a decimal slip). Settling it would move real paper cash by hundreds
        of USDT per tick and end the season in an accounting-error halt, so it falls back instead."""
        try:
            r = self._rpc("get_funding_rate", instrument_name=self.s.instrument)
            rate = _dec(r["rate"])
            expire = int(r["expire_time"])
            if not rate.is_finite() or abs(rate) > FUNDING_RATE_LIMIT or expire <= 0:
                raise ValueError("bad funding payload")
            return rate, expire, "orangex"
        except (MarketUnavailable, KeyError, TypeError, ValueError):
            return D(self.s.funding_fallback), int(time.time() * 1000) + 8 * 3600 * 1000, "fallback"
