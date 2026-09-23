import dataclasses
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from stonkfly.perp import runner
from stonkfly.perp.config import PerpSettings
from stonkfly.perp.fixture import FixturePerpMarket
from stonkfly.perp.ledger import PerpLedger
from stonkfly.venues.orangex import MarketUnavailable, SeedUnavailable

DATA = Path("data/graph.npz")
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="prepared MaleCNS data required")

INSTRUMENT = "BTC-USDT-PERPETUAL"
# Every events row carries exactly these keys, on a filled tick and on a skipped one alike.
ROW_KEYS = {
    "tick", "wall_time", "product", "mode", "venue", "quote", "equity_usdt", "equity_usdc",
    "pnl_delta_usdt", "pnl_delta_usdc", "neural", "execution", "veto", "position", "fees_paid",
    "funding_paid", "realized_pnl", "liquidations", "funding", "funding_source", "liquidation",
    "room_events", "outage_ticks",
}


def run_cli(*args, cwd=None):
    return subprocess.run([sys.executable, "-m", "stonkfly", *args], capture_output=True, text=True, cwd=cwd)


def ns(out, steps=1, **kw):
    """The argparse namespace `stonkfly run --venue orangex-perp --fixture --fast` produces."""
    return SimpleNamespace(**{
        "venue": "orangex-perp", "live": False, "preflight_only": False, "resume_reviewed": False,
        "fixture": True, "fast": True, "frozen": False, "steps": steps, "out": Path(out),
        "products": ["BTC-USDC"], "neural_ms": 500.0, **kw,
    })


class ScriptedMarket(FixturePerpMarket):
    """Fixture market that fails or staled on chosen loop iterations.

    The iteration number is the events.jsonl row count + 1. That number is the same for a tick's
    loop snapshot and for its re-quote snapshot (the row is written after both), so a scripted
    failure always lands on the skip path and never disguises itself as an execution veto."""

    def __init__(self, settings, out, fail_on=(), stale_on=()):
        super().__init__(settings)
        self.out, self.fail_on, self.stale_on = Path(out), set(fail_on), set(stale_on)

    def iteration(self):
        f = self.out / "events.jsonl"
        return (len(f.read_text().splitlines()) if f.exists() else 0) + 1

    def snapshot(self):
        i = self.iteration()
        if i in self.fail_on:
            raise MarketUnavailable("request failed: OSError")
        quotes = super().snapshot()
        if i in self.stale_on:  # a wrong local clock, not a stale feed
            return {p: dataclasses.replace(q, timestamp=time.time() - 3600) for p, q in quotes.items()}
        return quotes


def scripted(monkeypatch, out, **kw):
    monkeypatch.setattr(runner, "make_market", lambda settings, fixture: ScriptedMarket(settings, out, **kw))


def one_tick(out, *extra):
    return run_cli("run", "--venue", "orangex-perp", "--fixture", "--fast", "--steps", "1", "--out", str(out), *extra)


def meta(out):
    db = sqlite3.connect(out / "ledger.sqlite")
    try:
        return {k: json.loads(v) for k, v in db.execute("SELECT key,value FROM meta")}
    finally:
        db.close()


def set_halted(out, reason):
    db = sqlite3.connect(out / "ledger.sqlite")
    try:
        db.execute("INSERT OR REPLACE INTO meta VALUES ('halted',?)", (json.dumps(reason),))
        db.commit()
    finally:
        db.close()


def rows_of(out):
    return [json.loads(l) for l in (out / "events.jsonl").read_text().splitlines()]


def test_live_with_perp_is_rejected(tmp_path):
    r = run_cli("run", "--venue", "orangex-perp", "--live", "--out", str(tmp_path / "x"))
    assert r.returncode == 2 and "Live" in r.stderr


def test_fixture_run_writes_perp_schema(tmp_path):
    out = tmp_path / "fx"
    r = run_cli("run", "--venue", "orangex-perp", "--fixture", "--fast", "--steps", "3", "--out", str(out))
    assert r.returncode == 0, r.stderr
    rows = [json.loads(l) for l in (out / "events.jsonl").read_text().splitlines()]
    assert len(rows) == 3
    e = rows[-1]
    for k in ["venue", "equity_usdt", "pnl_delta_usdt", "position", "fees_paid", "funding_paid",
              "realized_pnl", "liquidations", "funding", "funding_source", "liquidation", "room_events", "neural", "execution"]:
        assert k in e, k
    assert [r["tick"] for r in rows] == [1, 2, 3]
    # Tick 1 only advances the funding schedule (no position, nothing settled), so it must not
    # claim a funding source: the dashboard pairs `funding_source` with a `funding` amount.
    assert all(r["funding"] is None and r["funding_source"] is None for r in rows)
    assert e["venue"] == "orangex-perp" and e["product"] == "BTC-USDT-PERPETUAL"
    assert e["equity_usdc"] == e["equity_usdt"]
    assert e["neural"]["side"] in ("BUY", "SELL", "HOLD")
    assert (out / "frames" / "tick-000003.png").exists()
    with np.load(out / "spikes" / "tick-000003.npz") as z:
        assert z["counts"].dtype == np.uint16 and z["counts"].shape[0] == 166700
    prov = json.loads((out / "provenance.json").read_text())
    assert prov["venue"] == "orangex-perp" and prov["perp_settings"]["leverage"] == 20
    assert prov["history_seed"] == "fixture" and prov["instrument_constants"]["price_increment"] == "0.1"
    assert prov["feed"] == "fixture"


