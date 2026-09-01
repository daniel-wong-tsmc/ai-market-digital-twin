# tests/test_change_alert_saturation.py
"""F137 — the saturated-band ceiling is gone from the alert ladder.

These started life (commit 5369831) as characterization tests pinning the BROKEN
behaviour. The user chose the fix on 2026-09-01, so they now pin the repair: the same
real-world moves that used to produce green must now speak, and the band words must no
longer appear anywhere in the ladder's reasoning.

Background. `bands.band_word` maps a value onto five words whose top band starts at
0.30 and has no upper edge. The demand and gap numbers are running totals that have
grown past 4.5, so both were pinned in the top word. Two ladder rules were defined
purely in terms of that word:

  * `gap-band-changed`   fired when band_word(gap) differed from the prior run's.
  * `demand-reversal`    fired when band_word(demand) RANKED LOWER than the prior run's
                         and the gap moved toward glut.

Both were structurally unreachable, no matter how large the underlying move. F136 had
already removed the same ceiling from the brief's headline demand/supply lines (see
bands.change_line); this removes it from the alert ladder.
"""
from __future__ import annotations
import statistics

from gpu_agent import bands, change
from gpu_agent.change import StateVector, _raw_alert

# Real values read off the stored scorecards (store/chips.merchant-gpu):
#   2026-07-v21  demand 3.393  supply -0.713  gap 4.107
#   2026-08-v17  demand 4.507  supply -0.093  gap 4.600
# and the largest single-run demand fall on record:
#   2026-08-v12  demand 4.407  gap 4.353   ->   2026-08-v13  demand 3.833  gap 3.860
LIVE_JUL, LIVE_AUG = (3.393, 4.107), (4.507, 4.600)
BIG_DROP_FROM, BIG_DROP_TO = (4.407, 4.353), (3.833, 3.860)

# A calm stretch of recent history at the live scale: runs about 0.20 apart, which is
# the real median run-to-run gap move in August.
CALM_GAP = [4.0, 4.2, 4.0, 4.2, 4.0, 4.2, 4.0, 4.2]
CALM_DEM = [4.0, 4.1, 4.0, 4.1, 4.0, 4.1, 4.0, 4.1]


def _st(demand, sdgi, *, constraint=None, as_of="2026-08"):
    return StateVector(asOf=as_of, demand=demand, supply=0.0, sdgi=sdgi,
                       constraintLabel=constraint)


def test_every_stored_run_since_july_still_sits_in_the_top_band():
    """The ceiling itself has not moved — bands.py is untouched, and it is still right
    for the dashboard tiles and the appendix table. The ladder simply stopped using it."""
    for demand, gap in (LIVE_JUL, LIVE_AUG, BIG_DROP_FROM, BIG_DROP_TO):
        assert bands.band_word(demand) == "accelerating"
        assert bands.band_word(gap) == "accelerating"


def test_the_ladder_no_longer_asks_a_band_question():
    """The old mechanism is gone, not merely retuned: no band-word call survives in the
    alert ladder, so no future value can saturate it back into silence."""
    import inspect
    src = inspect.getsource(change._raw_alert)
    assert "band_word" not in src and "_band_rank" not in src
    assert not hasattr(change, "_band_rank")
    assert "gap-band-changed" not in change._YELLOW_RULES


def test_the_real_july_to_august_gap_move_now_speaks():
    """The gap rose 0.49 (4.107 -> 4.600). Under the band test this was green."""
    color, trig, sizes = _raw_alert(_st(*LIVE_AUG), _st(*LIVE_JUL, as_of="2026-07"),
                                    "2026-07", None,
                                    gap_history=CALM_GAP + [LIVE_JUL[1]],
                                    demand_history=CALM_DEM + [LIVE_JUL[0]])
    assert color == "yellow" and "gap-moved-sharply" in trig
    assert sizes["gap-moved-sharply"].startswith("up 0.49")


def test_an_arbitrarily_large_gap_move_can_no_longer_hide_inside_one_band():
    """A 4-point collapse used to leave the rule silent because both ends of the move
    were still inside the one top word."""
    _color, trig, _sizes = _raw_alert(_st(9.0, 5.0), _st(9.0, 9.0, as_of="2026-07"),
                                      "2026-07", None,
                                      gap_history=[9.0, 9.2, 9.0, 9.2, 9.0],
                                      demand_history=[9.0] * 5)
    assert "gap-moved-sharply" in trig


def test_the_largest_recorded_demand_fall_now_goes_orange():
    """Demand fell 0.574 and the gap fell 0.493 at the same time — exactly the shape the
    rule was written to catch. Under the band test this run was green."""
    color, trig, sizes = _raw_alert(_st(*BIG_DROP_TO), _st(*BIG_DROP_FROM, as_of="2026-07"),
                                    "2026-07", None,
                                    gap_history=CALM_GAP + [BIG_DROP_FROM[1]],
                                    demand_history=CALM_DEM + [BIG_DROP_FROM[0]])
    assert color == "orange" and "demand-reversal" in trig
    assert sizes["demand-reversal"].startswith("demand fell 0.57")


def test_demand_no_longer_has_to_fall_4_points_to_be_heard():
    """The old rule needed demand to drop under the 0.30 floor — from today's 4.51 that
    is a fall of more than 4.2 in a single run, against a usual move of about 0.13."""
    today = 4.507
    assert all(bands.band_word(today - drop) == "accelerating"
               for drop in (0.5, 1.0, 2.0, 3.0, 4.0))
    # ...whereas the repaired rule hears a 0.30 fall against a calm history. (The run being
    # compared against is the last value of the history: demand 4.1, gap 4.2.)
    _c, trig, _s = _raw_alert(_st(CALM_DEM[-1] - 0.30, 4.10),
                              _st(CALM_DEM[-1], CALM_GAP[-1], as_of="2026-07"),
                              "2026-07", None,
                              gap_history=CALM_GAP, demand_history=CALM_DEM)
    assert "demand-reversal" in trig


def test_the_featured_metric_tags_track_the_renamed_rule():
    """registry/featured-metrics.json tags exactly the two repaired rules, so the
    dashboard's 'shown because it tracks today's alert' reason is reachable again.
    See tests/dashboard/test_featured.py for the render-level proof."""
    from gpu_agent.dashboard.featured import load_library
    tags = {t for m in load_library() for t in m["alertRuleTags"]}
    assert tags == {"gap-moved-sharply", "demand-reversal"}


def test_the_old_pre_drift_fixtures_no_longer_stand_in_for_production():
    """Why the suite missed this for a month: the ladder tests used 0.10 / 0.35 / -0.10,
    values from before the indices drifted, all of which straddle real band edges.
    Nothing in production has been below the top band since July."""
    assert bands.band_word(0.10) == "firm"
    assert bands.band_word(0.35) == "accelerating"
    assert bands.band_word(-0.10) == "softening"
    assert min(statistics.mean(LIVE_JUL), statistics.mean(LIVE_AUG)) > 0.30
