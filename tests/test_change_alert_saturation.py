# tests/test_change_alert_saturation.py
"""F137 characterization — the saturated-band ceiling silently disables two alert rules.

These tests PIN THE CURRENT (broken) BEHAVIOUR so that the fix, when the user has
chosen it, shows up as a deliberate, visible change here rather than as a silent
drift. They assert nothing about what the rules SHOULD do.

Background. `bands.band_word` maps a value onto five words whose top band starts at
0.30. The demand and gap numbers are running totals that have grown past 4.5 — every
stored run since 2026-07-31 sits far above 0.30, so both values are pinned in the top
band. Two ladder rules are defined purely in terms of that band:

  * `gap-band-changed`   fires when band_word(gap) differs from the prior run's.
  * `demand-reversal`    fires when band_word(demand) RANKS LOWER than the prior run's
                         and the gap moved toward glut.

Both are structurally unreachable once the two numbers are above the ceiling, no
matter how large the underlying move is. F136 removed the same ceiling from the
brief's headline demand/supply lines (see bands.change_line); the alert ladder still
has it.
"""
from __future__ import annotations
import statistics

from gpu_agent import bands
from gpu_agent.change import StateVector, _raw_alert

# Real values read off the stored scorecards (store/chips.merchant-gpu):
#   2026-07-v21  demand 3.393  supply -0.713  gap 4.107
#   2026-08-v17  demand 4.507  supply -0.093  gap 4.600
# and the largest single-run demand fall on record:
#   2026-08-v12  demand 4.407  gap 4.353   ->   2026-08-v13  demand 3.833  gap 3.860
LIVE_JUL, LIVE_AUG = (3.393, 4.107), (4.507, 4.600)
BIG_DROP_FROM, BIG_DROP_TO = (4.407, 4.353), (3.833, 3.860)


def _st(demand, sdgi, *, constraint=None, as_of="2026-08"):
    return StateVector(asOf=as_of, demand=demand, supply=0.0, sdgi=sdgi,
                       constraintLabel=constraint)


def test_every_stored_run_since_july_sits_in_the_top_band():
    """The ceiling is not hypothetical: production values saturate both bands."""
    for demand, gap in (LIVE_JUL, LIVE_AUG, BIG_DROP_FROM, BIG_DROP_TO):
        assert bands.band_word(demand) == "accelerating"
        assert bands.band_word(gap) == "accelerating"


def test_gap_band_changed_cannot_fire_on_the_real_july_to_august_move():
    """The gap rose 0.49 (4.107 -> 4.600) and the rule stayed silent."""
    color, trig = _raw_alert(_st(*LIVE_AUG), _st(*LIVE_JUL, as_of="2026-07"),
                             "2026-07", None)
    assert "gap-band-changed" not in trig
    assert color == "green"


def test_gap_band_changed_cannot_fire_on_an_arbitrarily_large_move():
    """Even a 4-point collapse in the gap leaves the rule silent, because both ends
    of the move are still inside the one top band."""
    _color, trig = _raw_alert(_st(9.0, 9.0), _st(9.0, 5.0, as_of="2026-07"),
                             "2026-07", None)
    assert "gap-band-changed" not in trig


def test_demand_reversal_cannot_fire_on_the_largest_recorded_demand_fall():
    """Demand fell 0.574 and the gap fell 0.493 at the same time — exactly the
    shape the rule was written to catch — and it stayed silent."""
    color, trig = _raw_alert(_st(*BIG_DROP_TO), _st(*BIG_DROP_FROM, as_of="2026-07"),
                             "2026-07", None)
    assert "demand-reversal" not in trig
    assert color == "green"


def test_demand_reversal_needs_demand_to_fall_below_the_top_band_floor():
    """Concretely: from today's 4.51, demand would have to lose more than 4.2 points
    in one run — drop under 0.30 — before the rule can speak at all."""
    today = 4.507
    survives = [drop for drop in (0.5, 1.0, 2.0, 3.0, 4.0)
                if bands.band_word(today - drop) == "accelerating"]
    assert survives == [0.5, 1.0, 2.0, 3.0, 4.0]
    assert bands.band_word(today - 4.3) != "accelerating"


def test_the_two_dead_rules_are_the_only_featured_metric_alert_tags():
    """Knock-on effect: registry/featured-metrics.json tags exactly these two rules,
    so the dashboard's 'shown because it tracks today's alert' reason can never be
    chosen either. Pinning the coupling so the fix has to consider it."""
    from gpu_agent.dashboard.featured import load_library
    tags = {t for m in load_library() for t in m["alertRuleTags"]}
    assert tags == {"gap-band-changed", "demand-reversal"}


def test_existing_alert_tests_only_exercise_pre_drift_values():
    """Why the suite never caught this: the ladder tests use values from before the
    indices drifted (0.10 / 0.35 / -0.10), all of which straddle real band edges."""
    assert bands.band_word(0.10) == "firm"
    assert bands.band_word(0.35) == "accelerating"
    assert bands.band_word(-0.10) == "softening"
    # ...whereas nothing in production has been below the top band since July.
    assert min(statistics.mean(LIVE_JUL), statistics.mean(LIVE_AUG)) > 0.30
