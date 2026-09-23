import dataclasses
import time

import pytest

from stonkfly.config import D, down
from stonkfly.perp.actions import PerpActions
from stonkfly.perp.broker import PerpPaperBroker
from stonkfly.perp.config import PerpSettings
from stonkfly.perp.ledger import PerpLedger
from stonkfly.perp.risk import PerpGuard, Veto
from stonkfly.venues.orangex import PerpQuote

P = "BTC-USDT-PERPETUAL"


def quote(bid="80000", ask="80000.1", **changes):
    q = PerpQuote(P, D(bid), D(ask), (D(bid) + D(ask)) / 2, time.time(),
                  D("0.1"), D("0.001"), D("0.001"), D("5"))
    return dataclasses.replace(q, **changes)


@pytest.fixture
def env(tmp_path):
    s = PerpSettings()
    l = PerpLedger(tmp_path / "ledger.sqlite", s)
    g = PerpGuard(s, l, tmp_path / "STOP")
    a = PerpActions(g, PerpPaperBroker(s, l))
    a.quotes = {P: quote()}
    yield s, l, g, a
    l.close()


@pytest.mark.parametrize("changes,message", [
    # The runner routes on the exact text: "Stale or future quote" is a clock problem, counted
    # separately from an outage, so these strings are part of the contract.
    (dict(timestamp=time.time() - 100), "Stale or future quote"),
    (dict(timestamp=time.time() + 100), "Stale or future quote"),
    (dict(ask=D("80500")), "Spread limit"),
])
def test_check_vetoes_bad_quotes(env, changes, message):
    _, _, g, _ = env
    with pytest.raises(Veto, match=message):
        g.check({P: quote(**changes)}, time.time())


def test_check_vetoes_stop_halt_and_incomplete(env):
    _, l, g, _ = env
    g.stop_file.touch()
    with pytest.raises(Veto, match="STOP"):
        g.check({P: quote()}, time.time())
    g.stop_file.unlink()
    l.halt("market-outage")
    with pytest.raises(Veto, match="market-outage"):
        g.check({P: quote()}, time.time())
    l.put("halted", None)
    with pytest.raises(Veto, match="Incomplete"):
        g.check({}, time.time())


def test_plan_open_then_same_side_veto_then_flip(env):
    # The freshness gate compares `now` with quote.timestamp, so every quote is stamped with the injected clock.
    _, l, g, _ = env
    t = time.time()
    p = g.plan(P, "LONG", {P: quote(timestamp=t)}, now=t)
    assert p["action"] == "OPEN" and p["side"] == "LONG" and p["quote"]["ask"] == "80000.1"
    l.open_position("LONG", quote(), 1, t)
    l.put("last_attempt", t)
    with pytest.raises(Veto, match="Order cooldown"):
        g.plan(P, "SHORT", {P: quote(timestamp=t + 30)}, now=t + 30)
    with pytest.raises(Veto, match="Already positioned"):
        g.plan(P, "LONG", {P: quote(timestamp=t + 61)}, now=t + 61)
    # Unchanged price: closing now costs the close fee plus the sunk open fee, so the flip waits.
    with pytest.raises(Veto, match="Below breakeven"):
        g.plan(P, "SHORT", {P: quote(timestamp=t + 61)}, now=t + 61)
    p = g.plan(P, "SHORT", {P: quote("80200", "80200.1", timestamp=t + 61)}, now=t + 61)
    assert p["action"] == "FLIP" and p["side"] == "SHORT"


def test_plan_below_minimum_and_invalid(env):
    _, l, g, _ = env
    l.put("cash", "3")
    t = time.time()  # last_attempt is 0, so the 60 s cooldown cannot fire before the size check
    with pytest.raises(Veto, match="Below minimum"):
        g.plan(P, "LONG", {P: quote(timestamp=t)}, now=t)
    with pytest.raises(Veto, match="Invalid"):
        g.plan(P, "BUY", {P: quote(timestamp=t)}, now=t)
    with pytest.raises(Veto, match="Invalid"):
        g.plan("ETH-USDT-PERPETUAL", "LONG", {P: quote(timestamp=t)}, now=t)


def test_actions_map_buy_sell_and_fill(env):
    s, l, g, a = env
    r = a.invoke({"product": P, "side": "BUY"})
    assert r["status"] == "FILLED" and r["action"] == "OPEN" and r["side"] == "LONG"
    assert len(r["fills"]) == 1 and l.position["side"] == "LONG"
    assert l.get("last_attempt") > 0
    with pytest.raises(Veto, match="cooldown"):
        a.invoke({"product": P, "side": "SELL"})
    l.put("last_attempt", 0)
    with pytest.raises(Veto, match="Below breakeven"):
        a.invoke({"product": P, "side": "SELL"})  # still the entry price: a flip would realize a fee loss
    a.quotes = {P: quote("80200", "80200.1")}
    r = a.invoke({"product": P, "side": "SELL"})
    assert r["action"] == "FLIP" and [f["action"] for f in r["fills"]] == ["FLIP_CLOSE", "FLIP_OPEN"]
    assert l.position["side"] == "SHORT"
    with pytest.raises(Veto):
        a.invoke({"product": P, "side": "HOLD"})


def held(side="LONG", open_fee="99.88", **changes):
    """A hand-built position with round numbers: closing 1 unit bought at 100 against a 200 bid
    grosses +100 and pays 200 x 0.0006 = 0.12 to close, so `open_fee` alone sets the close net.
    Margin 5 and the untouched 1,000 USDT of cash then fix the re-entry the flip would pay for."""
    return {"side": side, "qty": "1", "entry": "100", "margin": "5", "notional": "100",
            "open_fee": open_fee, "opened_tick": 1, "opened_at": 0.0, **changes}


