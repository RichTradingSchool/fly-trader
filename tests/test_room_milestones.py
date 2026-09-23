from stonkfly.config import D
from stonkfly.perp.room import load_milestones, room_update


def test_table_is_ascending_and_complete():
    m = load_milestones()
    thresholds = [x["equity"] for x in m]
    assert thresholds == sorted(thresholds) == [1200, 1500, 2000, 3000, 5000, 10000, 20000, 50000]
    assert all({"equity", "item", "label", "slot"} <= set(x) for x in m)
    assert len({x["item"] for x in m}) == len(m)


def test_unlock_repossess_and_reunlock_in_order():
    unlocked, ev = room_update(D("1000"), [])
    assert unlocked == [] and ev == []
    unlocked, ev = room_update(D("1600"), unlocked)
    assert unlocked == ["coffee_machine", "dual_monitor"]
    assert [e["type"] for e in ev] == ["unlock", "unlock"] and ev[0]["item"] == "coffee_machine"
    unlocked, ev = room_update(D("1450"), unlocked)
    assert unlocked == ["coffee_machine"] and ev == [{"type": "repossess", "item": "dual_monitor", "label": "듀얼 모니터", "equity_threshold": 1500}]
    unlocked, ev = room_update(D("2100"), unlocked)
    assert unlocked == ["coffee_machine", "dual_monitor", "gold_chain"] and len(ev) == 2


def test_multiple_levels_in_one_tick_are_ordered_low_to_high():
    unlocked, ev = room_update(D("60000"), [])
    assert [e["equity_threshold"] for e in ev] == [1200, 1500, 2000, 3000, 5000, 10000, 20000, 50000]
    unlocked, ev = room_update(D("900"), unlocked)
    assert unlocked == [] and [e["equity_threshold"] for e in ev] == [50000, 20000, 10000, 5000, 3000, 2000, 1500, 1200]
