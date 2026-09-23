import gzip
import importlib.util
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from test_dashboard_server import RUN, get, server  # noqa: F401  (module-scoped server fixture)

needs_run = pytest.mark.skipif(not (RUN / "events.jsonl").exists() or not Path("data/graph.npz").exists(),
                               reason="needs runs/fixture-perp from the engine plan and prepared data")
spec = importlib.util.spec_from_file_location("live_feed", Path("dashboard/live_feed.py"))
live_feed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live_feed)


def event(tick, **extra):
    base = {"tick": tick, "time": 1000.0 + tick * 60, "bid": "86000.0", "equity": 1000.0, "pnl": 0.0, "side": "HOLD",
            "left_hz": 30.04, "right_hz": 31.06, "gate": 1, "stimulus": "none", "reward_spikes": 0, "aversive_spikes": 0,
            "execution": "HOLD", "reason": None, "fills": [], "liquidation": None, "funding": None, "position": None,
            "room_events": [], "kc_spikes": 99, "total_spikes": 12345, "compute": 7.5, "product": "BTC-USDT-PERPETUAL"}
    base.update(extra)
    return base


def test_slim_event_keeps_what_the_studio_reads_and_drops_the_rest():
    e = event(5, fills=[{"action": "OPEN", "side": "LONG", "price": "1", "qty": "0.1", "realized_net": "0", "quote": {"x": 1}}],
              position={"side": "LONG", "qty": "0.1", "entry": "1", "margin": "3", "unrealized": "0", "leverage": 20,
                        "liquidation_price": "82081.43216080402", "opened_at": 1, "mark": "2"})
    s = live_feed.slim_event(e)
    for k in ["tick", "time", "bid", "equity", "side", "left_hz", "right_hz", "gate", "execution", "fills", "position", "room_events"]:
        assert k in s, k
    assert "kc_spikes" not in s and "compute" not in s and "product" not in s
    assert s["fills"][0] == {"action": "OPEN", "side": "LONG", "price": "1", "qty": "0.1", "realized_net": "0"}
    assert s["position"]["liquidation_price"] == 82081.4 and "mark" not in s["position"]
    assert s["left_hz"] == 30.0


def test_thin_points_keeps_ends_and_every_liquidation():
    pts = [{"tick": i, "time": i, "equity": 1000 + i, "bid": 1.0, "liq": i in (7, 1234), "bankrupt": i == 1999} for i in range(2000)]
    out = live_feed.thin_points(pts, limit=100)
    ticks = [p["tick"] for p in out]
    assert ticks[0] == 0 and ticks[-1] == 1999
    assert 7 in ticks and 1234 in ticks
    assert len(out) <= 104 and ticks == sorted(ticks)


def test_live_payload_caps_events_and_collects_trades():
    events = [event(i) for i in range(400)]
    events[10]["fills"] = [{"action": "OPEN", "side": "SHORT", "price": "1", "qty": "1", "realized_net": "0"}]
    events[20]["funding"] = {"side": "SHORT", "fee": "0.05", "realized_net": "-0.05", "quote": {}}
    p = live_feed.live_payload({"events": events, "ledger": {"equity": 1, "cash": 2, "halted": None}, "season": {"points": []}})
    assert len(p["events"]) == live_feed.MAX_EVENTS and p["events"][-1]["tick"] == 399
    assert [e["tick"] for e in p["notable"]] == [10, 20]
    assert "cash" not in p["ledger"] and "halted" in p["ledger"]
    assert live_feed.current_tick({"events": events}) == 399


def raw(url, method="GET", headers=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


@needs_run
def test_tick_and_versioned_live_feed(server):  # noqa: F811
    _, h, body = get(server + "/tick.json")
    t = json.loads(body)
    assert t["v"] and isinstance(t["now"], float) and "tick" in t
    assert h["Access-Control-Allow-Origin"] == "*" and h["Cache-Control"] == "no-store"
    st, h, body = raw(f"{server}/live.json?v={t['v']}", headers={"Accept-Encoding": "gzip"})
    assert st == 200 and h["Cache-Control"] == "public, max-age=31536000, immutable"
    assert h["Content-Encoding"] == "gzip" and h["Vary"] == "Accept-Encoding"
    live = json.loads(gzip.decompress(body))
    assert live["events"] and "notable" in live and "now" not in live
    assert live["settings"]["leverage"] == 20
    _, h, _ = get(server + "/live.json")
    assert h["Cache-Control"] == "no-store"
    _, h, _ = get(server + "/live.json?v=stale")
    assert h["Cache-Control"] == "no-store"


@needs_run
def test_state_json_keeps_a_fresh_clock(server):  # noqa: F811
    st, h, body = raw(server + "/state.json", headers={"Accept-Encoding": "gzip"})
    s = json.loads(gzip.decompress(body))
    assert st == 200 and h["Content-Encoding"] == "gzip" and s["now"] > 1e9 and s["events"]


@needs_run
def test_room_redirects_to_a_folder_and_keeps_the_query(server):  # noqa: F811
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    with pytest.raises(urllib.error.HTTPError) as e:
        opener.open(server + "/room?stream=1", timeout=10)
    assert e.value.code == 301 and e.value.headers["Location"] == "/room/?stream=1"
    st, _, body = raw(server + "/room/")
    page = body.decode()
    assert st == 200 and 'src="app.js"' in page and "<!--SITE-CONFIG-->" in page
    assert '"/room/' not in page and 'url("/assets' not in page, "studio assets must be relative"


@needs_run
def test_cors_preflight_head_and_static_gzip(server):  # noqa: F811
    st, h, _ = raw(server + "/live.json", method="OPTIONS")
    assert st == 204 and h["Access-Control-Allow-Origin"] == "*" and "GET" in h["Access-Control-Allow-Methods"]
    st, h, body = raw(server + "/tick.json", method="HEAD")
    assert st == 200 and body == b"" and int(h["Content-Length"]) > 0
    st, h, body = raw(server + "/pos.bin", headers={"Accept-Encoding": "gzip"})
    assert st == 200 and h["Content-Encoding"] == "gzip" and h["Cache-Control"] == "max-age=3600"
    assert len(gzip.decompress(body)) % 12 == 0
