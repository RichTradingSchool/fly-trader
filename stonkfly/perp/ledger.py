"""Isolated-margin perpetual paper ledger. One position, Decimal strings, SQLite WAL."""

import contextlib
import json
import sqlite3
from pathlib import Path

from ..config import D, down

SIGN = {"LONG": D(1), "SHORT": D(-1)}


class PerpLedger:
    def __init__(self, path, settings, mode="paper"):
        self.s = settings
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS fills (id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " tick INTEGER NOT NULL, created REAL NOT NULL, side TEXT, action TEXT NOT NULL,"
            " qty TEXT NOT NULL, price TEXT NOT NULL, notional TEXT NOT NULL, fee TEXT NOT NULL,"
            " realized TEXT NOT NULL, realized_net TEXT NOT NULL, reason TEXT, quote TEXT NOT NULL)"
        )
        if self.get("settings") is None:
            with self.transaction():
                for k, v in {
                    "settings": settings.signature(),
                    "mode": mode,
                    "venue": settings.venue,
                    "cash": settings.capital,
                    "initial_cash": settings.capital,
                    "position": None,
                    "anchor": settings.capital,
                    "equity": settings.capital,  # the dashboard reads this before the first commit_tick

                    "tick": 0,
                    "checkpoint": None,
                    "halted": None,
                    "last_attempt": 0,
                    "fees_paid": "0",
                    "funding_paid": "0",
                    "realized_pnl": "0",
                    "liquidations": 0,
                    "next_funding": 0,
                    "room_unlocked": [],
                }.items():
                    self.put(k, v)
        elif self.get("settings") != settings.signature() or self.get("mode") != mode:
            raise RuntimeError("Run settings/mode mismatch; use a separate run directory")

    @contextlib.contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def get(self, key):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value, allow_nan=False)))

    # ---- state ---------------------------------------------------------
    @property
    def cash(self):
        return D(self.get("cash"))

    @property
    def position(self):
        return self.get("position")

    def mark_price(self, quote):
        p = self.position
        if p is None:
            return (quote.bid + quote.ask) / 2
        return quote.bid if p["side"] == "LONG" else quote.ask

    def unrealized(self, quote):
        p = self.position
        if p is None:
            return D(0)
        return D(p["qty"]) * (self.mark_price(quote) - D(p["entry"])) * SIGN[p["side"]]

    def equity(self, quote):
        p = self.position
        if p is None:
            return self.cash
        return self.cash + D(p["margin"]) + self.unrealized(quote)

    def liquidation_price(self):
        p = self.position
        if p is None:
            return None
        lev, mmr, entry = D(self.s.leverage), D(self.s.mmr), D(p["entry"])
        if p["side"] == "LONG":
            return entry * (1 - 1 / lev) / (1 - mmr)
        return entry * (1 + 1 / lev) / (1 + mmr)

    def target_notional(self, equity):
        """The notional an entry aims at, before the quantity is rounded to the instrument's lot.
        `entry_size` and the flip guard's re-entry fee forecast share it so they cannot drift."""
        return down(equity * D(self.s.margin_fraction), D("0.01")) * self.s.leverage  # spec §4: cent rounding

    def entry_size(self, quote, side):
        price = quote.ask if side == "LONG" else quote.bid
        target_notional = self.target_notional(self.equity(quote))
        qty = down(target_notional / price, quote.base_increment)
        notional = qty * price
        return {
            "qty": qty,
            "price": price,
            "notional": notional,
            "margin": notional / self.s.leverage,
            "fee": notional * D(self.s.taker_fee),
        }

    def position_view(self, quote):
        p = self.position
        if p is None:
            return None
        return {
            **p,
            "mark": str(self.mark_price(quote)),
            "unrealized": str(self.unrealized(quote)),
            "liquidation_price": str(self.liquidation_price()),
            "leverage": self.s.leverage,
        }

    def funding_due(self, now_ms):
        return now_ms >= int(self.get("next_funding") or 0)

    def halt(self, reason):
        self.put("halted", reason)

    def commit_tick(self, anchor, checkpoint, observation=None):
        with self.transaction():
            self.put("anchor", str(anchor))
            self.put("equity", str(anchor))  # marked equity of this tick, read by the dashboard
            self.put("checkpoint", checkpoint)
            self.put("tick", self.get("tick") + 1)
            if observation is not None:
                self.put("observation", observation)

    # ---- fills ---------------------------------------------------------
    def _insert_fill(self, tick, now, side, action, qty, price, notional, fee, realized, realized_net, reason, quote):
        cur = self.db.execute(
            "INSERT INTO fills(tick,created,side,action,qty,price,notional,fee,realized,realized_net,reason,quote)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (tick, now, side, action, str(qty), str(price), str(notional), str(fee),
             str(realized), str(realized_net), reason, json.dumps(quote.json())),
        )
        return self._fill_row(cur.lastrowid)

    def _fill_row(self, fill_id):
        r = self.db.execute(
            "SELECT id,tick,created,side,action,qty,price,notional,fee,realized,realized_net,reason,quote"
            " FROM fills WHERE id=?", (fill_id,)).fetchone()
        keys = ["id", "tick", "created", "side", "action", "qty", "price", "notional", "fee",
                "realized", "realized_net", "reason", "quote"]
        d = dict(zip(keys, r))
        d["quote"] = json.loads(d["quote"])
        return d

    def fills(self, limit=None):
        sql = "SELECT id FROM fills ORDER BY id"
        if limit is not None:  # limit=0 asks for no rows, not for all of them
            sql = f"SELECT id FROM (SELECT id FROM fills ORDER BY id DESC LIMIT {int(limit)}) ORDER BY id"
        return [self._fill_row(r[0]) for r in self.db.execute(sql).fetchall()]

    def _add(self, key, amount):
        self.put(key, str(D(self.get(key)) + amount))

    # ---- position lifecycle -------------------------------------------
    def _open(self, side, quote, tick, now, action, reason):
        if self.position is not None:
            raise ValueError("Already positioned")
        if side not in SIGN:
            raise ValueError("Invalid side")
        e = self.entry_size(quote, side)
        if e["qty"] < quote.minimum_base or e["notional"] < quote.minimum_quote:
            raise ValueError("Below minimum")
        # No cash check: with no position equity == cash, so margin + fee <= 0.334 * cash always.
        self.put("cash", str(self.cash - e["margin"] - e["fee"]))
        self.put("position", {
            "side": side, "qty": str(e["qty"]), "entry": str(e["price"]), "margin": str(e["margin"]),
            "notional": str(e["notional"]), "open_fee": str(e["fee"]), "opened_tick": tick, "opened_at": now,
        })
        self._add("fees_paid", e["fee"])
        return self._insert_fill(tick, now, side, action, e["qty"], e["price"], e["notional"], e["fee"],
                                 D(0), D(0), reason, quote)

    def _close_math(self, quote):
        """Everything closing the open position at `quote` would cost and pay. `_close` and
        `projected_close_net` both read it, so a prediction can never drift from the record."""
        p = self.position
        if p is None:
            raise ValueError("No position")
        qty, entry = D(p["qty"]), D(p["entry"])
        price = self.mark_price(quote)  # LONG closes at bid, SHORT at ask
        realized = qty * (price - entry) * SIGN[p["side"]]
        fee = qty * price * D(self.s.taker_fee)
        return {"qty": qty, "price": price, "realized": realized, "fee": fee,
                "net": realized - fee - D(p["open_fee"])}

    def projected_close_net(self, quote):
        """The `realized_net` `_close` would record if the position closed at `quote` right now:
        gross move minus the close fee minus the fee already paid to open."""
        return self._close_math(quote)["net"]

    def projected_flip_net(self, quote):
        """What a flip at `quote` would be worth end to end: the close's net minus the taker fee the
        re-entry immediately sinks. The guard requires this to reach `flip_min_net`, so an allowed
        flip is a fee-neutral round trip rather than one that only pays for its own exit.

        The re-entry fee prices `target_notional` off the equity the close leaves behind, which is a
        forecast in two small ways: the lot rounding in `entry_size` is not applied, and the sunk
        open fee is not added back. Both are worth well under one lot of fee."""
        p = self.position
        if p is None:
            raise ValueError("No position")
        net = self._close_math(quote)["net"]
        post_equity = self.cash + D(p["margin"]) + net
        return net - self.target_notional(post_equity) * D(self.s.taker_fee)

    def _close(self, quote, tick, now, action, reason):
        p = self.position
        if p is None:
            raise ValueError("No position")
        m = self._close_math(quote)
        qty, price, realized, fee = m["qty"], m["price"], m["realized"], m["fee"]
        self.put("cash", str(self.cash + D(p["margin"]) + realized - fee))
        self.put("position", None)
        self._add("fees_paid", fee)
        self._add("realized_pnl", realized)
        return self._insert_fill(tick, now, p["side"], action, qty, price, qty * price, fee,
                                 realized, m["net"], reason, quote)

    def open_position(self, side, quote, tick, now, action="OPEN", reason="", last_attempt=None):
        with self.transaction():
            fill = self._open(side, quote, tick, now, action, reason)
            if last_attempt is not None:
                self.put("last_attempt", last_attempt)  # cooldown stamp lands in the fill's own transaction
            return fill

    def close_position(self, quote, tick, now, action="CLOSE", reason=""):
        """Test helper: the engine closes only via flip() or liquidation (spec §7.2 has no 청산 banner)."""
        with self.transaction():
            return self._close(quote, tick, now, action, reason)

    def flip(self, side, quote, tick, now, last_attempt=None):
        with self.transaction():
            closed = self._close(quote, tick, now, "FLIP_CLOSE", "opposite signal")
            opened = self._open(side, quote, tick, now, "FLIP_OPEN", "opposite signal")
            if last_attempt is not None:
                self.put("last_attempt", last_attempt)
            return [closed, opened]

    def bankrupt(self, quote, tick, now):
        """Terminal: record the BANKRUPT row and halt in one transaction."""
        with self.transaction():
            self.put("halted", "bankrupt")
            return self._insert_fill(tick, now, None, "BANKRUPT", D(0), self.mark_price(quote),
                                     D(0), D(0), D(0), D(0), "cash below minimum margin", quote)

    def liquidate_if_needed(self, quote, tick, now):
        p = self.position
        if p is None:
            return None
        qty, margin = D(p["qty"]), D(p["margin"])
        mark = self.mark_price(quote)
        if margin + self.unrealized(quote) > qty * mark * D(self.s.mmr):
            return None
        with self.transaction():
            self.put("position", None)
            self._add("realized_pnl", -margin)
            self.put("liquidations", int(self.get("liquidations")) + 1)
            return self._insert_fill(tick, now, p["side"], "LIQUIDATION", qty, mark, qty * mark, D(0),
                                     -margin, -margin - D(p["open_fee"]), "maintenance margin", quote)

    def apply_funding(self, rate, expire_ms, source, quote, tick, now):
        p = self.position
        # The venue's expire_time is the boundary it is counting down to, and right after a
        # rollover it can still name the one that just passed (or regress to seconds). Storing it
        # unchanged leaves funding due on every 60 s tick: up to 480 charges per 8 h interval,
        # silently. The schedule only ever moves forward from now.
        expire = int(expire_ms)
        if expire <= int(now * 1000):
            expire = int(now * 1000) + 8 * 3600 * 1000
        with self.transaction():
            self.put("next_funding", expire)
            if p is None:
                return None
            qty = D(p["qty"])
            amount = qty * self.mark_price(quote) * rate  # positive: longs pay
            paid = amount if p["side"] == "LONG" else -amount
            self.put("cash", str(self.cash - paid))
            self._add("funding_paid", paid)
            return self._insert_fill(tick, now, p["side"], "FUNDING", qty, self.mark_price(quote),
                                     qty * self.mark_price(quote), paid, D(0), -paid, f"{source}:{rate}", quote)

    def is_bankrupt(self, quote):
        """No position and too little cash to open a minimum-size position on either side (spec §4).
        Reuses entry_size so this is identical by construction to _open's "Below minimum" guard.
        Replaces an earlier min_notional/leverage + fee formula, which ignored the 33% margin
        fraction and so under-counted the cash actually needed to clear entry_size's floor."""
        if self.position is not None:
            return False
        for side in ("LONG", "SHORT"):
            e = self.entry_size(quote, side)
            if e["qty"] >= quote.minimum_base and e["notional"] >= quote.minimum_quote:
                return False
        return True

    def close(self):
        self.db.close()