def reentry_fee(s, post_equity):
    """The fee the guard charges the re-entry, from the same constants `entry_size` sizes with."""
    return down(D(post_equity) * D(s.margin_fraction), D("0.01")) * s.leverage * D(s.taker_fee)


def test_flip_vetoed_while_the_close_is_below_fee_breakeven(env):
    _, l, g, _ = env
    t = time.time()
    l.open_position("LONG", quote(), 1, t)
    # A loser: the price fell 1,000 USDT against a long entered at 80,000.1.
    q = quote("79000", "79000.1", timestamp=t)
    assert l.projected_close_net(q) < 0
    with pytest.raises(Veto, match="Below breakeven"):
        g.plan(P, "SHORT", {P: q}, now=t)


def test_a_close_that_only_pays_for_itself_is_not_enough(env):
    """A close net of exactly 0 still sinks the new entry's fee, so it is not a round trip."""
    s, l, g, _ = env
    t = time.time()
    q = quote("200", "200.1", timestamp=t)
    l.put("position", held(open_fee="99.88"))  # close net exactly 0
    assert l.projected_close_net(q) == D(0)
    assert l.projected_flip_net(q) == -reentry_fee(s, l.cash + D(5))
    with pytest.raises(Veto, match="Below breakeven"):
        g.plan(P, "SHORT", {P: q}, now=t)


def test_flip_allowed_at_exactly_breakeven_and_when_winning(env):
    s, l, g, _ = env
    t = time.time()
    q = quote("200", "200.1", timestamp=t)
    # The break-even point is the fixed point of "close net == re-entry fee": a close net of
    # 3.99552 leaves 1,008.99552 of equity, which sizes to 6,659.2 notional and 3.99552 of fee.
    l.put("position", held(open_fee="95.88448"))
    net = l.projected_close_net(q)
    assert net == D("3.99552") == reentry_fee(s, l.cash + D(5) + net)
    assert l.projected_flip_net(q) == D(0)
    assert g.plan(P, "SHORT", {P: q}, now=t)["action"] == "FLIP"
    l.put("position", held(open_fee="95.88449"))  # one satoshi-cent short of the fixed point
    assert l.projected_flip_net(q) == D("-0.00001")
    with pytest.raises(Veto, match="Below breakeven"):
        g.plan(P, "SHORT", {P: q}, now=t)
    l.put("position", held(open_fee="0.88"))  # a real winner: close net +99
    assert l.projected_close_net(q) == D(99)
    assert l.projected_flip_net(q) == D(99) - reentry_fee(s, l.cash + D(5) + D(99))
    assert g.plan(P, "SHORT", {P: q}, now=t)["action"] == "FLIP"


def test_flip_min_net_demands_more_than_breakeven(tmp_path):
    s = PerpSettings(flip_min_net="5")
    l = PerpLedger(tmp_path / "ledger.sqlite", s)
    g = PerpGuard(s, l, tmp_path / "STOP")
    t = time.time()
    q = quote("200", "200.1", timestamp=t)
    l.put("position", held(open_fee="92.87248"))  # close net 7.00752, re-entry 4.00752 -> flip +3
    assert l.projected_flip_net(q) == D(3)
    with pytest.raises(Veto, match="Below breakeven"):
        g.plan(P, "SHORT", {P: q}, now=t)
    l.put("position", held(open_fee="90.86456"))  # close net 9.01544, re-entry 4.01544 -> flip +5
    assert l.projected_flip_net(q) == D(5)  # the floor itself passes
    assert g.plan(P, "SHORT", {P: q}, now=t)["action"] == "FLIP"
    l.close()


def test_projected_close_net_equals_the_realized_net_recorded(env):
    """The guard predicts with the same arithmetic the fill is written with, on both sides."""
    _, l, _, _ = env
    t = time.time()
    l.open_position("LONG", quote(), 1, t)
    q = quote("80200", "80200.1", timestamp=t)
    projected = l.projected_close_net(q)
    closed, _opened = l.flip("SHORT", q, 2, t)
    assert D(closed["realized_net"]) == projected
    q2 = quote("79000", "79000.1", timestamp=t)  # the SHORT now closes at the ask
    projected2 = l.projected_close_net(q2)
    assert D(l.close_position(q2, 3, t)["realized_net"]) == projected2


def test_projected_flip_net_tracks_the_recorded_round_trip(env):
    s, l, _, _ = env
    t = time.time()
    l.open_position("LONG", quote(), 1, t)
    q = quote("80200", "80200.1", timestamp=t)
    projected = l.projected_flip_net(q)
    closed, opened = l.flip("SHORT", q, 2, t)
    recorded = D(closed["realized_net"]) - D(opened["fee"])
    # The close half is exact; the re-entry half is a forecast that skips the 0.001 BTC lot
    # rounding and leaves the sunk open fee out of the equity it sizes on. One lot of taker fee
    # is the whole budget for the gap, and here the forecast lands 0.032 USDT conservative.
    assert D("0") < recorded - projected <= D("0.001") * D("80200") * D(s.taker_fee)


def test_broker_never_touches_network():
    import inspect
    from stonkfly.perp import actions, broker, risk
    for m in (actions, broker, risk):
        src = inspect.getsource(m)
        assert "urllib" not in src and "coinbase" not in src and "requests" not in src
