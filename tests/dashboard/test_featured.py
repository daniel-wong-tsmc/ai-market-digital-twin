from gpu_agent.dashboard.featured import (
    MetricReading, Selection, load_library, normalized_change, select_featured,
)


def _r(mid, value, prior, priority, tags=(), scale=0.5):
    return MetricReading(
        metric_id=mid, label=mid, plain_label=mid, unit="score",
        value=value, prior=prior, scale=scale, static_priority=priority,
        alert_rule_tags=tuple(tags), how_to_read="how", honesty_note=None,
        display=f"{value:+.2f}")


def test_library_loads_four_entries_with_required_keys():
    lib = load_library()
    assert len(lib) == 4
    for e in lib:
        for k in ("id", "label", "plainLabel", "unit", "source", "howToRead",
                  "staticPriority", "scale", "alertRuleTags"):
            assert k in e, f"{e.get('id')} missing {k}"


def test_rule_tag_hit_beats_bigger_move():
    quiet_tagged = _r("gap", 0.10, 0.09, priority=2, tags=["gap-band-changed"])
    big_mover = _r("price", 3.00, 1.00, priority=1)
    sel = select_featured([big_mover, quiet_tagged], triggers=["gap-band-changed"])
    assert sel.reading.metric_id == "gap" and sel.reason_code == "alert-rule"


def test_two_tagged_hits_tie_break_by_priority():
    a = _r("a", 1.0, 1.0, priority=3, tags=["gap-band-changed"])
    b = _r("b", 1.0, 1.0, priority=2, tags=["high-call-moved"])
    sel = select_featured([a, b], triggers=["gap-band-changed", "high-call-moved"])
    assert sel.reading.metric_id == "b"


def test_biggest_normalized_move_wins_scale_matters():
    # raw move 0.30/scale 0.5 = 0.6  beats  raw move 1.00/scale 2.0 = 0.5
    small_scale = _r("idx", 0.40, 0.10, priority=4, scale=0.5)
    big_scale = _r("price", 3.00, 2.00, priority=1, scale=2.0)
    sel = select_featured([big_scale, small_scale], triggers=[])
    assert sel.reading.metric_id == "idx" and sel.reason_code == "biggest-move"


def test_move_tie_breaks_by_priority():
    a = _r("a", 0.30, 0.10, priority=3)
    b = _r("b", 0.30, 0.10, priority=2)
    assert select_featured([a, b], triggers=[]).reading.metric_id == "b"


def test_no_priors_falls_back_to_priority():
    a = _r("a", 0.3, None, priority=2)
    b = _r("b", 0.4, None, priority=1)
    sel = select_featured([a, b], triggers=[])
    assert sel.reading.metric_id == "b" and sel.reason_code == "priority"


def test_zero_moves_fall_back_to_priority():
    a = _r("a", 0.3, 0.3, priority=1)
    sel = select_featured([a], triggers=[])
    assert sel.reason_code == "priority"


def test_unknown_triggers_are_ignored_and_empty_readings_give_none():
    a = _r("a", 0.3, None, priority=1, tags=["gap-band-changed"])
    assert select_featured([a], triggers=["no-such-rule"]).reason_code == "priority"
    assert select_featured([], triggers=["gap-band-changed"]) is None


def test_normalized_change():
    assert normalized_change(_r("a", 0.40, 0.10, 1, scale=0.5)) == 0.6
    assert normalized_change(_r("a", 0.40, None, 1)) is None
