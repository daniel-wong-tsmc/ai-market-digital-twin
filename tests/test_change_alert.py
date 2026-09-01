# tests/test_change_alert.py
from __future__ import annotations
from gpu_agent.schema.scorecard import Scorecard, DemandSupply
from gpu_agent.schema.finding import Confidence
from gpu_agent.thesis import ThesisBook, ThesisEntry
from gpu_agent.change import (StateVector, AlertState, _raw_alert, _fold_displayed,
                              alert_state, build_state)

# F137 (user-decided 2026-09-01): the gap and demand rules no longer compare band WORDS
# (which saturate — see tests/test_change_alert_saturation.py). They compare each run's
# move against how much the series usually moves, read from the recent history the
# caller passes in. A calm history whose runs move about 0.10 apiece makes a 0.40 jump
# "much more than usual" at any absolute level, which is the whole point.
CALM = [0.00, 0.10, 0.00, 0.10, 0.00, 0.10, 0.00, 0.10]        # usual move ~0.10
CALM_HIGH = [9.00, 9.10, 9.00, 9.10, 9.00, 9.10, 9.00, 9.10]   # same swing, huge level


def _conf():
    return Confidence(level="medium", basis="b")


def _st(demand=0.10, supply=0.10, sdgi=0.10, constraint=None, as_of="2026-07-08"):
    return StateVector(asOf=as_of, demand=demand, supply=supply, sdgi=sdgi,
                       constraintLabel=constraint)


def _entry(eid="t1", conviction="high", status="registered", verdict="strengthened",
           direction=1, changed="2026-07-05"):
    return ThesisEntry(id=eid, title="T", statement="s", lens="demand", status=status,
                       conviction=conviction, lastVerdict=verdict, lastDirection=direction,
                       streak=2, mechanism="m", falsifiableTrigger="t", sensitivity="s",
                       createdAsOf="2026-06", lastChangedAsOf=changed,
                       lastJudgedAsOf=changed)


def test_green_when_nothing_moved():
    color, trig, sizes = _raw_alert(_st(), _st(as_of="2026-07-01"), "2026-07-01", None)
    assert color == "green" and trig == [] and sizes == {}


def test_yellow_when_the_gap_moves_much_more_than_usual():
    # history swings about 0.10 per run; this run jumps 0.50 off the last value (0.10).
    color, trig, sizes = _raw_alert(_st(sdgi=0.60), _st(sdgi=0.10, as_of="2026-07-01"),
                                    "2026-07-01", None, gap_history=CALM, demand_history=CALM)
    assert color == "yellow" and "gap-moved-sharply" in trig
    assert "0.50" in sizes["gap-moved-sharply"]
    assert "times its usual run-to-run move" in sizes["gap-moved-sharply"]


def test_the_gap_rule_works_the_same_at_any_level():
    """F137's point: the old band test went silent once the numbers passed 0.30. The
    same 0.50 jump on a series sitting at 9.0 must read exactly the same."""
    _c, low, _s = _raw_alert(_st(sdgi=0.60), _st(sdgi=0.10, as_of="2026-07-01"),
                             "2026-07-01", None, gap_history=CALM, demand_history=CALM)
    _c, high, _s = _raw_alert(_st(sdgi=9.60), _st(sdgi=9.10, as_of="2026-07-01"),
                              "2026-07-01", None, gap_history=CALM_HIGH,
                              demand_history=CALM_HIGH)
    assert "gap-moved-sharply" in low and "gap-moved-sharply" in high


def test_an_ordinary_sized_gap_move_stays_quiet():
    color, trig, _s = _raw_alert(_st(sdgi=0.20), _st(sdgi=0.10, as_of="2026-07-01"),
                                 "2026-07-01", None, gap_history=CALM, demand_history=CALM)
    assert color == "green" and trig == []


def test_gap_rule_silent_until_there_is_enough_history():
    """Fewer than four prior runs and the rule says nothing rather than guessing."""
    _c, trig, _s = _raw_alert(_st(sdgi=5.0), _st(sdgi=0.10, as_of="2026-07-01"),
                              "2026-07-01", None, gap_history=[0.0, 0.1, 0.0],
                              demand_history=[0.0, 0.1, 0.0])
    assert trig == []


