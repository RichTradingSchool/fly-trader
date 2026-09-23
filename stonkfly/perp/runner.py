"""Perpetual paper run loop: OrangeX observations, 20x isolated long/short, fly decides."""

import dataclasses
import fcntl
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

import numpy as np

from ..config import D
from ..venues.orangex import SeedUnavailable
from .config import PerpSettings

PACKAGE = Path(__file__).resolve().parent.parent  # stonkfly/
SLIPPAGE = D("0.005")  # observation-vs-execution tolerance, same value as the spot Settings.slippage
TERMINAL_HALTS = ("bankrupt", "accounting-error")  # spec §4/§8: the season is over, never auto-cleared
SKEW_VETO = "Stale or future quote"  # PerpGuard's freshness message; a clock problem, not an outage


def source_hashes():
    return {
        str(path.relative_to(PACKAGE)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in PACKAGE.rglob("*")
        if path.suffix in (".py", ".cpp", ".json")
    }


def build_settings(a):
    """One settings signature per run directory. `--neural-ms 500` parses to a float while the
    omitted default is an int, and the two hash differently, so a run started with the flag could
    never resume without it. The cast happens here and nowhere else."""
    ms = float(a.neural_ms)
    return PerpSettings(learning=not a.frozen, neural_ms=ms, pulse_ms=min(200, ms))


def make_market(settings, fixture):
    """Market factory, kept separate so tests can drive the loop's failure paths in process."""
    from ..venues.orangex import OrangeXMarket
    from .fixture import FixturePerpMarket

    return FixturePerpMarket(settings) if fixture else OrangeXMarket(settings)


def row_position(ledger, settings, quote=None):
    """One position shape for every events row. A skipped tick has no usable quote, so the marked
    fields are null — but the key set stays identical to `position_view`, because the dashboard
    reads one key and must not meet two shapes under it."""
    if quote is not None:
        return ledger.position_view(quote)
    p = ledger.position
    if p is None:
        return None
    return {**p, "mark": None, "unrealized": None, "liquidation_price": None,
            "leverage": settings.leverage}


def operator_gates(a, ledger, out):
    """Start-up preconditions, checked before the run's own error handling. An operator mistake
    exits with a message and writes no `halted`: a halt written by a mistake would have to be
    cleared by the very flag the mistake just refused. Checkpoint damage is the exception — it is
    data loss, not a slip, so it halts durably and only a restored file lets the season continue."""
    if a.resume_reviewed:
        if (out / "STOP").exists():
            raise SystemExit("Remove STOP only after review")
        reason = ledger.get("halted") or None
        if reason in TERMINAL_HALTS:
            raise SystemExit(
                f"Terminal halt {reason!r}: this season is over and is never cleared."
                " Start a new season in a fresh run directory."
            )
        ledger.put("halted", None)
        print(json.dumps({"resume_reviewed": {"cleared": reason}}), flush=True)
    cp = ledger.get("checkpoint")
    if cp:
        path = out / cp["file"]
        try:
            intact = hashlib.sha256(path.read_bytes()).hexdigest() == cp["sha256"]
        except OSError:
            intact = False  # missing or unreadable is damage too, not a different kind of problem
        if not intact:
            if not ledger.get("halted"):
                # Durable, so flyguard holds the season instead of watching systemd restart forever.
                ledger.halt("Checkpoint integrity")
            raise SystemExit(
                f"Checkpoint integrity: {path} is missing or does not match the committed brain"
                f" state. Restore {cp['file']} itself from a backup — the other brain-N.npz slot"
                " holds a different tick's brain and fails the same hash — or start a new season"
                " in a fresh run directory."
            )


def run(a):
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    settings = build_settings(a)
    out = a.out or Path("runs/perp")
    out.mkdir(parents=True, exist_ok=True)
    (out / "frames").mkdir(exist_ok=True)
    (out / "spikes").mkdir(exist_ok=True)
    lock = (out / "worker.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("A worker already owns this run directory")
    from .broker import PerpPaperBroker
    from .ledger import PerpLedger

    try:
        ledger = PerpLedger(out / "ledger.sqlite", settings, "paper")
    except RuntimeError as e:
        # Operator error like the gates below: this run directory belongs to different settings.
        # No halt and no error.json — there is nothing to review and nothing a flag could clear,
        # and a silent non-zero exit would leave systemd restarting forever (spec §10).
        raise SystemExit(str(e)) from None
    operator_gates(a, ledger, out)
    try:
        broker = PerpPaperBroker(settings, ledger)
        print(json.dumps(broker.preflight()), flush=True)
        import subprocess

        clock = subprocess.run(
            ["timedatectl", "show", "--property=NTPSynchronized", "--property=TimeUSec", "--value"],
            capture_output=True, text=True,
        )
        print(json.dumps({"clock": clock.stdout.split()}), flush=True)
        if a.preflight_only:
            return
        from ..data import verify

        verified = verify()
        from PIL import Image

        from ..display import market_frame
        from ..neural.controller import FlyController
        from ..reinforcement import reinforcement
        from ..risk import Veto
        from ..venues.orangex import MarketUnavailable
        from .actions import PerpActions
        from .risk import PerpGuard
        from .room import load_milestones, room_update

        instrument = settings.instrument
        market = make_market(settings, a.fixture)
        previous = ledger.get("observation")
        if previous:
            market.history = previous["market_history"]
            if a.fixture:
                market.tick = previous["fixture_tick"]
        controller = FlyController(settings)
        cp = ledger.get("checkpoint")
        if cp:
            controller.restore(out / cp["file"])  # integrity already verified by operator_gates
        provenance = {
            "venue": settings.venue,
            "perp_settings": dataclasses.asdict(settings),
            "instrument_constants": {
                "price_increment": settings.price_increment,
                "base_increment": settings.base_increment,
                "minimum_base": settings.minimum_base,
                "minimum_quote": settings.minimum_quote,
            },
            "history_seed": "fixture" if a.fixture else "bybit-linear-1m",
            "funding": "orangex public/get_funding_rate at expire_time; fallback constant on failure",
            "dataset": verified,
            "circuit": controller.brain.circuit["report"],
            "vision": controller.brain.visual_report,
            "mode": broker.mode,
            "feed": "fixture" if a.fixture else "orangex-public",
            "decoder": "DNp20 mean R-L: BUY->LONG / SELL->SHORT; DNpe017 spike gate; otherwise hold. Engineered fixed mapping.",
            "position_rules": "one position; same-side signal ignored; opposite signal closes then opens; isolated liquidation at mmr; funding at expire_time",
            "learning_validated": False,
            "pain_receptors_modeled": False,
            "timing": "Each observation advances configured neural_ms regardless of wall-market time; no claim of real-time fly physiology.",
            "milestones": load_milestones(),
            "source_sha256": source_hashes(),
        }
        signature = hashlib.sha256(json.dumps(provenance, sort_keys=True).encode()).hexdigest()
        if ledger.get("provenance_sha256") not in (None, signature):
            # The last operator gate; it can only run here, because the signature needs the
            # provenance built from the loaded brain. SystemExit is not an Exception, so it
            # passes the handler below untouched: no halt, no error.json, just a message.
            raise SystemExit("Run source/protocol changed; use a separate paper run or explicitly review migration")
        ledger.put("provenance_sha256", signature)
        (out / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
        guard = PerpGuard(settings, ledger, out / "STOP")
        actions = PerpActions(guard, broker)
        if not ledger.get("started_at"):
            with ledger.transaction():
                ledger.put("started_at", time.time())  # season start, read by the dashboard's D+n
        count = 0
        outage = 0
        skew = 0  # consecutive freshness vetoes: a wrong clock, which no auto-resume can fix

        def write_row(row):
            with (out / "events.jsonl").open("a") as f:
                f.write(json.dumps(row, allow_nan=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            (out / "latest.json").write_text(json.dumps(row, indent=2) + "\n")

        while not a.steps or count < a.steps:
            wall_started = time.time()  # tick cadence is wall clock, not monotonic; see _sleep
            if (out / "STOP").exists() or ledger.get("halted"):
                break
            now = time.time()
            tick = ledger.get("tick")
            row_tick = tick + 1  # one number per observation for every fill and every events row
            try:
                quotes = market.snapshot()
                now = time.time()  # freshness is judged after the round trip (original cli.py:204-205)
                guard.check(quotes, now)
            except (MarketUnavailable, Veto) as e:
                outage += 1
                reason = str(e)
                skew = skew + 1 if reason == SKEW_VETO else 0
                with ledger.transaction():
                    ledger.put("tick", row_tick)  # skipped observations still advance the tick counter
                write_row({
                    "tick": row_tick, "wall_time": now, "product": instrument, "mode": broker.mode,
                    "venue": settings.venue, "quote": None, "neural": None, "veto": reason,
                    "execution": {"status": "VETO", "reason": reason},
                    "equity_usdt": None, "equity_usdc": None, "pnl_delta_usdt": None, "pnl_delta_usdc": None,
                    "position": row_position(ledger, settings), "fees_paid": ledger.get("fees_paid"),
                    "funding_paid": ledger.get("funding_paid"), "realized_pnl": ledger.get("realized_pnl"),
                    "liquidations": ledger.get("liquidations"), "funding": None, "liquidation": None,
                    "funding_source": None, "room_events": [], "outage_ticks": outage,
                })
                print(json.dumps({"tick": row_tick, "skipped": reason, "outage_ticks": outage}), flush=True)
                if skew >= settings.outage_ticks:
                    # Every quote looked stale for outage_ticks in a row: the feed is fine and this
                    # clock is not. Halting as "market-outage" would have flyguard auto-resume into
                    # the same wall, forever, recording nothing (spec §8 holds every other perp halt).
                    ledger.halt("clock-skew")
                    break
                if outage >= settings.outage_ticks:
                    ledger.halt("market-outage")
                    break
                count += 1
                _sleep(a, count, wall_started, settings.interval_seconds, out)
                continue
            outage = skew = 0
            market.record(quotes)
            q = quotes[instrument]
            funding_fill, funding_source = None, None
            if ledger.funding_due(int(now * 1000)):
                rate, expire, source = market.funding()
                funding_fill = ledger.apply_funding(rate, expire, source, q, row_tick, now)
                # Only a settlement has a source. A bare schedule advance (no position) settles
                # nothing, so claiming one would label a "funding": null row with provenance.
                funding_source = source if funding_fill else None
            liq_fill = ledger.liquidate_if_needed(q, row_tick, now)
            equity = ledger.equity(q)
            if equity < 0:
                raise ValueError(f"Negative equity {equity}")  # -> halted="accounting-error", error.json (spec §10)
            kind, delta = reinforcement(equity, ledger.get("anchor"), settings.reward_deadband)
            frame = market_frame(settings.label, market.history[instrument], q.bid, q.ask)
            neural = controller.observe(frame, kind)
            # Always write the slot the committed checkpoint does NOT point at. Deriving it from
            # the tick counter breaks after an even number of skipped ticks (a market outage
            # advances the tick without writing a checkpoint), and overwriting the committed slot
            # leaves a crash between replace() and COMMIT with no file matching the stored hash.
            slot = 0 if (ledger.get("checkpoint") or {}).get("file") == "brain-1.npz" else 1
            checkpoint = out / f"brain-{slot}.npz"
            controller.save(checkpoint)
            checkpoint_info = {"file": checkpoint.name, "sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest()}
            observation = {
                "neural": neural, "product": instrument, "quote": q.json(), "pnl_delta_usdt": str(delta),
                "market_history": market.history, "fixture_tick": getattr(market, "tick", None),
            }
            ledger.commit_tick(equity, checkpoint_info, observation)
            unlocked, room_events = room_update(equity, ledger.get("room_unlocked") or [])
            if room_events:
                with ledger.transaction():
                    ledger.put("room_unlocked", unlocked)
            order = {"status": "HOLD"}
            if ledger.is_bankrupt(q):
                # Terminal: no position and cash below one minimum order. Checked once here — a fill
                # cannot make the account bankrupt (it creates a position), and a veto leaves it unchanged.
                order = {"status": "BANKRUPT", "fills": [ledger.bankrupt(q, row_tick, now)]}
            elif neural["side"] != "HOLD":
                try:
                    fresh = market.snapshot()
                    latest = fresh[instrument]
                    if abs(latest.bid - q.bid) / q.bid > SLIPPAGE:
                        raise Veto("Price moved beyond neural observation tolerance")
                    actions.quotes = fresh
                    order = actions.invoke({"product": instrument, "side": neural["side"]})
                except (Veto, MarketUnavailable) as e:
                    order = {"status": "VETO", "reason": str(e)}
            new_tick = ledger.get("tick")
            assert new_tick == row_tick, "tick bookkeeping drifted"
            row = {
                "tick": new_tick, "wall_time": now, "product": instrument, "mode": broker.mode,
                "venue": settings.venue, "quote": q.json(),
                "equity_usdt": str(equity), "equity_usdc": str(equity),
                "pnl_delta_usdt": str(delta), "pnl_delta_usdc": str(delta),
                "neural": neural, "execution": order, "veto": None,
                "position": row_position(ledger, settings, q), "fees_paid": ledger.get("fees_paid"),
                "funding_paid": ledger.get("funding_paid"), "realized_pnl": ledger.get("realized_pnl"),
                "liquidations": ledger.get("liquidations"), "funding": funding_fill, "funding_source": funding_source,
                "liquidation": liq_fill, "room_events": room_events, "outage_ticks": 0,
            }
            write_row(row)
            Image.fromarray(frame).save(out / "latest-input.png")
            Image.fromarray(frame).save(out / "frames" / f"tick-{new_tick:06d}.png")
            np.savez_compressed(out / "spikes" / f"tick-{new_tick:06d}.npz",
                                counts=np.clip(controller.brain.counts, 0, 65535).astype(np.uint16))
            print(json.dumps({
                "tick": new_tick, "side": neural["side"], "execution": order["status"],
                "equity": str(equity), "position": (ledger.position or {}).get("side"),
                "stimulus": kind, "plastic_edges_changed": neural["memory"]["changed_edges"],
                "liquidation": bool(liq_fill), "room": [e["type"] + ":" + e["item"] for e in room_events],
            }), flush=True)
            count += 1
            _sleep(a, count, wall_started, settings.interval_seconds, out)
    except SeedUnavailable as e:
        # Spec §10: a failed startup seed is an exit, not a halt. Writing one would leave flyguard
        # holding the season (it releases only "market-outage") for what systemd's Restart=always
        # fixes by itself; if it never recovers, flyguard's stall counter holds instead.
        print(json.dumps({"seed_unavailable": str(e)}), file=sys.stderr, flush=True)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print("Stopped; run state preserved.", flush=True)
    except Exception as e:
        if not ledger.get("halted"):
            ledger.halt(
                "accounting-error" if isinstance(e, (ValueError, ArithmeticError))
                else type(e).__name__
            )
        frames = traceback.extract_tb(e.__traceback__)
        diagnostic = {
            "type": type(e).__name__,
            "reason": str(e),
            "locations": [f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in frames],
        }
        (out / "error.json").write_text(json.dumps(diagnostic, indent=2) + "\n")
        print(f"Stopped safely: {type(e).__name__}. Inspect local state and reconcile before restarting.", file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        ledger.close()
        lock.close()


def _sleep(a, count, wall_started, interval, out):
    """Wait out the rest of the tick interval on the wall clock, not monotonic: on this WSL2 host
    the monotonic clock runs fast (5-9%, and the rate wanders), so a monotonic deadline fires early
    and the wall-clock order cooldown then vetoes the tick after every fill; hyper-v timesync keeps
    wall time honest. Wall time can step, so the wait is bounded two ways: it ends at
    `wall_started + interval` (a forward jump is "tick now") and it never sleeps more than one
    interval in total (a backwards step must not stretch the tick). Slices stay at one second so a
    STOP file still stops the run promptly."""
    if a.fast or (a.steps and count >= a.steps):
        return
    until, slept = wall_started + interval, 0.0
    while not (out / "STOP").exists():
        remaining = min(until - time.time(), interval - slept)
        if remaining <= 0:
            break
        slice_ = min(1, remaining)
        time.sleep(slice_)
        slept += slice_
