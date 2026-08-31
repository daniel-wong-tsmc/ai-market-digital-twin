"""F136 — the headline demand line must show the day-over-day change, at any scale.

The old word-band line (gpu_agent.bands.band_with_prior) was built for values in
roughly -1..+1 with its top band starting at 0.30. The demand number is now ~4.5, so
the line printed "ACCELERATING = (was ACCELERATING)" forever, however far the number
moved. These tests pin the replacement: a plain-words change line that carries
information at any scale, plus a deterministic coverage-vs-re-rating split so the
brief can say honestly when a move is mostly newly tracked companies.

Real data: store/chips.merchant-gpu/2026-08-v16.json -> ...v17.json, demand 3.940 ->
4.507 (+0.567), of which +0.520 is pairs never tracked before and +0.047 is a
re-rating of something already tracked (verified against the DMI v17 audit).
"""
from __future__ import annotations

import json

from gpu_agent import bands, coverage
from gpu_agent.registry.indicators import IndicatorRegistry
from gpu_agent.schema.scorecard import Scorecard

V16_DEMAND = 3.9400000000000013
V17_DEMAND = 4.506666666666668


def _load(path: str) -> Scorecard:
    with open(path, encoding="utf-8") as fh:
        return Scorecard.model_validate(json.load(fh))


def _registry() -> IndicatorRegistry:
    return IndicatorRegistry.load("registry/indicators.json")


# ── the saturation this lane exists to fix ────────────────────────────────────

def test_old_word_band_is_blind_to_the_real_v16_to_v17_move():
    """Documents the defect: a +0.567 move renders as no change at all."""
    assert bands.band_with_prior(V17_DEMAND, V16_DEMAND) == (
        "ACCELERATING = (was ACCELERATING)")


def test_change_line_shows_the_real_v16_to_v17_move():
    line = bands.change_line(V17_DEMAND, V16_DEMAND)
    assert line == "4.51, up 0.57 since the last run"


def test_change_line_never_saturates_at_any_scale():
    """The same move reads the same whether the level is 0.5, 4.5 or 450."""
    for base in (0.0, 4.0, 450.0, -900.0):
        assert bands.change_line(base + 0.57, base) == (
            f"{base + 0.57:.2f}, up 0.57 since the last run")


def test_change_line_down_move():
    assert bands.change_line(3.94, 4.5067) == "3.94, down 0.57 since the last run"


def test_change_line_unchanged():
    assert bands.change_line(4.5067, 4.5067) == "4.51, unchanged since the last run"


def test_change_line_move_below_display_precision_reads_unchanged():
    assert bands.change_line(4.5067, 4.5047) == "4.51, unchanged since the last run"


def test_change_line_never_prints_a_minus_sign_in_front_of_zero():
    assert bands.change_line(-0.001, -0.001) == "0.00, unchanged since the last run"
    assert bands.change_line(-0.001, 0.5) == "0.00, down 0.50 since the last run"


def test_change_line_no_prior():
    assert bands.change_line(4.5067, None) == "4.51, first tracked run — nothing to compare yet"


def test_change_line_carries_no_off_allowlist_acronym():
    from gpu_agent import reader
    assert reader.lint_acronyms(bands.change_line(4.5067, 3.94)) == []


# ── the deterministic coverage split ──────────────────────────────────────────

def test_coverage_split_reproduces_the_audit_on_real_v16_v17():
    cur = _load("store/chips.merchant-gpu/2026-08-v17.json")
    prior = _load("store/chips.merchant-gpu/2026-08-v16.json")
    split = coverage.demand_split(cur, prior, _registry())
    assert round(split.total, 3) == 0.567
    assert round(split.new_coverage, 3) == 0.520
    assert round(split.rerating, 3) == 0.047
    # exhaustive by construction, to the tolerance demand_split's own guard enforces
    assert abs((split.new_coverage + split.rerating) - split.total) < 1e-6
    assert split.coverage_dominates is True


def test_coverage_split_matches_the_stored_headline_delta():
    """The split must describe the SAME move the headline shows, not a recomputed one."""
    cur = _load("store/chips.merchant-gpu/2026-08-v17.json")
    prior = _load("store/chips.merchant-gpu/2026-08-v16.json")
    split = coverage.demand_split(cur, prior, _registry())
    stored = cur.demandSupply.dmiContribution - prior.demandSupply.dmiContribution
    assert split.total == stored


def test_coverage_split_stays_silent_when_it_cannot_reconcile_the_stored_delta():
    """If the stored demand number disagrees with the findings (e.g. per-category weight
    overrides the renderer cannot see), attribute nothing rather than guess."""
    cur = _load("store/chips.merchant-gpu/2026-08-v17.json")
    prior = _load("store/chips.merchant-gpu/2026-08-v16.json")
    tampered = prior.model_copy(deep=True)
    tampered.demandSupply.dmiContribution = prior.demandSupply.dmiContribution + 1.0
    assert coverage.demand_split(cur, tampered, _registry()) is None


def test_coverage_split_is_none_without_a_prior():
    cur = _load("store/chips.merchant-gpu/2026-08-v17.json")
    assert coverage.demand_split(cur, None, _registry()) is None


