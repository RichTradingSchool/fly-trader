import importlib.util
import json
import threading
from pathlib import Path

import pytest

from stonkfly.perp.config import PerpSettings
from stonkfly.perp.ledger import PerpLedger

SPEC = importlib.util.spec_from_file_location("perp_state", Path("dashboard/perp_state.py"))
ps = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ps)

NEURAL = {"side": "BUY", "left_hz": 10.0, "right_hz": 14.0, "difference_hz": 4.0, "gate_spikes": 3,
          "stimulus": "none", "reward_spikes": 0, "aversive_spikes": 0, "KC_spikes": 100, "total_spikes": 5000,
          "compute_seconds": 7.5, "memory": {"changed_edges": 12, "mean_efficacy": 0.99, "minimum_efficacy": 0.5}}


def row(tick, execution, **extra):
    base = {"tick": tick, "wall_time": 1000.0 + tick, "product": "BTC-USDT-PERPETUAL", "mode": "paper",
            "venue": "orangex-perp", "quote": {"bid": "80000", "ask": "80000.1"}, "equity_usdt": "1000", "equity_usdc": "1000",
            "pnl_delta_usdt": "0", "pnl_delta_usdc": "0", "neural": NEURAL, "execution": execution, "veto": None,
            "position": None, "fees_paid": "0", "funding_paid": "0", "realized_pnl": "0", "liquidations": 0,
            "funding": None, "liquidation": None, "room_events": [], "outage_ticks": 0}
    base.update(extra)
    return json.dumps(base)


def test_tail_lines(tmp_path):
    p = tmp_path / "e.jsonl"
    assert ps.tail_lines(p, 5) == []
    p.write_text("\n".join(f"line{i}" for i in range(1000)))  # no trailing newline
    assert ps.tail_lines(p, 3) == ["line997", "line998", "line999"]
    assert len(ps.tail_lines(p, 5000)) == 1000
    p.write_text("a\nb\n")
    assert ps.tail_lines(p, 10) == ["a", "b"]


def test_perp_events_maps_fields_and_skips_veto_rows():
    fills = [{"action": "FLIP_CLOSE", "realized_net": "-3.5"}, {"action": "FLIP_OPEN", "realized_net": "0"}]
    lines = [
        row(1, {"status": "HOLD"}),
        json.dumps({"tick": 1, "wall_time": 1002.0, "product": "BTC-USDT-PERPETUAL", "mode": "paper", "venue": "orangex-perp",
                    "quote": None, "neural": None, "veto": "Stale or future quote",
                    "execution": {"status": "VETO", "reason": "Stale or future quote"}, "equity_usdt": None,
                    "position": None, "fees_paid": "0", "funding_paid": "0", "realized_pnl": "0", "liquidations": 0,
                    "funding": None, "liquidation": None, "room_events": [], "outage_ticks": 1}),
        row(2, {"status": "FILLED", "action": "FLIP", "side": "SHORT", "fills": fills},
            position={"side": "SHORT", "qty": "0.082"}, room_events=[{"type": "unlock", "item": "coffee_machine", "label": "커피머신", "equity_threshold": 1200}],
            liquidation=None),
        row(3, {"status": "VETO", "reason": "Already positioned"}, liquidation={"action": "LIQUIDATION", "realized_net": "-330"}),
    ]
    ev = ps.perp_events(lines)
    assert [e["tick"] for e in ev] == [1, 2, 3] and ps.veto_count(lines) == 1
    assert ev[0]["execution"] == "HOLD" and ev[0]["bid"] == "80000" and ev[0]["equity"] == 1000.0
    assert ev[1]["execution"] == "FILLED" and ev[1]["action"] == "FLIP" and ev[1]["fills"] == fills
    assert ev[1]["trade_pnl"] == -3.5 and ev[1]["position"]["side"] == "SHORT"
    assert ev[1]["room_events"][0]["item"] == "coffee_machine"
    assert ev[2]["reason"] == "Already positioned" and ev[2]["trade_pnl"] == -330.0 and ev[2]["liquidation"]["action"] == "LIQUIDATION"
    assert ev[2]["compute"] == 7.5 and ev[2]["changed_edges"] == 12


def test_perp_ledger_and_fly_name(tmp_path):
    l = PerpLedger(tmp_path / "ledger.sqlite", PerpSettings(fly_name="버즈"))
    l.put("liquidations", 2)
    l.close()
    d = ps.perp_ledger(tmp_path)
    assert d["venue"] == "orangex-perp" and d["liquidations"] == 2 and d["cash"] == "1000" and d["room_unlocked"] == []
    assert ps.perp_ledger(tmp_path / "nowhere") == {}
    assert ps.fly_name(tmp_path) == "초파리"
    (tmp_path / "provenance.json").write_text(json.dumps({"perp_settings": {"fly_name": "버즈"}}))
    assert ps.fly_name(tmp_path) == "버즈"


