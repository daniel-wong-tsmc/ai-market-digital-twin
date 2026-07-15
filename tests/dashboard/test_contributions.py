from pathlib import Path

from gpu_agent.config import REGISTRY_PATH
from gpu_agent.dashboard.contributions import contribution_rows
from gpu_agent.registry.indicators import IndicatorRegistry
from gpu_agent.report import load_scorecard
from gpu_agent.scoring import dmi_smi_contribution

FIX = Path("tests/dashboard/fixtures")
CAT = "chips.merchant-gpu"


def _sc():
    return load_scorecard(FIX / "2026-07-06-v1.json")


def _reg():
    return IndicatorRegistry.load(REGISTRY_PATH)


def test_row_sums_match_frozen_scoring_exactly():
    sc, reg = _sc(), _reg()
    rows = contribution_rows(sc.findings, reg, CAT)
    dmi, smi = dmi_smi_contribution(sc.findings, reg, CAT)
    assert abs(sum(r["demand_contribution"] for r in rows) - dmi) < 1e-12
    assert abs(sum(r["supply_contribution"] for r in rows) - smi) < 1e-12


def test_rows_have_the_drilldown_fields_and_are_sorted():
    rows = contribution_rows(_sc().findings, _reg(), CAT)
    assert rows, "fixture scorecard must produce scoring rows"
    for r in rows:
        for k in ("entity", "indicator_id", "label", "weight", "magnitude",
                  "polarity_demand", "polarity_supply", "demand_contribution",
                  "supply_contribution", "finding_id", "statement", "observed_at",
                  "evidence"):
            assert k in r
        for ev in r["evidence"]:
            assert set(ev) == {"source", "url", "date", "tier"}
    totals = [abs(r["demand_contribution"]) + abs(r["supply_contribution"]) for r in rows]
    assert totals == sorted(totals, reverse=True)


def test_deterministic_across_two_calls():
    sc, reg = _sc(), _reg()
    assert contribution_rows(sc.findings, reg, CAT) == contribution_rows(sc.findings, reg, CAT)


def test_weight_overrides_mirror_scoring_and_actually_move_the_sums():
    # F95 item 2: production scoring (pipeline.py) passes assignment.weights into
    # dmi_smi_contribution as a per-indicator override. This must stay live in the
    # mirror, not just plumbed-through-but-unused, so pin both parity AND movement.
    sc, reg = _sc(), _reg()
    ind_id = next(r["indicator_id"] for r in contribution_rows(sc.findings, reg, CAT))
    overrides = {ind_id: 0.9}   # far from the registry default -> sums must move

    rows_plain = contribution_rows(sc.findings, reg, CAT)
    rows_overridden = contribution_rows(sc.findings, reg, CAT, weight_overrides=overrides)

    dmi, smi = dmi_smi_contribution(sc.findings, reg, CAT, weight_overrides=overrides)
    assert abs(sum(r["demand_contribution"] for r in rows_overridden) - dmi) < 1e-12
    assert abs(sum(r["supply_contribution"] for r in rows_overridden) - smi) < 1e-12

    sum_plain = sum(r["demand_contribution"] for r in rows_plain) + \
        sum(r["supply_contribution"] for r in rows_plain)
    sum_overridden = sum(r["demand_contribution"] for r in rows_overridden) + \
        sum(r["supply_contribution"] for r in rows_overridden)
    assert sum_plain != sum_overridden
