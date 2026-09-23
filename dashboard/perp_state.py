"""Read-only helpers for perpetual runs: tail reads, ledger meta, event mapping."""

import json
import os
import sqlite3
import threading
from pathlib import Path

LEDGER_KEYS = ["mode", "venue", "tick", "cash", "equity", "position", "initial_cash", "halted", "fees_paid",
               "funding_paid", "realized_pnl", "liquidations", "next_funding", "started_at", "room_unlocked"]
KST_OFFSET = 32400  # seconds; the season is run and watched in Korea
MAX_SEASON_POINTS = 2000


def _ro(run):
    """Open the run ledger read-only. as_uri() percent-escapes the path, so a run
    directory containing '?' or '#' cannot corrupt the sqlite URI query string."""
    return sqlite3.connect((Path(run) / "ledger.sqlite").resolve().as_uri() + "?mode=ro", uri=True)


def venue_of(run):
    """Which venue produced this run. provenance.json is written before the first
    tick and survives an unreadable ledger; the ledger meta is the second source."""
    try:
        p = json.loads((Path(run) / "provenance.json").read_text(encoding="utf-8"))
        if isinstance(p, dict):
            v = p.get("venue")
            if isinstance(v, str) and v:
                return v
            s = p.get("perp_settings")
            if isinstance(s, dict):
                v = s.get("venue")
                return v if isinstance(v, str) and v else "orangex-perp"
    except (OSError, ValueError):
        pass
    try:
        db = _ro(run)
        row = db.execute("SELECT value FROM meta WHERE key='venue'").fetchone()
        db.close()
        if row:
            v = json.loads(row[0])
            if isinstance(v, str) and v:
                return v
    except (sqlite3.Error, ValueError):
        pass
    return "coinbase-spot"


def perp_settings(run):
    """Display settings the client must not hard-code (spec §4: leverage is a setting)."""
    try:
        p = json.loads((Path(run) / "provenance.json").read_text(encoding="utf-8"))
        s = p["perp_settings"]
        if not isinstance(s, dict):
            raise TypeError
    except (OSError, KeyError, TypeError, ValueError):
        s = {}
    try:
        leverage = int(s["leverage"])
    except (KeyError, TypeError, ValueError):
        leverage = 20
    out = {"leverage": leverage, "fly_name": fly_name(run)}
    for key in ("capital", "margin_fraction"):  # shown in the studio's explainer; strings as frozen
        if isinstance(s.get(key), str):
            out[key] = s[key]
    return out


def perp_trade_pnl(run):
    """tick -> realized_net for every closing fill, read from the ledger itself (spec §7.1). FUNDING rows are excluded by the action filter."""
    try:
        db = _ro(run)
        rows = db.execute("SELECT tick, realized_net FROM fills"
                          " WHERE action IN ('FLIP_CLOSE','LIQUIDATION') ORDER BY id").fetchall()
        db.close()
    except sqlite3.Error:
        return {}
    return {t: float(rn) for t, rn in rows}


def fills_today(run, now, tz_offset=KST_OFFSET):
    """Entries (OPEN, FLIP_OPEN) since local midnight of `now`.

    "Today" is the viewer's day, not UTC: with the default KST offset a fill at
    23:30 UTC already belongs to the next Korean day (08:30 KST).
    """
    midnight = now - (now + tz_offset) % 86400
    try:
        db = _ro(run)
        n = db.execute("SELECT COUNT(*) FROM fills WHERE action IN ('OPEN','FLIP_OPEN') AND created>=?",
                       (midnight,)).fetchone()[0]
        db.close()
        return int(n)
    except sqlite3.Error:
        return 0


def tail_lines(path, n):
    path = Path(path)
    if not path.exists() or n <= 0:
        return []
    block = 65536
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = pos = f.tell()
        chunks = []
        newlines = 0
        while pos > 0 and newlines <= n:
            step = min(block, pos)
            pos -= step
            f.seek(pos)
            data = f.read(step)
            chunks.append(data)
            newlines += data.count(b"\n")
    text = b"".join(reversed(chunks)).decode("utf-8", "replace")
    lines = text.splitlines()
    return lines[-n:]


def perp_ledger(run):
    try:
        db = _ro(run)
        meta = {k: json.loads(v) for k, v in db.execute("SELECT key,value FROM meta")}
        db.close()
    except sqlite3.Error:
        return {}
    return {k: meta.get(k) for k in LEDGER_KEYS}


def fly_name(run):
    try:
        p = json.loads((Path(run) / "provenance.json").read_text(encoding="utf-8"))
        name = p["perp_settings"]["fly_name"]
    except (OSError, KeyError, TypeError, ValueError):
        return "초파리"
    return str(name) if name else "초파리"  # JSON null / "" must not become "None"


def _rows(lines):
    for line in lines:
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def veto_count(lines):
    return sum(1 for r in _rows(lines) if not r.get("neural"))


def _closing_pnl(r):
    liq = r.get("liquidation")
    if liq:
        return float(liq["realized_net"])
    for f in (r.get("execution") or {}).get("fills") or []:
        if f.get("action") == "FLIP_CLOSE":  # the engine closes only via FLIP or liquidation
            return float(f["realized_net"])
    return None


def perp_events(lines, pnl=None):
    """Map event rows for the client. One malformed row must never take the whole
    dashboard down for hours, so an unmappable row is skipped like a quote failure."""
    pnl = pnl or {}
    out = []
    for r in _rows(lines):
        nr = r.get("neural")
        if not nr or r.get("equity_usdt") is None:
            continue
        ex = r.get("execution") or {}
        try:
            mapped = _map_event(r, nr, ex, pnl)
        except (KeyError, TypeError, ValueError):
            continue
        out.append(mapped)
    return out


