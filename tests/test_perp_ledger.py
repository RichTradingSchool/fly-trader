import dataclasses
import time

import pytest

from stonkfly.config import D
from stonkfly.perp.config import PerpSettings
from stonkfly.perp.ledger import PerpLedger
from stonkfly.venues.orangex import PerpQuote

P = "BTC-USDT-PERPETUAL"


def quote(bid="80000", ask="80000.1", **changes):
    q = PerpQuote(P, D(bid), D(ask), (D(bid) + D(ask)) / 2, time.time(),
                  D("0.1"), D("0.001"), D("0.001"), D("5"))
    return dataclasses.replace(q, **changes)


@pytest.fixture
def ledger(tmp_path):
    s = PerpSettings()
    l = PerpLedger(tmp_path / "ledger.sqlite", s)
    yield l
    l.close()


def test_initial_state(ledger):
    assert ledger.cash == D("1000") and ledger.get("initial_cash") == "1000"
    assert ledger.position is None and ledger.get("tick") == 0
    assert ledger.get("venue") == "orangex-perp" and ledger.get("mode") == "paper"
    assert ledger.get("fees_paid") == "0" and ledger.get("funding_paid") == "0"
    assert ledger.get("realized_pnl") == "0" and ledger.get("liquidations") == 0
    assert ledger.get("next_funding") == 0 and ledger.get("room_unlocked") == []
    assert ledger.get("anchor") == "1000" and ledger.get("equity") == "1000"  # dashboard reads equity
    assert ledger.equity(quote()) == D("1000") and ledger.unrealized(quote()) == D(0)
    assert ledger.liquidation_price() is None and ledger.position_view(quote()) is None


def test_settings_mismatch_rejected(tmp_path):
    l = PerpLedger(tmp_path / "l.sqlite", PerpSettings())
    l.close()
    with pytest.raises(RuntimeError, match="mismatch"):
        PerpLedger(tmp_path / "l.sqlite", PerpSettings(leverage=10))


def test_entry_size_long_uses_ask_and_33pct_20x(ledger):
    e = ledger.entry_size(quote(), "LONG")
    # margin target 330 -> notional 6600 -> qty 6600/80000.1 = 0.0824.. -> 0.082
    assert e["qty"] == D("0.082") and e["price"] == D("80000.1")
    assert e["notional"] == D("0.082") * D("80000.1")
    assert e["margin"] == e["notional"] / 20
    assert e["fee"] == e["notional"] * D("0.0006")


def test_entry_size_short_uses_bid(ledger):
    e = ledger.entry_size(quote(), "SHORT")
    assert e["price"] == D("80000")


def test_funding_due(ledger):
    assert ledger.funding_due(1_000) is True  # next_funding == 0 -> due (first fetch)
    ledger.put("next_funding", 5_000)
    assert ledger.funding_due(4_999) is False and ledger.funding_due(5_000) is True


def open_long(ledger, bid="80000", ask="80000.1"):
    return ledger.open_position("LONG", quote(bid, ask), tick=1, now=1000.0)


def test_open_long_moves_cash_and_records_fill(ledger):
    f = open_long(ledger)
    p = ledger.position
    assert p["side"] == "LONG" and D(p["qty"]) == D("0.082") and D(p["entry"]) == D("80000.1")
    notional = D("0.082") * D("80000.1")
    assert D(p["margin"]) == notional / 20 and D(p["open_fee"]) == notional * D("0.0006")
    assert ledger.cash == D("1000") - notional / 20 - notional * D("0.0006")
    assert ledger.get("fees_paid") == str(notional * D("0.0006"))
    assert f["action"] == "OPEN" and f["side"] == "LONG" and D(f["notional"]) == notional
    assert ledger.fills()[0]["id"] == f["id"] and ledger.position_view(quote())["leverage"] == 20
    assert ledger.fills(limit=0) == [] and len(ledger.fills(limit=1)) == 1  # 0 means none, not all


def test_equity_marks_long_at_bid_and_short_at_ask(ledger):
    open_long(ledger)
    q = quote("80800", "80800.1")  # +1%
    assert ledger.unrealized(q) == D("0.082") * (D("80800") - D("80000.1"))
    assert ledger.equity(q) == ledger.cash + D(ledger.position["margin"]) + ledger.unrealized(q)
    ledger.close_position(q, tick=2, now=1001.0)
    ledger.open_position("SHORT", quote("80800", "80800.1"), tick=3, now=1100.0)
    q2 = quote("80000", "80000.1")
    assert ledger.unrealized(q2) == D(ledger.position["qty"]) * (D("80800") - D("80000.1"))