def test_resume_keeps_ledger_and_history(tmp_path):
    out = tmp_path / "fx"
    assert run_cli("run", "--venue", "orangex-perp", "--fixture", "--fast", "--steps", "2", "--out", str(out)).returncode == 0
    assert run_cli("run", "--venue", "orangex-perp", "--fixture", "--fast", "--steps", "2", "--out", str(out)).returncode == 0
    rows = [json.loads(l) for l in (out / "events.jsonl").read_text().splitlines()]
    assert [r["tick"] for r in rows] == [1, 2, 3, 4]
    assert len(rows[-1]["quote"]) and rows[-1]["neural"] is not None


def test_resume_reviewed_clears_a_non_terminal_halt(tmp_path):
    out = tmp_path / "fx"
    assert one_tick(out).returncode == 0
    set_halted(out, "RuntimeError")  # e.g. an operator mistake recorded by the outer handler
    r = one_tick(out, "--resume-reviewed")
    assert r.returncode == 0, r.stderr
    assert [x["tick"] for x in rows_of(out)] == [1, 2]
    assert not meta(out)["halted"]


def test_resume_reviewed_refuses_a_terminal_halt(tmp_path):
    out = tmp_path / "fx"
    assert one_tick(out).returncode == 0
    set_halted(out, "bankrupt")
    r = one_tick(out, "--resume-reviewed")
    assert r.returncode != 0
    assert "bankrupt" in r.stderr.lower() and "terminal" in r.stderr.lower()
    assert meta(out)["halted"] == "bankrupt"  # refusing must not clear it
    assert not (out / "error.json").exists()  # an operator error is not a run failure
    assert len(rows_of(out)) == 1


def test_resume_reviewed_with_stop_present_exits_without_halting(tmp_path):
    out = tmp_path / "fx"
    assert one_tick(out).returncode == 0
    (out / "STOP").touch()
    r = one_tick(out, "--resume-reviewed")
    assert r.returncode != 0 and "Remove STOP" in r.stderr
    assert not meta(out)["halted"]  # the refusal itself must not brick the next start
    assert not (out / "error.json").exists()
    assert len(rows_of(out)) == 1
    (out / "STOP").unlink()
    assert one_tick(out).returncode == 0 and len(rows_of(out)) == 2


def test_corrupt_checkpoint_halts_durably(tmp_path):
    out = tmp_path / "fx"
    assert one_tick(out).returncode == 0
    brain = out / meta(out)["checkpoint"]["file"]
    brain.write_bytes(b"not a brain")
    r = one_tick(out)
    assert r.returncode != 0
    assert brain.name in r.stderr and "Checkpoint integrity" in r.stderr
    assert meta(out)["halted"] == "Checkpoint integrity"  # flyguard has to see this
    assert not (out / "error.json").exists()
    assert len(rows_of(out)) == 1
    brain.unlink()  # a missing file is damage too, not a crash
    r = one_tick(out, "--resume-reviewed")
    assert r.returncode != 0
    assert meta(out)["halted"] == "Checkpoint integrity"  # cleared by the flag, re-halted by the gate
    assert len(rows_of(out)) == 1


def test_status_reports_perp_fields(tmp_path):
    out = tmp_path / "fx"
    run_cli("run", "--venue", "orangex-perp", "--fixture", "--fast", "--steps", "1", "--out", str(out))
    r = run_cli("status", "--out", str(out))
    s = json.loads(r.stdout)
    assert s["mode"] == "paper" and s["tick"] == 1 and "position" in s and "liquidations" in s
    import sqlite3
    db = sqlite3.connect(f"file:{out / 'ledger.sqlite'}?mode=ro", uri=True)
    meta = {k: json.loads(v) for k, v in db.execute("SELECT key,value FROM meta")}
    assert meta["started_at"] > 0 and 900 < float(meta["equity"]) <= 1000  # a first-tick fill costs fee + spread


# ---- loop paths that only a live season would otherwise exercise --------------------------