def _map_event(r, nr, ex, pnl):
    return {
        "tick": r["tick"],
        "time": r["wall_time"],
        "product": r["product"],
        "bid": (r.get("quote") or {}).get("bid"),
        "equity": float(r["equity_usdt"]),
        "pnl": float(r["pnl_delta_usdt"]),
        "side": nr["side"],
        "left_hz": nr["left_hz"],
        "right_hz": nr["right_hz"],
        "diff_hz": nr["difference_hz"],
        "gate": nr["gate_spikes"],
        "stimulus": nr["stimulus"],
        "reward_spikes": nr["reward_spikes"],
        "aversive_spikes": nr["aversive_spikes"],
        "kc_spikes": nr["KC_spikes"],
        "total_spikes": nr["total_spikes"],
        "compute": nr["compute_seconds"],
        "changed_edges": nr["memory"]["changed_edges"],
        "mean_efficacy": nr["memory"]["mean_efficacy"],
        "min_efficacy": nr["memory"]["minimum_efficacy"],
        "execution": ex.get("status"),
        "reason": ex.get("reason"),
        "action": ex.get("action"),
        "fills": ex.get("fills") or [],
        "liquidation": r.get("liquidation"),
        "funding": r.get("funding"),
        "position": r.get("position"),
        "room_events": r.get("room_events") or [],
        "fees_paid": r.get("fees_paid"),
        "funding_paid": r.get("funding_paid"),
        "realized_pnl": r.get("realized_pnl"),
        "liquidations": r.get("liquidations"),
        "trade_pnl": pnl.get(r["tick"], _closing_pnl(r)),
    }


def room_recent(lines, limit=20):
    if limit <= 0:
        return []  # out[-0:] would return every event, not none
    out = []
    for r in _rows(lines):
        for e in r.get("room_events") or []:
            out.append({"tick": r["tick"], "type": e["type"], "item": e["item"], "label": e["label"]})
    return out[-limit:]


# season_series keeps one entry per events.jsonl path: how far it has parsed and
# what it kept. A 7-day run is ~15 MB and the dashboard polls every 4 s, so the
# whole-season view must never re-read the file from the start.
_SEASON_CACHE = {}
# The server is a ThreadingHTTPServer: two concurrent /state.json polls can both
# see a cold or stale cache entry for the same path and race to read+update it
# (double-counted points, a drifted offset). One lock serializes the whole
# read-modify-write below, across every path.
_SEASON_LOCK = threading.Lock()


def _season_row(c, line):
    try:
        r = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(r, dict) or not r.get("neural") or r.get("equity_usdt") is None:
        return  # quote-failure ticks observed nothing and priced nothing
    try:
        tick = int(r["tick"])
        equity = float(r["equity_usdt"])
        bid = (r.get("quote") or {}).get("bid")
        bid = None if bid is None else float(bid)
        when = float(r.get("wall_time") or 0.0)
    except (KeyError, TypeError, ValueError):
        return
    if c["seed_bid"] is None and bid is not None:
        c["seed_bid"] = bid  # the season anchor for the buy-and-hold benchmark
    c["seen"] += 1
    liq = bool(r.get("liquidation"))
    bankrupt = (r.get("execution") or {}).get("status") == "BANKRUPT"
    if not (liq or bankrupt or c["seen"] % c["stride"] == 1 or c["stride"] <= 1):
        return
    c["points"].append({"tick": tick, "time": when, "equity": equity, "bid": bid,
                        "liq": liq, "bankrupt": bankrupt})
    if len(c["points"]) > MAX_SEASON_POINTS:
        _thin(c)


def _thin(c):
    """Halve the sampled points (events are always kept) and halve the sampling rate."""
    kept, i = [], 0
    for p in c["points"]:
        if p["liq"] or p["bankrupt"]:
            kept.append(p)
        else:
            if i % 2 == 0:
                kept.append(p)
            i += 1
    c["points"] = kept
    c["stride"] *= 2


def season_series(path, every=10):
    """Whole-season equity and price points for the season chart.

    Returns `{"seed_bid": <first observed bid or None>, "points": [...]}` where a
    point is `{tick, time, equity, bid, liq, bankrupt}`. Every `every`-th observed
    tick is kept plus every liquidation/bankruptcy tick, capped at MAX_SEASON_POINTS.
    Only bytes appended since the previous call are parsed; a shrunk or replaced
    file resets the cache.
    """
    path = Path(path)
    with _SEASON_LOCK:
        try:
            st = path.stat()
        except OSError:
            return {"seed_bid": None, "points": []}
        key = str(path)
        c = _SEASON_CACHE.get(key)
        if (c is None or c["every"] != every or c["id"] != (st.st_ino, st.st_dev)
                or st.st_size < c["offset"]):
            c = {"offset": 0, "id": (st.st_ino, st.st_dev), "every": every, "stride": every,
                 "seen": 0, "seed_bid": None, "points": []}
            _SEASON_CACHE[key] = c
        if st.st_size > c["offset"]:
            with path.open("rb") as f:
                f.seek(c["offset"])
                data = f.read(st.st_size - c["offset"])
            end = data.rfind(b"\n")
            if end >= 0:  # a half-written last line stays unparsed until it is complete
                c["offset"] += end + 1
                for raw in data[:end].split(b"\n"):
                    _season_row(c, raw.decode("utf-8", "replace"))
        return {"seed_bid": c["seed_bid"], "points": list(c["points"])}