def test_gap_rule_silent_when_the_series_has_never_moved():
    flat = [1.0] * 8
    _c, trig, _s = _raw_alert(_st(sdgi=1.0), _st(sdgi=1.0, as_of="2026-07-01"),
                              "2026-07-01", None, gap_history=flat, demand_history=flat)
    assert trig == []


def test_yellow_on_constraint_rotation():
    color, trig, _s = _raw_alert(_st(constraint="memory scarcity"),
                                 _st(constraint="export enforcement", as_of="2026-07-01"),
                                 "2026-07-01", None)
    assert color == "yellow" and "constraint-rotated" in trig


def test_yellow_on_high_call_moved():
    book = ThesisBook(categoryId="c", entries=[_entry(changed="2026-07-05")])
    color, trig, _s = _raw_alert(_st(), _st(as_of="2026-07-01"), "2026-07-01", book)
    assert color == "yellow" and "high-call-moved" in trig


def test_reaffirmed_high_call_in_window_stays_green():
    # USER-APPROVED 2026-07-12: "reaffirmed" re-stamps lastChangedAsOf without a real move,
    # so a timestamp-only predicate would fire every day under daily cadence.
    book = ThesisBook(categoryId="c", entries=[
        _entry(verdict="reaffirmed", direction=0, changed="2026-07-05")])
    color, trig = _raw_alert(_st(), _st(as_of="2026-07-01"), "2026-07-01", book)[:2]
    assert color == "green" and trig == []


def test_yellow_on_high_call_challenged():
    # USER-APPROVED 2026-07-12 (spec §4: "challenged" counts): an in-window pendingChallenge
    # on a high-conviction call is a "down" move -> high-call-moved fires.
    from gpu_agent.thesis import PendingChallenge
    e = _entry(verdict="reaffirmed", direction=0, changed="2026-06-20").model_copy(
        update={"pendingChallenge": PendingChallenge(verdict="weakened", asOf="2026-07-05",
                                                     rationale="r", findingIds=[])})
    book = ThesisBook(categoryId="c", entries=[e])
    color, trig, _s = _raw_alert(_st(), _st(as_of="2026-07-01"), "2026-07-01", book)
    assert color == "yellow" and "high-call-moved" in trig


def test_new_call_in_window_is_not_an_alert_trigger():
    # USER-APPROVED 2026-07-12: new-call surfacing is diff-only — a thesis created inside the
    # window (no verdict, no challenge) must not fire any ladder trigger.
    e = _entry(verdict=None, direction=0, changed="2026-07-05").model_copy(
        update={"createdAsOf": "2026-07-05"})
    book = ThesisBook(categoryId="c", entries=[e])
    color, trig, _s = _raw_alert(_st(), _st(as_of="2026-07-01"), "2026-07-01", book)
    assert color == "green" and trig == []


def test_two_yellow_rules_escalate_orange():
    color, trig, _s = _raw_alert(_st(sdgi=0.60, constraint="memory"),
                                 _st(sdgi=0.10, constraint="export", as_of="2026-07-01"),
                                 "2026-07-01", None, gap_history=CALM, demand_history=CALM)
    assert color == "orange"
    assert {"gap-moved-sharply", "constraint-rotated"} <= set(trig)


def test_orange_on_high_break():
    book = ThesisBook(categoryId="c", entries=[
        _entry(status="retired", verdict="broken", changed="2026-07-06")])
    color, trig, _s = _raw_alert(_st(), _st(as_of="2026-07-01"), "2026-07-01", book)
    assert color == "orange" and "high-call-broke" in trig