def test_market_outage_halts_after_ten_skips(tmp_path, monkeypatch):
    out = tmp_path / "fx"
    scripted(monkeypatch, out, fail_on=range(1, 30))
    runner.run(ns(out, steps=12))  # more steps than the outage budget: the halt has to stop it
    rows = rows_of(out)
    assert [r["tick"] for r in rows] == list(range(1, 11))  # skipped ticks still advance the counter
    assert [r["outage_ticks"] for r in rows] == list(range(1, 11))
    assert all(set(r) == ROW_KEYS for r in rows)
    assert all(r["quote"] is None and r["neural"] is None for r in rows)
    assert all(r["execution"] == {"status": "VETO", "reason": r["veto"]} for r in rows)
    assert meta(out)["halted"] == "market-outage" and meta(out)["tick"] == 10
    assert not (out / "error.json").exists()  # an outage is not a crash


def test_clock_skew_halts_separately_from_an_outage(tmp_path, monkeypatch):
    """A wrong clock vetoes every quote as stale. Halting it as "market-outage" would have flyguard
    auto-resume into the same wall forever, recording nothing for the rest of the season."""
    out = tmp_path / "fx"
    scripted(monkeypatch, out, stale_on=range(1, 30))
    runner.run(ns(out, steps=12))
    rows = rows_of(out)
    assert [r["tick"] for r in rows] == list(range(1, 11))
    assert all(r["veto"] == "Stale or future quote" for r in rows)
    assert meta(out)["halted"] == "clock-skew"
    assert not (out / "error.json").exists()


def test_skip_row_and_normal_row_share_keys(tmp_path, monkeypatch):
    out = tmp_path / "fx"
    scripted(monkeypatch, out, fail_on=[2])
    runner.run(ns(out, steps=2))
    normal, skipped = rows_of(out)
    assert normal["quote"] is not None and skipped["quote"] is None
    assert set(normal) == set(skipped) == ROW_KEYS
    assert meta(out)["halted"] is None


def test_row_position_has_one_shape(tmp_path):
    s = runner.build_settings(ns(tmp_path))
    led = PerpLedger(tmp_path / "l.sqlite", s)
    q = FixturePerpMarket(s).snapshot()[INSTRUMENT]
    assert runner.row_position(led, s, q) is None and runner.row_position(led, s) is None
    led.open_position("LONG", q, 1, 1.0)
    marked, skipped = runner.row_position(led, s, q), runner.row_position(led, s)
    assert set(marked) == set(skipped)  # the dashboard reads one key; it must not meet two shapes
    assert skipped["mark"] is skipped["unrealized"] is skipped["liquidation_price"] is None
    assert skipped["leverage"] == 20 and skipped["side"] == "LONG"
    led.close()


def test_checkpoint_slot_survives_skipped_ticks(tmp_path, monkeypatch):
    """tick % 2 collapses after an even number of skips: the next good tick overwrites the slot the
    committed checkpoint points at, and a crash mid-write leaves nothing matching its hash."""
    out = tmp_path / "fx"
    scripted(monkeypatch, out, fail_on=[2, 3])
    runner.run(ns(out, steps=4))
    rows = rows_of(out)
    assert [r["tick"] for r in rows] == [1, 2, 3, 4]
    assert [r["quote"] is None for r in rows] == [False, True, True, False]
    committed = meta(out)["checkpoint"]
    assert committed["file"] == "brain-0.npz"  # tick 1 wrote brain-1; tick 4 must not reuse it
    import hashlib
    assert hashlib.sha256((out / committed["file"]).read_bytes()).hexdigest() == committed["sha256"]
    assert (out / "brain-1.npz").exists()


def test_bankrupt_row_and_halt(tmp_path):
    out = tmp_path / "fx"
    a = ns(out, steps=1)
    led = PerpLedger(out / "ledger.sqlite", runner.build_settings(a))
    led.put("cash", "2")  # no position and too little cash for a minimum order on either side
    led.close()
    runner.run(a)
    row = rows_of(out)[-1]
    assert row["execution"]["status"] == "BANKRUPT"
    assert [f["action"] for f in row["execution"]["fills"]] == ["BANKRUPT"]
    assert meta(out)["halted"] == "bankrupt"
    assert not (out / "error.json").exists()  # terminal, but not a crash


def test_seed_failure_exits_without_halting(tmp_path, monkeypatch):
    """Spec §10: a failed startup seed exits and systemd restarts. A halt would strand the season,
    because flyguard releases "market-outage" and nothing else on this venue."""
    out = tmp_path / "fx"

    class NoSeed(FixturePerpMarket):
        def snapshot(self):
            raise SeedUnavailable("seed failed: request failed: URLError")

    monkeypatch.setattr(runner, "make_market", lambda settings, fixture: NoSeed(settings))
    with pytest.raises(SystemExit) as e:
        runner.run(ns(out, steps=1))
    assert e.value.code == 1
    assert meta(out)["halted"] is None
    assert not (out / "error.json").exists() and not (out / "events.jsonl").exists()