def test_close_realizes_pnl_and_fee(ledger):
    open_long(ledger)
    p = ledger.position
    cash_before = ledger.cash
    q = quote("81600", "81600.1")  # +2%
    f = ledger.close_position(q, tick=2, now=1001.0, reason="signal")
    realized = D(p["qty"]) * (D("81600") - D("80000.1"))
    fee = D(p["qty"]) * D("81600") * D("0.0006")
    assert D(f["realized"]) == realized and D(f["fee"]) == fee
    assert D(f["realized_net"]) == realized - fee - D(p["open_fee"])
    assert ledger.cash == cash_before + D(p["margin"]) + realized - fee
    assert ledger.position is None and ledger.get("realized_pnl") == str(realized)


def test_roundtrip_fee_is_about_0_8pct_of_equity(ledger):
    open_long(ledger)
    ledger.close_position(quote(), tick=2, now=1001.0)
    fees = D(ledger.get("fees_paid"))
    assert D("0.0075") < fees / D("1000") < D("0.0085")


def test_flip_closes_then_opens_opposite_in_one_call(ledger):
    open_long(ledger)
    fills = ledger.flip("SHORT", quote("80400", "80400.1"), tick=5, now=1300.0)
    assert [f["action"] for f in fills] == ["FLIP_CLOSE", "FLIP_OPEN"]
    assert ledger.position["side"] == "SHORT" and D(ledger.position["entry"]) == D("80400")
    # the new margin is 33% of post-close equity
    e = fills[1]
    assert D(e["notional"]) / 20 == D(ledger.position["margin"])


def test_same_direction_open_and_close_without_position_raise(ledger):
    with pytest.raises(ValueError, match="No position"):
        ledger.close_position(quote(), tick=1, now=1.0)
    open_long(ledger)
    with pytest.raises(ValueError, match="Already positioned"):
        ledger.open_position("LONG", quote(), tick=2, now=2.0)


def test_below_minimum(ledger):
    ledger.put("cash", "3")  # 33% of 3 = ~1 USDT margin -> qty 0.00025 -> down -> 0.000 < 0.001
    with pytest.raises(ValueError, match="Below minimum"):
        open_long(ledger)
    ledger.put("cash", "4")  # 33% of 4 at ask 100000.1 -> qty 0.000 -> Below minimum
    with pytest.raises(ValueError, match="Below minimum"):
        ledger.open_position("LONG", quote("100000", "100000.1"), tick=1, now=1.0)


def test_bankrupt_records_terminal_fill(ledger):
    ledger.put("cash", "2")
    f = ledger.bankrupt(quote(), tick=9, now=9.0)
    assert f["action"] == "BANKRUPT" and f["side"] is None and D(f["qty"]) == 0
    assert ledger.get("halted") == "bankrupt" and ledger.fills()[-1]["id"] == f["id"]


def test_liquidation_loses_whole_margin_and_leaves_cash(ledger):
    open_long(ledger)
    p = ledger.position
    cash = ledger.cash
    assert ledger.liquidate_if_needed(quote("77000", "77000.1"), tick=2, now=1001.0) is None  # -3.75%: safe
    f = ledger.liquidate_if_needed(quote("76000", "76000.1"), tick=3, now=1002.0)  # -5%: gone
    assert f["action"] == "LIQUIDATION" and D(f["realized"]) == -D(p["margin"]) and D(f["fee"]) == 0
    assert ledger.cash == cash and ledger.position is None and ledger.get("liquidations") == 1
    assert D(ledger.get("realized_pnl")) == -D(p["margin"])


def test_liquidation_price_matches_rule(ledger):
    open_long(ledger)
    lp = ledger.liquidation_price()
    assert lp == D("80000.1") * (1 - D(1) / 20) / (1 - D("0.005"))
    assert ledger.liquidate_if_needed(quote(str(lp + D("0.1")), str(lp + D("0.2"))), 2, 1.0) is None
    assert ledger.liquidate_if_needed(quote(str(lp - D("0.1")), str(lp)), 3, 2.0) is not None


def test_short_liquidates_on_rally(ledger):
    ledger.open_position("SHORT", quote(), tick=1, now=1.0)
    assert ledger.liquidate_if_needed(quote("83000", "83000.1"), 2, 2.0) is None  # +3.75%
    assert ledger.liquidate_if_needed(quote("84200", "84200.1"), 3, 3.0)["action"] == "LIQUIDATION"