def test_orange_on_asymmetric_demand_reversal():
    """Demand falls further than it usually moves AND the gap falls with it. The gap's
    own fall is ordinary-sized here, so the gap rule stays quiet and demand-reversal
    escalates to orange on its own."""
    dem_hist = [4.0, 4.1, 4.0, 4.1, 4.0, 4.1, 4.0, 4.1]      # usual move ~0.10
    gap_hist = [4.0, 4.2, 4.0, 4.2, 4.0, 4.2, 4.0, 4.2]      # usual move ~0.20
    color, trig, sizes = _raw_alert(_st(demand=3.80, sdgi=4.10),
                                    _st(demand=4.10, sdgi=4.20, as_of="2026-07-01"),
                                    "2026-07-01", None,
                                    gap_history=gap_hist, demand_history=dem_hist)
    assert color == "orange" and trig == ["demand-reversal"]
    assert sizes["demand-reversal"].startswith("demand fell 0.30")


def test_demand_reversal_needs_the_gap_to_fall_too():
    dem_hist = [4.0, 4.1, 4.0, 4.1, 4.0, 4.1, 4.0, 4.1]
    gap_hist = [4.0, 4.2, 4.0, 4.2, 4.0, 4.2, 4.0, 4.2]
    color, trig, _s = _raw_alert(_st(demand=3.80, sdgi=4.25),   # gap ROSE
                                 _st(demand=4.10, sdgi=4.20, as_of="2026-07-01"),
                                 "2026-07-01", None,
                                 gap_history=gap_hist, demand_history=dem_hist)
    assert "demand-reversal" not in trig and color == "green"


def test_demand_rising_never_fires_the_reversal_rule():
    dem_hist = [4.0, 4.1, 4.0, 4.1, 4.0, 4.1, 4.0, 4.1]
    gap_hist = [4.0, 4.2, 4.0, 4.2, 4.0, 4.2, 4.0, 4.2]
    _c, trig, _s = _raw_alert(_st(demand=4.50, sdgi=4.10),
                              _st(demand=4.10, sdgi=4.20, as_of="2026-07-01"),
                              "2026-07-01", None,
                              gap_history=gap_hist, demand_history=dem_hist)
    assert "demand-reversal" not in trig


def test_red_on_break_plus_sharp_gap_move():
    book = ThesisBook(categoryId="c", entries=[
        _entry(status="retired", verdict="broken", changed="2026-07-06")])
    color, trig, _s = _raw_alert(_st(sdgi=-0.60), _st(sdgi=0.10, as_of="2026-07-01"),
                                 "2026-07-01", book, gap_history=CALM, demand_history=CALM)
    assert color == "red" and "gap-moved-sharply" in trig


def test_no_prior_run_is_green():
    color, trig, _s = _raw_alert(_st(), None, None, None)
    assert color == "green"


def test_fold_immediate_escalation_and_two_calm_step_down():
    assert _fold_displayed(["green", "orange"]) == ["green", "orange"]      # escalate now
    assert _fold_displayed(["orange", "green"]) == ["orange", "orange"]     # 1st calm holds
    assert _fold_displayed(["orange", "green", "green"]) == ["orange", "orange", "green"]
    assert _fold_displayed(["orange", "green", "yellow"]) == ["orange", "orange", "yellow"]
    assert _fold_displayed(["yellow", "red"]) == ["yellow", "red"]


def test_alert_state_walk_deterministic(tmp_path):
    def _write(as_of, constraint):
        cat = tmp_path / "chips.merchant-gpu"
        cat.mkdir(parents=True, exist_ok=True)
        sc = Scorecard(categoryId="chips.merchant-gpu", asOf=as_of, findings=[],
                       demandSupply=DemandSupply(dmiContribution=0.1, smiContribution=0.1),
                       narrative="n", confidence=_conf())
        (cat / f"{as_of}-v1.json").write_text(sc.model_dump_json(), "utf-8")
        return sc

    _write("2026-07-01", None)
    _write("2026-07-07", None)
    today = _write("2026-07-08", None)
    a = alert_state(tmp_path, today)
    b = alert_state(tmp_path, today)
    assert a == b
    assert a.color == "green" and a.priorColor == "green" and a.rawColor == "green"
    assert a.triggerSizes == {}