def test_room_recent_orders_and_limits():
    lines = [row(i, {"status": "HOLD"}, room_events=[{"type": "unlock", "item": f"i{i}", "label": f"L{i}", "equity_threshold": 1}]) for i in range(30)]
    r = ps.room_recent(lines, limit=5)
    assert [x["tick"] for x in r] == [25, 26, 27, 28, 29] and r[-1]["item"] == "i29" and r[-1]["type"] == "unlock"


def test_perp_trade_pnl_and_fills_today(tmp_path):
    import time
    from decimal import Decimal as D
    from stonkfly.venues.orangex import PerpQuote
    P = "BTC-USDT-PERPETUAL"

    def quote(bid, ask, ts):
        return PerpQuote(P, D(bid), D(ask), (D(bid) + D(ask)) / 2, ts, D("0.1"), D("0.001"), D("0.001"), D("5"))

    now = time.time()  # both fills at the same wall time so a UTC-midnight boundary cannot split them
    l = PerpLedger(tmp_path / "ledger.sqlite", PerpSettings())
    l.open_position("LONG", quote("80000", "80000.1", now), 1, now)
    l.flip("SHORT", quote("79000", "79000.1", now), 2, now)
    l.close()
    pnl = ps.perp_trade_pnl(tmp_path)
    assert list(pnl) == [2] and pnl[2] < 0  # FLIP_CLOSE at tick 2 lost money
    assert ps.fills_today(tmp_path, now) == 2  # OPEN + FLIP_OPEN
    assert ps.fills_today(tmp_path, now + 86400 * 2) == 0
    assert ps.perp_trade_pnl(tmp_path / "nowhere") == {} and ps.fills_today(tmp_path / "nowhere", now) == 0
    # the fills table wins over the event row when both exist
    lines = [json.dumps({**json.loads(row(2, {"status": "FILLED", "action": "FLIP", "side": "SHORT",
                                              "fills": [{"action": "FLIP_CLOSE", "realized_net": "-1"}]}))})]
    assert ps.perp_events(lines, pnl)[0]["trade_pnl"] == pnl[2]


def quote(bid, ask, ts):
    from decimal import Decimal as D

    from stonkfly.venues.orangex import PerpQuote
    return PerpQuote("BTC-USDT-PERPETUAL", D(bid), D(ask), (D(bid) + D(ask)) / 2, ts,
                     D("0.1"), D("0.001"), D("0.001"), D("5"))


def test_fills_today_counts_the_local_day_not_the_utc_one(tmp_path):
    day = 1790000000 // 86400 * 86400  # a UTC midnight
    early, late = day + 14 * 3600, day + 23 * 3600 + 1800  # 23:00 KST of D, 08:30 KST of D+1
    lg = PerpLedger(tmp_path / "ledger.sqlite", PerpSettings())
    lg.open_position("LONG", quote("80000", "80000.1", early), 1, early)
    lg.flip("SHORT", quote("79000", "79000.1", late), 2, late)
    lg.close()
    assert ps.fills_today(tmp_path, late) == 1  # KST default: only the 08:30 KST entry is today
    assert ps.fills_today(tmp_path, late, 0) == 2  # UTC: both entries fall on the same day
    assert ps.fills_today(tmp_path, day + 15 * 3600) == 1  # exactly KST midnight of D+1


def test_perp_events_skips_rows_it_cannot_map():
    no_equity = json.loads(row(2, {"status": "HOLD"}))
    no_equity["equity_usdt"] = None  # the brain observed, the ledger read did not
    missing = json.loads(row(3, {"status": "HOLD"}))
    del missing["pnl_delta_usdt"]
    ev = ps.perp_events([row(1, {"status": "HOLD"}), json.dumps(no_equity), json.dumps(missing),
                         row(4, {"status": "HOLD"})])
    assert [e["tick"] for e in ev] == [1, 4]  # one bad row must not 500 /state.json for hours


def test_venue_of_prefers_provenance_then_ledger_meta(tmp_path):
    prov = tmp_path / "prov"
    prov.mkdir()
    (prov / "provenance.json").write_text(json.dumps({"venue": "orangex-perp"}), encoding="utf-8")
    assert ps.venue_of(prov) == "orangex-perp"
    (prov / "provenance.json").write_text(json.dumps({"perp_settings": {"leverage": 20}}), encoding="utf-8")
    assert ps.venue_of(prov) == "orangex-perp"  # perp_settings alone identifies the venue
    meta = tmp_path / "meta"
    meta.mkdir()
    PerpLedger(meta / "ledger.sqlite", PerpSettings()).close()
    assert ps.venue_of(meta) == "orangex-perp"  # no provenance: the ledger meta answers
    empty = tmp_path / "empty"
    empty.mkdir()
    assert ps.venue_of(empty) == "coinbase-spot"


def test_perp_settings_exposes_leverage_and_fly_name(tmp_path):
    assert ps.perp_settings(tmp_path) == {"leverage": 20, "fly_name": "초파리"}
    (tmp_path / "provenance.json").write_text(
        json.dumps({"perp_settings": {"leverage": 50, "fly_name": "버즈"}}), encoding="utf-8")
    assert ps.perp_settings(tmp_path) == {"leverage": 50, "fly_name": "버즈"}
    (tmp_path / "provenance.json").write_text(
        json.dumps({"perp_settings": {"fly_name": None}}), encoding="utf-8")
    assert ps.perp_settings(tmp_path) == {"leverage": 20, "fly_name": "초파리"}  # null is not "None"


