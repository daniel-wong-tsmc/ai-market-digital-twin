"""gpu_agent/coverage.py — F136: how much of a demand move is just wider coverage.

Pure, deterministic, report-side only. NOTHING here changes how the demand number is
computed: the split is derived by re-running the frozen scoring function
(gpu_agent.scoring.dmi_smi_contribution) over disjoint slices of each scorecard's
findings, so the arithmetic is the frozen arithmetic, byte for byte.

Why this exists. The demand number is a running TOTAL over (company, indicator) pairs,
not an average, so it grows whenever the agent starts covering a company or an
indicator it never tracked before. A reader who sees "up 0.57 since the last run"
deserves to know when most of that is new coverage rather than the market re-rating.
(Whether the number *should* be a total or an average is a separate, frozen-scoring
question — see F79, the v2 scoring path. This module only reports.)

The derivation, in plain terms:

  * Group every finding in each scorecard by the pair (company, indicator) — the exact
    same grouping key the frozen scoring code uses.
  * Pairs present now but not in the prior scorecard are NEW COVERAGE; their whole
    contribution counts as coverage growth.
  * Pairs present then but not now are ALSO coverage (coverage narrowing); their prior
    contribution counts against it.
  * Pairs present in both are RE-RATING: the change in their contribution is a genuine
    "something we already tracked moved".

Those three slices are disjoint and exhaustive, so new_coverage + rerating is exactly
the total move. Verified against the 2026-08 v16 -> v17 cycle: total +0.567 = +0.520
new coverage + +0.047 re-rating, matching the read-only audit item by item.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from gpu_agent import scoring

# A move smaller than this rounds to 0.00 at the two-decimal display precision the
# headline uses, so there is nothing worth qualifying. Display precision, not a tuned
# threshold — it follows the format string, and needs no retuning at any scale.
_DISPLAY_EPSILON = 0.005


@dataclass(frozen=True)
class DemandSplit:
    """How a demand move divides between wider coverage and genuine re-rating."""

    total: float
    new_coverage: float
    rerating: float

    @property
    def coverage_dominates(self) -> bool:
        """True only when "most of this move is coverage" is literally true.

        Four conditions, and the last two matter more than they look:

        * the move is big enough to show at two decimals at all;
        * the coverage part is big enough to show at two decimals (otherwise the
          sentence would quote 0.00 as its own evidence);
        * the coverage part pulls the SAME way as the move, and so does the re-rating
          part — if the two parts pull opposite ways, the coverage part is larger than
          the whole move and calling it "most of" the move is simply false. Real
          precedent in the store (v11 -> v12): total +0.033 = +0.140 coverage plus
          -0.107 re-rating, where the "most of a +0.03 move" part was +0.14;
        * the coverage part outweighs the re-rating part.
        """
        if abs(self.total) < _DISPLAY_EPSILON or abs(self.new_coverage) < _DISPLAY_EPSILON:
            return False
        if self.new_coverage * self.total <= 0:          # coverage pulls against the move
            return False
        if self.new_coverage * self.rerating < 0:        # the two parts pull apart
            return False
        return abs(self.new_coverage) > abs(self.rerating)


def _signed(value: float) -> str:
    """Two decimals with an explicit sign, and never the '-0.00' / '+0.00' pair that a
    value below display precision would otherwise print (mirrors bands._two_dp)."""
    text = f"{value:+.2f}"
    return "+0.00" if text == "-0.00" else text


def _key(finding) -> tuple[str, str]:
    """The frozen scoring code's grouping key: one contribution per (company, indicator)."""
    return (finding.entity, finding.indicatorId)


def _demand(findings, registry, category_id: str) -> float:
    """The frozen demand contribution of exactly these findings, nothing duplicated."""
    return scoring.dmi_smi_contribution(list(findings), registry, category_id)[0]


def demand_split(sc, prior, registry) -> Optional[DemandSplit]:
    """Split the demand move from ``prior`` to ``sc``. None when there is no prior.

    ``sc`` / ``prior`` are Scorecards; ``registry`` an IndicatorRegistry. Deterministic
    and side-effect free — it only reads the two scorecards already on disk.
    """
    if prior is None or registry is None:
        return None
    category_id = sc.categoryId
    cur_keys = {_key(f) for f in sc.findings}
    prior_keys = {_key(f) for f in prior.findings}
    fresh = cur_keys - prior_keys
    dropped = prior_keys - cur_keys
    shared = cur_keys & prior_keys

    try:
        gained = _demand([f for f in sc.findings if _key(f) in fresh], registry, category_id)
        lost = _demand([f for f in prior.findings if _key(f) in dropped], registry, category_id)
        shared_now = _demand([f for f in sc.findings if _key(f) in shared], registry, category_id)
        shared_then = _demand([f for f in prior.findings if _key(f) in shared], registry, category_id)
    except Exception:   # noqa: BLE001 — see below; the whole point is to never raise
        # Scoring the PRIOR scorecard's findings is new exposure: nothing else in the
        # renderer re-resolves them, and an indicator retired from the registry since
        # that run makes registry.resolve raise. This qualifier is a nicety; it must
        # never be the reason a whole brief fails to render. Same rule as the guard
        # below — say nothing rather than guess.
        return None

    new_coverage = gained - lost
    rerating = shared_now - shared_then

    # Honesty guard. The split is recomputed from the findings, while the headline number
    # is the value each scorecard STORED. Those agree today, but the scoring function also
    # accepts per-category weight overrides (an assignment's `weights`) that the renderer
    # cannot see. If the two ever disagree, the attribution would be describing a move the
    # reader is not being shown — so say nothing rather than guess.
    stored_total = sc.demandSupply.dmiContribution - prior.demandSupply.dmiContribution
    if abs((new_coverage + rerating) - stored_total) > 1e-6:
        return None
    return DemandSplit(total=stored_total,
                       new_coverage=new_coverage,
                       rerating=rerating)


def qualifier_line(split: Optional[DemandSplit]) -> Optional[str]:
    """One honest plain-words line when coverage growth drives the move — else None.

    Reader-facing prose: no acronyms, no ids, no jargon.
    """
    if split is None or not split.coverage_dominates:
        return None
    # Coverage moves BOTH ways. A cycle that stops covering more pairs than it starts
    # covering has a negative coverage part, and calling that "newly tracked" would tell
    # the reader a fall was caused by companies being ADDED. Two branches, one true each.
    what = ("companies and measures we started tracking only now"
            if split.new_coverage > 0 else
            "companies and measures we stopped tracking")
    # Signed parts, not a share of the total: coverage_dominates has already established
    # that both parts pull the same way as the move, so these two numbers add up to the
    # total the Demand line directly above states.
    return (f"Most of that demand move is {what} ({_signed(split.new_coverage)}), not "
            f"readings we already followed changing ({_signed(split.rerating)}).")
