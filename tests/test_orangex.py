import json
import time
from decimal import Decimal
from unittest import mock

import numpy as np
import pytest

from stonkfly.config import D
from stonkfly.display import market_frame
from stonkfly.perp.config import PerpSettings
from stonkfly.venues import orangex
from stonkfly.venues.orangex import MarketUnavailable, OrangeXMarket, PerpQuote, SeedUnavailable

NOW_MS = int(time.time() * 1000)


def bybit_klines(n=3):
    # newest-first, first element is the still-open minute
    base = (int(time.time()) // 60) * 60 * 1000
    rows = []
    for i in range(n):
        start = base - i * 60000
        close = 81000 + i  # oldest gets the largest close so ordering is testable
        rows.append([str(start), "1", "2", "0", str(close), "1", "1"])
    return {"retCode": 0, "result": {"symbol": "BTCUSDT", "category": "linear", "list": rows}}


class Http:
    def __init__(self):
        self.calls = []
        self.fail = set()
        self.book_ts = NOW_MS
        self.funding = {"jsonrpc": "2.0", "result": {"rate": "0.000007", "capitalRateInterval": 8, "expire_time": NOW_MS + 3600000}}

    def __call__(self, url):
        self.calls.append(url)
        for key in self.fail:
            if key in url:
                raise OSError("boom")
        if "get_order_book" in url:
            return {"jsonrpc": "2.0", "result": {"asks": [["81340.3", "4.302"]], "bids": [["81340.2", "4.269"]],
                                                 "timestamp": str(self.book_ts), "instrument_name": "BTC-USDT-PERPETUAL"}}
        if "tickers" in url:
            return {"jsonrpc": "2.0", "result": [{"mark_price": "81340.0", "last_price": "81340.2", "timestamp": str(self.book_ts)}]}
        if "get_funding_rate" in url:
            return self.funding
        if "bybit.com" in url:
            return bybit_klines()
        raise AssertionError("unexpected url " + url)


@pytest.fixture
def market():
    return OrangeXMarket(PerpSettings(), Http())


def test_quote_fields_and_ms_to_seconds(market):
    q = market.snapshot()["BTC-USDT-PERPETUAL"]
    assert isinstance(q, PerpQuote)
    assert q.bid == D("81340.2") and q.ask == D("81340.3") and q.mark == D("81340.0")
    assert abs(q.timestamp - NOW_MS / 1000) < 1  # milliseconds converted to seconds
    assert (q.price_increment, q.base_increment, q.minimum_base, q.minimum_quote) == (
        D("0.1"), D("0.001"), D("0.001"), D("5"))
    j = q.json()
    assert j["bid"] == "81340.2" and isinstance(j["timestamp"], float)


def test_seed_is_oldest_first_and_excludes_open_minute(market):
    market.snapshot()
    h = market.history["BTC-USDT-PERPETUAL"]
    assert h == [81002.0, 81001.0]  # open minute (81000) dropped, oldest first
    market.record(market.snapshot())
    assert h[-1] == 81340.25 and len(h) == 3
    market.snapshot()  # a second snapshot in the same tick must not re-seed or append
    assert len(market.history["BTC-USDT-PERPETUAL"]) == 3


def test_history_capped_at_120(market):
    market.snapshot()
    for _ in range(130):
        market.record(market.snapshot())
    assert len(market.history["BTC-USDT-PERPETUAL"]) == 120


def test_seed_failure_raises_seed_unavailable_not_transient(monkeypatch):
    monkeypatch.setattr(orangex, "SEED_RETRY_SECONDS", 0)
    h = Http()
    h.fail.add("bybit.com")
    with pytest.raises(SeedUnavailable):
        OrangeXMarket(PerpSettings(), h).snapshot()
    assert not issubclass(SeedUnavailable, MarketUnavailable)  # runner must NOT treat it as an outage tick


def test_seed_waits_between_attempts():
    """A refused connection fails in microseconds; without the pause all 3 tries burn in ~100 ms."""
    slept = []
    h = Http()
    h.fail.add("bybit.com")
    with mock.patch.object(orangex.time, "sleep", slept.append):
        with pytest.raises(SeedUnavailable):
            OrangeXMarket(PerpSettings(), h).snapshot()
    assert slept == [orangex.SEED_RETRY_SECONDS] * (orangex.SEED_ATTEMPTS - 1)
    assert orangex.SEED_RETRY_SECONDS > 0
    assert len([u for u in h.calls if "bybit.com" in u]) == orangex.SEED_ATTEMPTS


def test_book_failure_raises_market_unavailable(market):
    market.snapshot()
    market.http.fail.add("get_order_book")
    with pytest.raises(MarketUnavailable):
        market.snapshot()


def test_invalid_book_is_unavailable(market):
    market.snapshot()

    def bad(url):
        if "get_order_book" in url:
            return {"jsonrpc": "2.0", "error": {"code": 1000, "message": "No service found"}}
        return Http()(url)

    market.http = bad
    with pytest.raises(MarketUnavailable):
        market.snapshot()


def test_funding_live_and_fallback(market):
    rate, expire, source = market.funding()
    assert rate == D("0.000007") and expire == NOW_MS + 3600000 and source == "orangex"
    market.http.fail.add("get_funding_rate")
    rate, expire, source = market.funding()
    assert rate == D("0.0001") and source == "fallback"
    assert expire >= int(time.time() * 1000) + 8 * 3600 * 1000 - 5000


def test_frame_renders_with_label(market):
    q = market.snapshot()["BTC-USDT-PERPETUAL"]
    frame = market_frame("BTC-PERP", market.history[q.product], q.bid, q.ask)
    assert frame.shape == (180, 320, 3) and frame.dtype == np.uint8


def test_default_http_uses_no_credentials():
    import inspect
    from stonkfly.venues import orangex
    src = inspect.getsource(orangex)
    assert "Authorization" not in src and "api_key" not in src


def test_null_book_price_is_market_unavailable(market):
    market.snapshot()

    def bad(url):
        if "get_order_book" in url:
            return {"jsonrpc": "2.0", "result": {"asks": [["81340.3", "4.302"]], "bids": [[None, "4.269"]],
                                                 "timestamp": str(NOW_MS), "instrument_name": "BTC-USDT-PERPETUAL"}}
        return Http()(url)

    market.http = bad
    with pytest.raises(MarketUnavailable):
        market.snapshot()


def test_nonnumeric_book_price_is_market_unavailable(market):
    market.snapshot()

    def bad(url):
        if "get_order_book" in url:
            return {"jsonrpc": "2.0", "result": {"asks": [["N/A", "4.302"]], "bids": [["81340.2", "4.269"]],
                                                 "timestamp": str(NOW_MS), "instrument_name": "BTC-USDT-PERPETUAL"}}
        return Http()(url)

    market.http = bad
    with pytest.raises(MarketUnavailable):
        market.snapshot()


def test_malformed_mark_price_falls_back_to_mid(market):
    market.snapshot()

    def bad(url):
        if "tickers" in url:
            return {"jsonrpc": "2.0", "result": [{"mark_price": "", "last_price": "81340.2"}]}
        return Http()(url)

    market.http = bad
    q = market.snapshot()["BTC-USDT-PERPETUAL"]
    assert q.mark == (q.bid + q.ask) / 2


@pytest.mark.parametrize("rate", ["1000", "0.011", "-0.011"])
def test_out_of_range_funding_rate_falls_back(market, rate):
    """A units regression or a placeholder is not a market condition: settling "1000" would move
    cash by millions per tick and end the season in an accounting-error halt."""
    market.http.funding = {"jsonrpc": "2.0", "result": {"rate": rate, "expire_time": NOW_MS + 3600000}}
    got, expire, source = market.funding()
    assert source == "fallback" and got == D("0.0001")
    assert expire >= int(time.time() * 1000) + 8 * 3600 * 1000 - 5000


@pytest.mark.parametrize("rate", ["0.01", "-0.01", "0.000007"])
def test_in_range_funding_rate_is_kept(market, rate):
    market.http.funding = {"jsonrpc": "2.0", "result": {"rate": rate, "expire_time": NOW_MS + 3600000}}
    got, expire, source = market.funding()
    assert source == "orangex" and got == D(rate) and expire == NOW_MS + 3600000


def test_malformed_funding_rate_falls_back(market):
    market.http.funding = {"jsonrpc": "2.0", "result": {"rate": "not-a-number", "expire_time": NOW_MS + 3600000}}
    rate, expire, source = market.funding()
    assert rate == D("0.0001") and source == "fallback"
    assert expire >= int(time.time() * 1000) + 8 * 3600 * 1000 - 5000


def test_seed_malformed_close_raises_seed_unavailable():
    def bad(url):
        if "bybit.com" in url:
            data = bybit_klines()
            data["result"]["list"][1][4] = "not-a-number"  # a non-open-minute close corrupted
            return data
        return Http()(url)

    with pytest.raises(SeedUnavailable):
        OrangeXMarket(PerpSettings(), bad).snapshot()


def test_seed_single_row_raises_seed_unavailable():
    def bad(url):
        if "bybit.com" in url:
            return bybit_klines(n=1)  # only the still-open minute; rows[1:] is empty
        return Http()(url)

    with pytest.raises(SeedUnavailable):
        OrangeXMarket(PerpSettings(), bad).snapshot()


def test_fixture_swings_enough_to_liquidate_20x():
    from stonkfly.perp.fixture import FixturePerpMarket
    m = FixturePerpMarket(PerpSettings())
    mids = []
    for _ in range(40):
        q = m.snapshot()["BTC-USDT-PERPETUAL"]
        assert q.bid < q.ask and q.timestamp <= time.time()
        mids.append(float((q.bid + q.ask) / 2))
        m.record({q.product: q})
    swing = (max(mids) - min(mids)) / max(mids)
    assert swing > 0.09  # a 20x position is liquidated after ~4.5%
    assert len(m.history["BTC-USDT-PERPETUAL"]) == 120  # 80 seeded + 40 recorded, capped
    rate, expire, source = m.funding()
    assert rate == D("0.0001") and source == "fixture"
    assert m.tick == 40
