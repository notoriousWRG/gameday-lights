import pytest

from app.bulbs.base import PatternError
from app.effects import EffectConfig, build_pattern, parse_color

G, Y = (0, 255, 0), (255, 182, 18)


@pytest.mark.parametrize(
    "s,want",
    [("#ffb612", Y), ("FFB612", Y), ("0, 255, 0", G), (" #00ff00 ", G)],
)
def test_parse_color(s, want):
    assert parse_color(s) == want


@pytest.mark.parametrize("s", ["", "#fff", "1,2", "1,2,300", "zzzzzz", "-1,0,0"])
def test_parse_color_rejects(s):
    with pytest.raises(ValueError):
        parse_color(s)


def test_default_effect():
    p = build_pattern(EffectConfig(), G, Y)
    assert len(p.steps) == 10
    assert all(s.hold_s == pytest.approx(0.6) for s in p.steps)
    assert [s.color for s in p.steps[:3]] == [G, Y, G]
    assert p.duration_s == pytest.approx(6.0)


def test_config_colors_override_team():
    p = build_pattern(EffectConfig(color=(1, 2, 3), alt_color=(4, 5, 6)), G, Y)
    assert [s.color for s in p.steps[:2]] == [(1, 2, 3), (4, 5, 6)]


def test_too_fast_raises_pattern_error():
    with pytest.raises(PatternError):
        build_pattern(EffectConfig(pulses=10, duration_s=6.0), G, Y)


def test_zero_pulses_rejected():
    with pytest.raises(ValueError):
        build_pattern(EffectConfig(pulses=0), G, Y)