def test_perp_settings_passes_capital_and_margin_for_the_explainer(tmp_path):
    (tmp_path / "provenance.json").write_text(json.dumps({"perp_settings": {
        "leverage": 10, "fly_name": "버즈", "capital": "500", "margin_fraction": "0.25", "taker_fee": "0.0006"}}),
        encoding="utf-8")
    assert ps.perp_settings(tmp_path) == {"leverage": 10, "fly_name": "버즈", "capital": "500", "margin_fraction": "0.25"}


def test_room_recent_with_zero_limit_returns_nothing():
    lines = [row(1, {"status": "HOLD"},
                 room_events=[{"type": "unlock", "item": "i", "label": "L", "equity_threshold": 1}])]
    assert ps.room_recent(lines, limit=0) == []  # out[-0:] would return every event
    assert len(ps.room_recent(lines, limit=1)) == 1


def _season_line(tick, **extra):
    return row(tick, {"status": "HOLD"}, quote={"bid": str(80000 + tick), "ask": str(80001 + tick)},
               equity_usdt=str(1000 + tick), **extra)


def test_season_series_anchors_samples_and_reads_incrementally(tmp_path):
    p = tmp_path / "events.jsonl"
    assert ps.season_series(p) == {"seed_bid": None, "points": []}
    skipped = json.dumps({**json.loads(_season_line(1)), "neural": None, "quote": None, "equity_usdt": None})
    body = [skipped] + [_season_line(t) for t in range(1, 13)]
    body[8] = _season_line(8, liquidation={"action": "LIQUIDATION", "realized_net": "-330"})
    p.write_text("\n".join(body) + "\n", encoding="utf-8")

    s = ps.season_series(p, every=5)
    assert s["seed_bid"] == 80001.0  # the quote-failure row carries no price, so it cannot anchor
    assert [q["tick"] for q in s["points"]] == [1, 6, 8, 11]  # every 5th observation + the liquidation
    assert s["points"][2]["liq"] is True and s["points"][0]["equity"] == 1001.0

    with p.open("a", encoding="utf-8") as f:
        f.write("\n".join(_season_line(t) for t in range(13, 17)) + "\n")
    assert [q["tick"] for q in ps.season_series(p, every=5)["points"]] == [1, 6, 8, 11, 16]

    tail = "\n".join(_season_line(t) for t in range(17, 22)) + "\n"
    cut = len(tail) - 30
    with p.open("a", encoding="utf-8") as f:
        f.write(tail[:cut])  # a crash mid-write leaves the last line incomplete
    assert [q["tick"] for q in ps.season_series(p, every=5)["points"]] == [1, 6, 8, 11, 16]
    with p.open("a", encoding="utf-8") as f:
        f.write(tail[cut:])
    assert [q["tick"] for q in ps.season_series(p, every=5)["points"]] == [1, 6, 8, 11, 16, 21]

    p.write_text(_season_line(1) + "\n", encoding="utf-8")  # a new season reusing the same path
    assert [q["tick"] for q in ps.season_series(p, every=5)["points"]] == [1]


def test_season_series_caps_and_thins(tmp_path):
    p = tmp_path / "events.jsonl"
    p.write_text("\n".join(_season_line(t) for t in range(1, 2600)) + "\n", encoding="utf-8")
    s = ps.season_series(p, every=1)
    ticks = [q["tick"] for q in s["points"]]
    assert len(ticks) <= ps.MAX_SEASON_POINTS
    assert ticks[:3] == [1, 3, 5] and ticks[-1] >= 2500  # thinned to every other point, still current


def test_season_series_is_thread_safe_on_a_cold_cache(tmp_path):
    """The dashboard is a ThreadingHTTPServer: concurrent /state.json polls can all
    observe a cold (or stale) cache entry for the same events.jsonl at once and race
    to read+update it, double-counting points or drifting the parsed offset. The
    lock around season_series must serialize that race so 8 threads hitting a cold
    cache together land on exactly the points a single-threaded read would produce.
    """
    body = "\n".join(_season_line(t) for t in range(1, 601)) + "\n"

    single = tmp_path / "single.jsonl"
    single.write_text(body, encoding="utf-8")
    reference = ps.season_series(single, every=10)
    ref_ticks = [q["tick"] for q in reference["points"]]
    assert len(ref_ticks) > 1  # a meaningless test if there is nothing to race over

    concurrent_path = tmp_path / "concurrent.jsonl"
    concurrent_path.write_text(body, encoding="utf-8")

    n = 8
    results = [None] * n
    barrier = threading.Barrier(n)

    def worker(i):
        barrier.wait()  # line every thread up so they hit the cold cache together
        results[i] = ps.season_series(concurrent_path, every=10)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for r in results:
        assert [q["tick"] for q in r["points"]] == ref_ticks
        assert r["seed_bid"] == reference["seed_bid"]
