import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

RUN = Path("runs/fixture-perp")
pytestmark = pytest.mark.skipif(not (RUN / "events.jsonl").exists() or not Path("data/graph.npz").exists(),
                                reason="needs runs/fixture-perp from the engine plan and prepared data")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def server():
    port = free_port()
    env = {**os.environ, "PORT": str(port)}
    proc = subprocess.Popen([sys.executable, "dashboard/server.py", str(RUN)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    deadline = time.time() + 180  # first start builds dashboard/cache
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/flies.json", timeout=2)
            break
        except Exception:
            if proc.poll() is not None:
                raise RuntimeError(proc.stdout.read())
            time.sleep(1)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, r.headers, r.read()


def test_state_has_perp_fields(server):
    _, _, body = get(server + "/state.json")
    s = json.loads(body)
    assert s["venue"] == "orangex-perp" and s["fly_name"]
    assert "position" in s["ledger"] and "liquidations" in s["ledger"]
    assert "equity" in s["ledger"] and "started_at" in s["ledger"]
    e = s["events"][-1]
    for k in ["action", "fills", "liquidation", "position", "room_events", "trade_pnl", "equity"]:
        assert k in e, k
    assert isinstance(s["veto_ticks"], int) and isinstance(s["orders_today"], int)
    assert "unlocked" in s["room"] and "events" in s["room"]
    assert any("페이퍼 트레이딩" in line for line in s["disclosure"]) and len(s["disclosure"]) == 5
    # The client must not hard-code 20x, and the benchmark must be anchored season-wide.
    assert s["settings"]["leverage"] == 20 and s["settings"]["fly_name"]
    assert s["season"]["seed_bid"] > 0 and len(s["season"]["points"]) >= 1
    p = s["season"]["points"][0]
    for k in ["tick", "time", "equity", "bid", "liq", "bankrupt"]:
        assert k in p, k


def test_milestones_and_font_routes(server):
    st, h, body = get(server + "/room/milestones.json")
    assert st == 200 and h["Content-Type"].startswith("application/json")
    assert h["Cache-Control"] == "max-age=3600"
    assert [m["equity"] for m in json.loads(body)][:2] == [1200, 1500]
    font = Path("dashboard/assets/fonts/PretendardVariable.woff2")
    assert font.is_file(), "the self-hosted Pretendard subset ships with the dashboard"
    st, h, body = get(server + "/assets/fonts/PretendardVariable.woff2")
    assert st == 200 and h["Content-Type"] == "font/woff2" and h["Cache-Control"] == "max-age=3600"
    assert len(body) == font.stat().st_size


def test_path_traversal_is_refused(server):
    # Plain and percent-encoded: the route regex never sees an unquoted separator.
    for route in ["/assets/fonts/../server.py", "/assets/fonts/%2e%2e%2fserver.py",
                  "/assets/fonts/..%2F..%2Fserver.py", "/assets/fonts/%2e%2e%2f%2e%2e%2fserver.py"]:
        with pytest.raises(urllib.error.HTTPError) as e:
            get(server + route)
        assert e.value.code in (400, 404), route


def test_write_methods_refused(server):
    req = urllib.request.Request(server + "/state.json", method="POST", data=b"{}")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=10)
    assert e.value.code == 405
