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


# --- C46: effect catalog ---------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from app.bulbs.base import SegmentPattern, capabilities_for  # noqa: E402
from app.effects import (  # noqa: E402
    EffectLayer,
    EffectSpec,
    build_effect,
    chase_frame,
    resolve_effect,
)

STRIP = capabilities_for("govee", 20)
BULB = capabilities_for("wiz")
RED, BLUE = (255, 0, 0), (0, 0, 255)


def test_build_effect_pulse_matches_build_pattern():
    spec = EffectSpec("pulse", {"pulses": 5, "duration_s": 6.0, "brightness": 255})
    assert build_effect(spec, G, Y, BULB) == build_pattern(EffectConfig(), G, Y)


def test_build_effect_rejects_unsupported_kind_and_unknown_things():
    with pytest.raises(ValueError, match="does not support 'chase'"):
        build_effect(EffectSpec("chase"), G, Y, BULB, "lamp")
    with pytest.raises(ValueError, match="unknown effect kind"):
        build_effect(EffectSpec("sparkle"), G, Y, STRIP)
    with pytest.raises(ValueError, match="no parameter 'chunk'"):
        build_effect(EffectSpec("pulse", {"chunk": 3}), G, Y, STRIP)


def test_chase_frame_rotates_and_wraps():
    assert chase_frame(6, 0, 2, (G, Y)) == [G, G, Y, Y, G, G]
    assert chase_frame(6, 1, 2, (G, Y)) == [Y, G, G, Y, Y, G]
    assert chase_frame(6, 4, 2, (G, Y)) == chase_frame(6, 0, 2, (G, Y))


def test_chase_builds_a_segment_pattern_for_the_fixture():
    p = build_effect(EffectSpec("chase", {"duration_s": 2.0}), G, Y, STRIP)
    assert isinstance(p, SegmentPattern)
    assert p.segments == 20
    assert p.duration_s == pytest.approx(2.0)
    assert p.frames[0].colors[:4] == (G, G, G, G)
    assert p.frames[0].colors[4:8] == (Y, Y, Y, Y)
    assert p.frames[-1].colors != p.frames[0].colors  # it moved


def test_chase_at_the_cap_is_accepted_and_over_it_is_refused():
    build_effect(EffectSpec("chase", {"speed": 8, "chunk": 4, "duration_s": 3}), G, Y, STRIP)
    with pytest.raises(ValueError, match="cap"):
        build_effect(EffectSpec("chase", {"speed": 10, "chunk": 4}), G, Y, STRIP)


# --- C47: resolver ---------------------------------------------------------------------------


def cfg(fixture_effects=None, **effect):
    return SimpleNamespace(
        score_effect=EffectConfig(**effect), fixture_effects=fixture_effects or {}
    )


def team(color=None, alt=None, effect=None, fixture_effects=None):
    return SimpleNamespace(color=color, alt_color=alt, effect=effect,
                           fixture_effects=fixture_effects or {})


ESPN = (RED, BLUE)


def test_global_only_resolves_like_today():
    r = resolve_effect(cfg(), team(), "lamp", ESPN)
    assert r.spec == EffectSpec("pulse", {"pulses": 5, "duration_s": 6.0, "brightness": 255})
    assert (r.primary, r.alternate) == ESPN
    assert build_effect(r.spec, r.primary, r.alternate, BULB) == build_pattern(
        EffectConfig(), *ESPN)


def test_each_layer_overrides_the_one_before():
    c = cfg({"strip": EffectLayer("chase", {"chunk": 5}, (1, 1, 1))}, color=(9, 9, 9))
    t = team(color=(2, 2, 2), effect=EffectLayer(params={"speed": 5}),
             fixture_effects={"strip": EffectLayer(params={"chunk": 6}, alt_color=(3, 3, 3))})
    r = resolve_effect(c, t, "strip", ESPN)
    assert r.spec.kind == "chase"
    assert r.spec.params["chunk"] == 6  # team x fixture beats fixture
    assert r.spec.params["speed"] == 5  # team layer
    assert r.primary == (2, 2, 2)  # team color beats fixture beats global
    assert r.alternate == (3, 3, 3)  # team x fixture alt color; ESPN not used


def test_fields_fall_through_and_other_fixtures_are_unaffected():
    c = cfg({"strip": EffectLayer("chase")})
    t = team(color=(2, 2, 2))
    assert resolve_effect(c, t, "lamp", ESPN).spec.kind == "pulse"
    strip = resolve_effect(c, t, "strip", ESPN)
    assert strip.spec.kind == "chase"
    assert strip.spec.params == {"duration_s": 6.0, "brightness": 255}  # pulses dropped
    assert strip.alternate == BLUE  # ESPN fallback for colors only
