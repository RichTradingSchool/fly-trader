"""Compact public feed for the 3D studio (/room) and the static web viewer.

The lab view reads the full /state.json (~400 KB). A viewer on a phone only needs the
last couple of hours of observations, the trades for the journal and a thinned season
chart, so /live.json carries exactly that. Everything here is a pure function of the
state dict the server already builds; nothing reads the run directory directly.
"""

EVENT_KEYS = ("tick", "time", "bid", "equity", "pnl", "side", "left_hz", "right_hz", "gate", "stimulus",
              "reward_spikes", "aversive_spikes", "execution", "reason")
LEDGER_KEYS = ("initial_cash", "equity", "realized_pnl", "fees_paid", "funding_paid", "liquidations",
               "next_funding", "started_at", "room_unlocked", "halted", "position", "tick")
MAX_EVENTS = 120      # two hours of one-minute observations: the price chart and fresh reactions
MAX_NOTABLE = 40      # trades, liquidations, funding and room events for the journal
MAX_POINTS = 400      # season chart resolution on a 1024 px monitor texture


def _num(v, nd):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return v


def _pick(d, keys):
    return {k: d.get(k) for k in keys if k in d} if isinstance(d, dict) else None


def slim_event(e):
    out = {k: e.get(k) for k in EVENT_KEYS}
    out["time"] = _num(out["time"], 1)
    out["equity"] = _num(out["equity"], 4)
    out["pnl"] = _num(out["pnl"], 4)
    out["left_hz"] = _num(out["left_hz"], 1)
    out["right_hz"] = _num(out["right_hz"], 1)
    out["fills"] = [_pick(f, ("action", "side", "price", "qty", "realized_net")) for f in e.get("fills") or []]
    out["liquidation"] = _pick(e.get("liquidation"), ("side", "price", "qty", "realized_net"))
    out["funding"] = _pick(e.get("funding"), ("side", "fee", "realized_net"))
    pos = _pick(e.get("position"), ("side", "qty", "entry", "margin", "unrealized", "liquidation_price", "leverage"))
    if pos and pos.get("liquidation_price") is not None:
        pos["liquidation_price"] = _num(pos["liquidation_price"], 1)
    out["position"] = pos
    out["room_events"] = [_pick(r, ("type", "item", "label", "equity_threshold")) for r in e.get("room_events") or []]
    return out


def notable(e):
    return bool(e.get("fills") or e.get("liquidation") or e.get("funding") or e.get("room_events")
                or e.get("execution") == "BANKRUPT")


def thin_points(points, limit=MAX_POINTS):
    """Evenly thin the season series to `limit` points, always keeping the first, the last,
    every liquidation and the bankruptcy so the chart still marks them."""
    if len(points) <= limit:
        keep = points
    else:
        step = len(points) / limit
        idx = {int(i * step) for i in range(limit)} | {0, len(points) - 1}
        idx |= {i for i, p in enumerate(points) if p.get("liq") or p.get("bankrupt")}
        keep = [points[i] for i in sorted(idx)]
    return [{"tick": p.get("tick"), "time": _num(p.get("time"), 0), "equity": _num(p.get("equity"), 2),
             "bid": _num(p.get("bid"), 1), "liq": bool(p.get("liq")), "bankrupt": bool(p.get("bankrupt"))}
            for p in keep]


def live_payload(state):
    """The /live.json body (without `now`: the viewer gets the clock from /tick.json)."""
    events = state.get("events") or []
    season = state.get("season") or {}
    return {
        "run": state.get("run"),
        "venue": state.get("venue"),
        "fly_name": state.get("fly_name"),
        "settings": state.get("settings") or {},
        "disclosure": state.get("disclosure") or [],
        "stopped": bool(state.get("stopped")),
        "orders_today": state.get("orders_today") or 0,
        "ledger": _pick(state.get("ledger") or {}, LEDGER_KEYS) or {},
        "season": {"seed_bid": season.get("seed_bid"), "points": thin_points(season.get("points") or [])},
        "events": [slim_event(e) for e in events[-MAX_EVENTS:]],
        "notable": [slim_event(e) for e in events if notable(e)][-MAX_NOTABLE:],
    }


def current_tick(state):
    events = state.get("events") or []
    if events:
        return events[-1].get("tick")
    return (state.get("ledger") or {}).get("tick")