def test_coverage_split_of_a_scorecard_against_itself_is_all_zero():
    cur = _load("store/chips.merchant-gpu/2026-08-v17.json")
    split = coverage.demand_split(cur, cur, _registry())
    assert round(split.total, 9) == 0.0
    assert round(split.new_coverage, 9) == 0.0
    assert round(split.rerating, 9) == 0.0
    assert split.coverage_dominates is False


def test_qualifier_line_on_real_data_is_plain_and_names_the_split():
    from gpu_agent import reader
    cur = _load("store/chips.merchant-gpu/2026-08-v17.json")
    prior = _load("store/chips.merchant-gpu/2026-08-v16.json")
    line = coverage.qualifier_line(coverage.demand_split(cur, prior, _registry()))
    assert line is not None
    assert "+0.52" in line and "+0.05" in line
    assert "started tracking only now" in line
    assert reader.lint_acronyms(line) == []
    assert len(line.splitlines()) == 1


def test_no_qualifier_when_coverage_does_not_dominate():
    cur = _load("store/chips.merchant-gpu/2026-08-v17.json")
    assert coverage.qualifier_line(coverage.demand_split(cur, cur, _registry())) is None
    assert coverage.qualifier_line(None) is None


# ── the qualifier must never say something false ──────────────────────────────

def test_no_qualifier_when_the_two_parts_pull_opposite_ways():
    """Real precedent, v11 -> v12: total +0.033 from +0.140 coverage and -0.107
    re-rating. Calling +0.14 "most of" a +0.03 move is false, so say nothing."""
    split = coverage.DemandSplit(total=0.033, new_coverage=0.140, rerating=-0.107)
    assert split.coverage_dominates is False
    assert coverage.qualifier_line(split) is None


def test_no_qualifier_when_coverage_pulls_against_the_move():
    split = coverage.DemandSplit(total=-0.20, new_coverage=0.10, rerating=-0.30)
    assert split.coverage_dominates is False


def test_no_qualifier_when_the_coverage_part_is_below_display_precision():
    """Otherwise the sentence would quote 0.00 as its own evidence."""
    split = coverage.DemandSplit(total=0.006, new_coverage=0.004, rerating=0.002)
    assert split.coverage_dominates is False


def test_narrowing_coverage_is_not_described_as_newly_tracked():
    """A fall driven by pairs we STOPPED covering must not read as companies added."""
    split = coverage.DemandSplit(total=-0.20, new_coverage=-0.15, rerating=-0.05)
    line = coverage.qualifier_line(split)
    assert line is not None
    assert "stopped tracking" in line
    assert "started tracking" not in line
    assert "-0.15" in line and "-0.05" in line


def test_qualifier_never_prints_a_minus_sign_in_front_of_zero():
    # The gating above already makes a tiny opposite-signed part unreachable through
    # qualifier_line — belt and braces, the formatter itself refuses to print "-0.00".
    assert coverage._signed(-0.0004) == "+0.00"
    assert coverage._signed(-0.15) == "-0.15"
    assert coverage._signed(0.52) == "+0.52"
    assert coverage.qualifier_line(
        coverage.DemandSplit(total=0.011, new_coverage=0.011, rerating=-0.0004)) is None


# ── the split must never be the reason a brief fails to render ────────────────

def test_split_returns_none_when_a_prior_finding_no_longer_resolves():
    """Scoring the PRIOR scorecard's findings is new exposure: an indicator retired from
    the registry since that run makes registry.resolve raise. The qualifier is a nicety —
    it must degrade to silence, never take the whole report down with it."""
    class _Exploding:
        def resolve(self, *a, **kw):
            raise RuntimeError("indicator retired from the registry")

    cur = _load("store/chips.merchant-gpu/2026-08-v17.json")
    prior = _load("store/chips.merchant-gpu/2026-08-v16.json")
    assert coverage.demand_split(cur, prior, _Exploding()) is None


# ── the rendered surfaces ─────────────────────────────────────────────────────

def test_state_of_market_leads_with_the_change_not_the_saturated_band():
    from gpu_agent import brief
    cur = _load("store/chips.merchant-gpu/2026-08-v17.json")
    prior = _load("store/chips.merchant-gpu/2026-08-v16.json")
    out = brief.render_state_of_market(cur, prior)
    demand_line = next(ln for ln in out.splitlines() if "Demand: " in ln)
    assert "up 0.57 since the last run" in demand_line
    assert "ACCELERATING" not in demand_line


def test_state_of_market_carries_the_coverage_qualifier_when_registry_is_supplied():
    from gpu_agent import brief
    cur = _load("store/chips.merchant-gpu/2026-08-v17.json")
    prior = _load("store/chips.merchant-gpu/2026-08-v16.json")
    marker = "not readings we already followed changing"
    out = brief.render_state_of_market(cur, prior, registry=_registry())
    assert marker in out
    without = brief.render_state_of_market(cur, prior)
    assert marker not in without
    # exactly one qualifier line, and it sits directly under the Demand line it qualifies
    lines = out.splitlines()
    assert sum(1 for ln in lines if marker in ln) == 1
    i_demand = next(i for i, ln in enumerate(lines) if "Demand: " in ln)
    assert marker in lines[i_demand + 1]
