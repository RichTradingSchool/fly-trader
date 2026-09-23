"""Net-worth milestones for the fly's room. The runner decides; the dashboard only shows."""

import json
from pathlib import Path

from ..config import D

MILESTONES_PATH = Path(__file__).with_name("milestones.json")


def load_milestones():
    table = json.loads(MILESTONES_PATH.read_text(encoding="utf-8"))
    return sorted(table, key=lambda m: m["equity"])


def room_update(equity, unlocked):
    """Return (new_unlocked, events). Unlocks ascend; repossessions descend."""
    equity = D(equity)
    table = load_milestones()
    have = list(unlocked)
    events = []
    for m in table:
        if equity >= D(m["equity"]) and m["item"] not in have:
            have.append(m["item"])
            events.append({"type": "unlock", "item": m["item"], "label": m["label"], "equity_threshold": m["equity"]})
    for m in reversed(table):
        if equity < D(m["equity"]) and m["item"] in have:
            have.remove(m["item"])
            events.append({"type": "repossess", "item": m["item"], "label": m["label"], "equity_threshold": m["equity"]})
    order = {m["item"]: i for i, m in enumerate(table)}
    have.sort(key=lambda item: order[item])
    return have, events
