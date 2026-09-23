import pytest

from stonkfly.config import D
from stonkfly.perp.config import PerpSettings


def test_defaults_match_spec():
    s = PerpSettings()
    assert s.venue == "orangex-perp"
    assert s.instrument == "BTC-USDT-PERPETUAL"
    assert s.label == "BTC-PERP"
    assert D(s.capital) == D("1000")
    assert s.leverage == 20
    assert D(s.margin_fraction) == D("0.33")
    assert D(s.taker_fee) == D("0.0006")
    assert D(s.flip_min_net) == D("0")  # 뒤집기는 수수료 보합권 이상에서만
    assert D(s.mmr) == D("0.005")
    assert D(s.funding_fallback) == D("0.0001")
    assert D(s.reward_deadband) == D("1.0")
    assert s.interval_seconds == 60 and s.max_quote_age == 15
    assert D(s.spread_limit) == D("0.005")
    assert (D(s.price_increment), D(s.base_increment), D(s.minimum_base), D(s.minimum_quote)) == (
        D("0.1"), D("0.001"), D("0.001"), D("5"))
    assert s.outage_ticks == 10
    assert s.neural_ms == 500 and s.neural_bin_ms == 10 and s.pulse_ms == 200
    assert s.pulse_current == 20 and s.decoder_threshold_hz == 2 and s.learning is True
    assert s.fly_name == "초파리"


@pytest.mark.parametrize(
    "changes",
    [
        dict(leverage=0),
        dict(leverage=126),
        dict(leverage=2.5),
        dict(margin_fraction="0"),
        dict(margin_fraction="1.01"),
        dict(taker_fee="-0.001"),
        dict(flip_min_net="nan"),  # 음수는 허용, 비유한값은 금지
        dict(flip_min_net="많이"),
        dict(mmr="0.05"),  # >= 1/leverage: 진입 즉시 청산이라 금지
        dict(capital="0"),
        dict(interval_seconds=59),
        dict(reward_deadband="0"),
        dict(neural_bin_ms=11),
        dict(pulse_ms=600),
        dict(outage_ticks=0),
    ],
)
def test_bounds(changes):
    with pytest.raises(ValueError):
        PerpSettings(**changes)


def test_flip_min_net_accepts_a_negative_budget():
    assert D(PerpSettings(flip_min_net="-5").flip_min_net) == D("-5")


def test_signature_changes_with_any_field():
    a, b = PerpSettings(), PerpSettings(leverage=10)
    assert a.signature() == PerpSettings().signature()
    assert a.signature() != b.signature()
