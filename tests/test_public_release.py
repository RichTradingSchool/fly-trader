"""Distribution guarantees that must hold without the connectome data (these run in CI)."""

import subprocess
import sys
from types import SimpleNamespace

import pytest

from stonkfly.perp.config import PerpSettings
from stonkfly.perp.runner import build_settings, env_settings


def test_live_trading_is_disabled_on_every_venue(tmp_path):
    for venue in ["coinbase-spot", "orangex-perp"]:
        r = subprocess.run([sys.executable, "-m", "stonkfly", "run", "--venue", venue, "--live", "--out", str(tmp_path / venue)],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 2 and "Live" in r.stderr, (venue, r.stderr)
        assert not (tmp_path / venue).exists(), "nothing may be created before the refusal"


def test_env_settings_reads_the_season_choices():
    assert env_settings({}) == {}
    got = env_settings({"FLY_NAME": " 버즈 ", "FLY_LEVERAGE": "10", "FLY_MARGIN": "0.25", "UNRELATED": "x"})
    assert got == {"fly_name": "버즈", "leverage": 10, "margin_fraction": "0.25"}


@pytest.mark.parametrize("env", [{"FLY_LEVERAGE": "20.5"}, {"FLY_LEVERAGE": "-3"}, {"FLY_MARGIN": "a lot"},
                                 {"FLY_NAME": "초" * 21}])
def test_env_settings_rejects_bad_values(env):
    with pytest.raises(SystemExit):
        env_settings(env)


def test_build_settings_applies_env_and_keeps_the_default_signature(monkeypatch):
    a = SimpleNamespace(neural_ms=500, frozen=False)
    for var in ["FLY_NAME", "FLY_LEVERAGE", "FLY_MARGIN"]:
        monkeypatch.delenv(var, raising=False)
    default = build_settings(a)
    assert default.signature() == PerpSettings(neural_ms=500.0, pulse_ms=200).signature()
    monkeypatch.setenv("FLY_NAME", "초파리")  # the default name changes nothing
    assert build_settings(a).signature() == default.signature()
    monkeypatch.setenv("FLY_LEVERAGE", "10")
    s = build_settings(a)
    assert s.leverage == 10 and s.signature() != default.signature()
    monkeypatch.setenv("FLY_LEVERAGE", "500")  # PerpSettings range check
    with pytest.raises(SystemExit):
        build_settings(a)
