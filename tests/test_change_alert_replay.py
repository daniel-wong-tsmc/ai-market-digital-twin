# tests/test_change_alert_replay.py
"""F137 — the two repaired alert rules replayed over the real stored history.

The user chose both rule shapes off this replay (USER-DECIDED 2026-09-01), so the
replay is pinned here as the regression fixture. It reads the committed scorecards in
`store/chips.merchant-gpu`, walks them in run order, and asserts exactly which runs
each rule fires on.

The walk stops at 2026-08-v17 — the newest run at the time F137 was built — so future
cycles appending to the store cannot silently move these expectations.
"""
from __future__ import annotations
from pathlib import Path

import pytest

from gpu_agent.asof import period_end
from gpu_agent.change import build_state, usual_swing, _raw_alert, StateVector
from gpu_agent.report import _VERSION_RE, load_scorecard

STORE = Path(__file__).resolve().parents[1] / "store" / "chips.merchant-gpu"
LAST_RUN = ("2026-08", 17)   # the newest run this replay covers


def _series():
    """(name, StateVector) for every stored scorecard up to LAST_RUN, in run order."""
    rows = []
    for p in STORE.glob("*.json"):
        m = _VERSION_RE.match(p.name)
        if not m:
            continue
        as_of, ver = m.group(1), int(m.group(2))
        if (period_end(as_of), ver) > (period_end(LAST_RUN[0]), LAST_RUN[1]):
            continue
        rows.append((period_end(as_of), ver, p))
    rows.sort(key=lambda t: (t[0], t[1]))
    return [(p.name, build_state(load_scorecard(p))) for _pe, _v, p in rows]


@pytest.fixture(scope="module")
def series():
    return _series()


def _fired(series, rule):
    """Which runs `rule` fires on, comparing each run with the one before it."""
    gaps = [st.sdgi for _n, st in series]
    dems = [st.demand for _n, st in series]
    out = []
    for i in range(1, len(series)):
        name, st = series[i]
        prior = StateVector(asOf="prior", demand=dems[i - 1], sdgi=gaps[i - 1])
        _c, trig, _s = _raw_alert(st, prior, None, None,
                                  gap_history=gaps[:i], demand_history=dems[:i])
        if rule in trig:
            out.append(name)
    return out


def test_the_store_still_holds_the_history_the_rules_were_chosen_on(series):
    assert len(series) == 54
    assert series[-1][0] == "2026-08-v17.json"


def test_gap_moved_sharply_fires_on_the_eight_runs_the_user_signed_off(series):
    assert _fired(series, "gap-moved-sharply") == [
        "2026-06-v7.json", "2026-07-02-v1.json", "2026-07-v1.json", "2026-07-v12.json",
        "2026-07-v14.json", "2026-07-v15.json", "2026-08-v7.json", "2026-08-v17.json"]


def test_demand_reversal_fires_on_the_four_runs_the_user_signed_off(series):
    assert _fired(series, "demand-reversal") == [
        "2026-06-v5.json", "2026-06-v7.json", "2026-07-02-v1.json", "2026-08-v13.json"]


def test_the_sharpest_recorded_reversal_now_goes_orange(series):
    """2026-08-v13: demand fell 0.573 while the gap fell 0.493 — the shape the rule was
    written to catch. Under the old band test this run was green."""
    names = [n for n, _ in series]
    i = names.index("2026-08-v13.json")
    gaps = [st.sdgi for _n, st in series]
    dems = [st.demand for _n, st in series]
    prior = StateVector(asOf="prior", demand=dems[i - 1], sdgi=gaps[i - 1])
    color, trig, sizes = _raw_alert(series[i][1], prior, None, None,
                                    gap_history=gaps[:i], demand_history=dems[:i])
    assert color == "orange" and "demand-reversal" in trig
    assert sizes["demand-reversal"].startswith("demand fell 0.57")


def test_the_biggest_recorded_gap_jump_now_fires(series):
    """2026-07-v1: the gap rose 1.02, the largest move on record. Old rule: silent."""
    names = [n for n, _ in series]
    i = names.index("2026-07-v1.json")
    gaps = [st.sdgi for _n, st in series]
    dems = [st.demand for _n, st in series]
    prior = StateVector(asOf="prior", demand=dems[i - 1], sdgi=gaps[i - 1])
    _c, trig, sizes = _raw_alert(series[i][1], prior, None, None,
                                 gap_history=gaps[:i], demand_history=dems[:i])
    assert "gap-moved-sharply" in trig
    assert sizes["gap-moved-sharply"].startswith("1.02")


def test_firing_rates_stay_in_the_band_the_user_approved(series):
    """Roughly one gap nudge every seven runs, and an orange demand reversal about
    once every thirteen — the rates the options table quoted."""
    n = len(series) - 1
    assert len(_fired(series, "gap-moved-sharply")) / n == pytest.approx(0.15, abs=0.03)
    assert len(_fired(series, "demand-reversal")) / n == pytest.approx(0.075, abs=0.03)


def test_usual_swing_reads_the_last_ten_runs_only():
    """A long-dead calm stretch must not blunt the rule once the series wakes up."""
    calm_then_choppy = [0.0] * 20 + [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0]
    assert usual_swing(calm_then_choppy) == pytest.approx(1.0, abs=0.01)


def test_usual_swing_is_none_without_enough_history():
    assert usual_swing([]) is None
    assert usual_swing([1.0, 2.0, 3.0]) is None
    assert usual_swing([1.0, 1.0, 1.0, 1.0]) is None      # never moved
    assert usual_swing([1.0, 2.0, 1.0, 2.0]) is not None