def test_settings_mismatch_exits_without_halting(tmp_path):
    """A settings/mode mismatch used to raise before the run's own error handling: a raw traceback,
    no halt, and systemd restarting it every 30-300 s with nobody told."""
    out = tmp_path / "fx"
    other = PerpLedger(out / "ledger.sqlite", PerpSettings(leverage=10, neural_ms=500.0, pulse_ms=200))
    other.close()
    with pytest.raises(SystemExit) as e:
        runner.run(ns(out, steps=1))
    assert "mismatch" in str(e.value)
    assert meta(out)["halted"] is None and not (out / "error.json").exists()


def test_neural_ms_flag_and_default_agree(tmp_path):
    """--neural-ms 500 parses to a float, the omitted default was an int, and the two settings
    signatures differ -> the ledger refuses to resume the run it just wrote."""
    assert runner.build_settings(ns(tmp_path, neural_ms=500)).signature() == \
        runner.build_settings(ns(tmp_path, neural_ms=500.0)).signature()
    assert runner.build_settings(ns(tmp_path, neural_ms=500)).neural_ms == 500.0


def test_fast_without_fixture_is_rejected(tmp_path):
    r = run_cli("run", "--venue", "orangex-perp", "--fast", "--out", str(tmp_path / "x"))
    assert r.returncode == 2 and "fixture" in r.stderr


class FakeClock:
    """A clock _sleep can be driven against in process: `time.time` reads it, `time.sleep` advances
    it, and `on_sleep` lets a test step the clock mid-wait. `monotonic` deliberately runs 8% fast,
    the way this WSL2 host's does -- any test that still passes is not reading it."""

    def __init__(self, start=1_000_000.0):
        self.now = self.start = start
        self.slept = []
        self.on_sleep = None

    def time(self):
        return self.now

    def monotonic(self):
        return (self.now - self.start) * 1.08

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds
        if self.on_sleep:
            self.on_sleep(self)

    @property
    def total(self):
        return sum(self.slept)


def fake_clock(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(runner.time, "time", clock.time)
    monkeypatch.setattr(runner.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(runner.time, "sleep", clock.sleep)
    return clock


def test_sleep_targets_the_wall_clock_not_monotonic(tmp_path, monkeypatch):
    """The monotonic clock on this host runs ~8% fast, which made live ticks arrive every ~55 s and
    the 60 s (wall-clock) order cooldown veto the tick after every fill."""
    clock = fake_clock(monkeypatch)
    runner._sleep(ns(tmp_path, steps=0, fast=False), 1, clock.start, 60, tmp_path)
    assert clock.now == pytest.approx(clock.start + 60)  # a monotonic deadline would stop at ~55.5
    assert clock.total == pytest.approx(60) and max(clock.slept) <= 1  # <=1 s slices for STOP


def test_sleep_is_not_extended_by_a_backwards_wall_step(tmp_path, monkeypatch):
    """timesync can step the wall clock backwards mid-wait. The tick may then be late, but it must
    never wait more than one interval for it."""
    clock = fake_clock(monkeypatch)
    stepped = []

    def step_back(c):
        if not stepped and c.now - c.start >= 30:
            stepped.append(c.now)
            c.now -= 30
    clock.on_sleep = step_back
    runner._sleep(ns(tmp_path, steps=0, fast=False), 1, clock.start, 60, tmp_path)
    assert stepped, "the step never happened; the test is not exercising what it claims"
    assert clock.total == pytest.approx(60)  # 30 s slept, clock rewound, 30 s of budget left


def test_sleep_ends_immediately_on_a_forward_wall_jump(tmp_path, monkeypatch):
    clock = fake_clock(monkeypatch)

    def jump(c):
        if c.total >= 5:
            c.now += 300
            c.on_sleep = None
    clock.on_sleep = jump
    runner._sleep(ns(tmp_path, steps=0, fast=False), 1, clock.start, 60, tmp_path)
    assert clock.total == pytest.approx(5)


def test_sleep_ends_when_the_stop_file_appears(tmp_path, monkeypatch):
    clock = fake_clock(monkeypatch)
    clock.on_sleep = lambda c: c.total >= 3 and (tmp_path / "STOP").write_text("")
    runner._sleep(ns(tmp_path, steps=0, fast=False), 1, clock.start, 60, tmp_path)
    assert clock.total == pytest.approx(3)


def test_sleep_returns_immediately_when_fast_or_on_the_last_step(tmp_path, monkeypatch):
    clock = fake_clock(monkeypatch)
    runner._sleep(ns(tmp_path, steps=1, fast=True), 1, clock.start, 60, tmp_path)
    runner._sleep(ns(tmp_path, steps=2, fast=False), 2, clock.start, 60, tmp_path)
    assert clock.slept == [] and clock.now == clock.start