def test_funding_long_pays_short_receives_and_negative_rate(ledger):
    open_long(ledger)
    p = ledger.position
    cash = ledger.cash
    f = ledger.apply_funding(D("0.0001"), 9_000, "orangex", quote(), tick=2, now=1.0)
    amount = D(p["qty"]) * D("80000") * D("0.0001")  # mark = bid for a long
    assert f["action"] == "FUNDING" and D(f["fee"]) == amount and f["reason"] == "orangex:0.0001"
    assert ledger.cash == cash - amount and ledger.get("funding_paid") == str(amount)
    assert ledger.get("next_funding") == 9_000
    ledger.close_position(quote(), 3, 2.0)
    ledger.open_position("SHORT", quote(), 4, 3.0)
    cash = ledger.cash
    ledger.apply_funding(D("0.0001"), 10_000, "orangex", quote(), 5, 4.0)
    assert ledger.cash == cash + D(ledger.position["qty"]) * D("80000.1") * D("0.0001")
    cash = ledger.cash
    ledger.apply_funding(D("-0.0002"), 11_000, "fallback", quote(), 6, 5.0)
    assert ledger.cash < cash  # negative rate: shorts pay


def test_funding_without_position_only_advances_schedule(ledger):
    now = 1_700_000_000.0
    now_ms, interval = int(now * 1000), 8 * 3600 * 1000
    assert ledger.apply_funding(D("0.0001"), now_ms + interval, "orangex", quote(), 1, now) is None
    assert ledger.get("next_funding") == now_ms + interval and ledger.cash == D("1000")
    # A boundary that already passed (rollover lag, or seconds where ms were meant) must not leave
    # the schedule permanently due: it is pushed one whole interval past now instead.
    assert ledger.apply_funding(D("0.0001"), now_ms - 1, "orangex", quote(), 2, now) is None
    assert ledger.get("next_funding") == now_ms + interval
    assert ledger.funding_due(now_ms) is False


def test_past_funding_expiry_settles_once_and_rearms_forward(ledger):
    """The 480x bug: with next_funding pinned in the past, every 60 s tick settled funding again."""
    open_long(ledger)
    now = 1_700_000_000.0
    now_ms, interval = int(now * 1000), 8 * 3600 * 1000
    cash = ledger.cash
    f = ledger.apply_funding(D("0.0001"), now_ms - 5_000, "orangex", quote(), tick=2, now=now)
    assert f is not None and ledger.cash < cash  # this settlement still happens
    assert ledger.get("next_funding") == now_ms + interval
    assert ledger.funding_due(now_ms) is False  # the next tick is not due again
    assert ledger.funding_due(now_ms + interval) is True


def test_bankruptcy(ledger):
    assert ledger.is_bankrupt(quote()) is False
    # margin down(12.12*0.33,0.01)=3.99 -> notional 79.80 -> qty 0.000 on LONG (ask 80000.1) and SHORT (bid 80000)
    ledger.put("cash", "12.12")
    assert ledger.is_bankrupt(quote()) is True
    with pytest.raises(ValueError, match="Below minimum"):
        ledger.open_position("LONG", quote(), 1, 1.0)
    with pytest.raises(ValueError, match="Below minimum"):
        ledger.open_position("SHORT", quote(), 1, 1.0)
    # margin down(12.13*0.33,0.01)=4.00 -> notional 80.00: SHORT clears at bid 80000 (80.00/80000 == 0.001
    # exactly) while LONG still doesn't (80.00/80000.1 < 0.001) -> not bankrupt because SHORT alone can open
    ledger.put("cash", "12.13")
    assert ledger.is_bankrupt(quote()) is False
    ledger.open_position("SHORT", quote(), 1, 1.0)
    ledger.put("cash", "0")
    assert ledger.is_bankrupt(quote()) is False  # margin still on the table


def test_fixture_market_liquidates_a_long_within_20_ticks(tmp_path):
    from stonkfly.perp.fixture import FixturePerpMarket
    s = PerpSettings()
    l = PerpLedger(tmp_path / "l.sqlite", s)
    m = FixturePerpMarket(s)
    q0 = m.snapshot()[P]
    l.open_position("LONG", q0, 1, 1.0)
    liquidated = []
    for tick in range(2, 22):
        q = m.snapshot()[P]
        if l.liquidate_if_needed(q, tick, float(tick)):
            liquidated.append(tick)
    assert len(liquidated) == 1 and liquidated[0] <= 21
    assert l.position is None and l.get("liquidations") == 1
    l.close()


def test_fill_transaction_is_atomic(ledger, monkeypatch):
    open_long(ledger)
    cash, pos = ledger.cash, ledger.position
    calls = {"n": 0}
    real = ledger._insert_fill

    def boom(*a, **k):
        calls["n"] += 1
        raise RuntimeError("disk full")

    monkeypatch.setattr(ledger, "_insert_fill", boom)
    with pytest.raises(RuntimeError):
        ledger.close_position(quote(), 2, 1.0)
    assert ledger.cash == cash and ledger.position == pos and calls["n"] == 1
