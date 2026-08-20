# tests/test_report_change_first.py
from __future__ import annotations
from gpu_agent.report import render_report, render_change_lines
from gpu_agent.registry.indicators import IndicatorRegistry
from gpu_agent.schema.scorecard import (Scorecard, DemandSupply, DimensionRating,
                                        CategoryStatus)
from gpu_agent.schema.finding import Confidence
from gpu_agent.change import build_state, StateVector, ChangeReport, HorizonDiff, ItemDelta
from gpu_agent import reader


def _reg():
    return IndicatorRegistry.load("registry/indicators.json")


def _conf():
    return Confidence(level="medium", basis="b")


def _sc():
    return Scorecard(categoryId="chips.merchant-gpu", asOf="2026-07-08", findings=[],
                     dimensionRatings={"momentum": DimensionRating(
                         rating="Very strong", direction="improving", confidence=_conf(),
                         findingIds=[], rationale="r")},
                     demandSupply=DemandSupply(dmiContribution=0.57, smiContribution=0.29),
                     narrative="n", confidence=_conf(),
                     categoryStatus=CategoryStatus(rating="Strong", direction="improving",
                                                   bottleneck="packaging", reason="demand outruns ramp"))


def _change():
    return ChangeReport(asOf="2026-07-08", horizons=[
        HorizonDiff(horizon="yesterday", lookbackDays=1, priorAsOf="2026-07-07", items=[
            ItemDelta(key="dim:momentum", changed=True, today="Very strong/improving",
                      prior="Strong/steady", direction="up")]),
        HorizonDiff(horizon="last week", lookbackDays=7, priorAsOf="2026-07-01", items=[]),
        HorizonDiff(horizon="last month", lookbackDays=30, priorAsOf="2026-06-08", items=[])])


def test_change_none_is_unchanged_behavior():
    # A caller that passes no change report gets exactly today's report (no WHAT CHANGED lead).
    out = render_report(_sc(), None, _reg(), render_ts="fixed")
    assert "WHAT CHANGED" not in out
    assert "STATE OF THE MARKET" in out


def test_change_first_leads_with_what_changed_then_glance():
    st = build_state(_sc())
    out = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(), state=st)
    assert out.index("WHAT CHANGED") < out.index("QUICK GLANCE") < out.index(reader.APPENDIX_DIVIDER)
    # change-first lead sits above STATE OF THE MARKET
    assert out.index("WHAT CHANGED") < out.index("STATE OF THE MARKET")


def test_top_band_leads_when_alert_supplied():
    # AMENDED 2026-07-11: TOP BAND above WHAT CHANGED; absent without an AlertState.
    from gpu_agent.change import AlertState
    st = build_state(_sc())
    out = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(), state=st,
                        alert=AlertState(color="yellow", priorColor="green", rawColor="yellow"))
    assert out.index("YELLOW") < out.index("WHAT CHANGED")
    assert "(was GREEN)" in out
    no_alert = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(), state=st)
    assert "(was GREEN)" not in no_alert


def test_above_fold_passes_acronym_lint():
    st = build_state(_sc())
    out = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(), state=st)
    above = out.split(reader.APPENDIX_DIVIDER)[0]
    assert reader.lint_acronyms(above) == []


def test_above_fold_within_length_budget():
    st = build_state(_sc())
    out = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(), state=st)
    above = out.split(reader.APPENDIX_DIVIDER)[0]
    from gpu_agent.report import _ABOVE_FOLD_BUDGET
    assert len(above.splitlines()) <= _ABOVE_FOLD_BUDGET


def test_change_first_is_byte_deterministic():
    st = build_state(_sc())
    a = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(), state=st)
    b = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(), state=st)
    assert a == b


def test_change_first_appendix_has_full_the_calls_block():
    # USER-APPROVED ADDITION (2026-07-12, interactive): the ranked-calls fold line above
    # the fold promises "full detail in THE CALLS appendix" — that promise is only true
    # if the appendix actually carries a THE CALLS section. On the change-first path
    # only, render_the_calls (the un-capped, un-folded book) leads the appendix, right
    # after reader.APPENDIX_DIVIDER, so every folded entry's full three-line detail is
    # still reachable one section down.
    from gpu_agent.thesis import ThesisBook, ThesisEntry

    def _entry(eid, conviction, verdict="reaffirmed"):
        return ThesisEntry(id=eid, title=f"call {eid}", statement="s", lens="demand",
                            status="registered", conviction=conviction,
                            lastVerdict=verdict, lastDirection=0, streak=2,
                            mechanism="m", falsifiableTrigger="t", sensitivity="s",
                            createdAsOf="2026-06", lastChangedAsOf="2026-07-08",
                            lastJudgedAsOf="2026-07-08")

    # More standing calls than top_k (default 5) so the above-the-fold block folds the
    # tail; one entry's verdict differs from "reaffirmed" so brief.render_the_calls
    # renders every entry's full three-line detail rather than its own "nothing
    # changed" one-liner shortcut.
    book = ThesisBook(categoryId="chips.merchant-gpu", entries=[
        _entry("a", "high", verdict="strengthened"), _entry("b", "medium"),
        _entry("c", "low"), _entry("d", "medium"), _entry("e", "low"), _entry("f", "low")])
    st = build_state(_sc())
    out = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(), state=st,
                        thesis_book=book, top_k=5)

    above, appendix_part = out.split(reader.APPENDIX_DIVIDER, 1)
    assert "more calls folded" in above
    assert "full detail in THE CALLS appendix" in above

    # The appendix's FIRST section (right after the divider) is the full THE CALLS
    # block, and it carries every entry's full detail, not folded.
    assert appendix_part.strip().startswith("THE CALLS")
    for eid in ("a", "b", "c", "d", "e", "f"):
        assert f"call {eid}" in appendix_part
    assert appendix_part.count("breaks if:") == 6


# ── F119: second shrink lever — QUICK GLANCE Tier 2/3 fold ──────────────────

def _big_book(n=17):
    from gpu_agent.thesis import ThesisBook, ThesisEntry
    entries = [ThesisEntry(
        id=f"t{i}", title=f"call t{i}", statement="s", lens="demand",
        status="registered", conviction="medium",
        lastVerdict=("strengthened" if i == 0 else "reaffirmed"),
        lastDirection=0, streak=2, mechanism="m", falsifiableTrigger="trigger",
        sensitivity="s", createdAsOf="2026-06", lastChangedAsOf="2026-07-08",
        lastJudgedAsOf="2026-07-08") for i in range(n)]
    return ThesisBook(categoryId="chips.merchant-gpu", entries=entries)


def _wide_state():
    # A state vector wide enough (prices + scarcity + money rows) that the top half
    # still overshoots the 88-line budget after ranked calls bottom out at top_k == 1.
    from gpu_agent.change import PriceCell, MetricCell
    st = build_state(_sc())
    st.prices = [PriceCell(model=m, usdPerGpuHour=2.5, asOfColumn="2026-07-08")
                 for m in ("B200", "H100", "H200", "GB200")]
    st.metrics = {
        "leadTimes": MetricCell(indicatorId="leadTimes", statement="36 weeks",
                                tier="scarcity"),
        "S10": MetricCell(indicatorId="S10", statement="inventory lean",
                          tier="scarcity"),
        "vendorRevenueGuidance": MetricCell(indicatorId="vendorRevenueGuidance",
                                            value=45.0, unit="USD_B", tier="money"),
        "rpoBacklog": MetricCell(indicatorId="rpoBacklog", value=90.0, unit="USD_B",
                                 tier="money"),
        "grossMargin": MetricCell(indicatorId="grossMargin", value=71.0, unit="pct",
                                  tier="money"),
    }
    return st


def test_f119_fold_brings_overshooting_page_within_budget():
    from gpu_agent.report import _ABOVE_FOLD_BUDGET
    out = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(),
                        state=_wide_state(), thesis_book=_big_book())
    above, appendix_part = out.split(reader.APPENDIX_DIVIDER, 1)
    assert len(above.splitlines()) <= _ABOVE_FOLD_BUDGET
    # the fold marker sits above the fold; Tier 1 verdict rows never fold
    assert "full rows below the divider" in above
    assert "Momentum rating" in above
    # Tier 2/3 detail rows are gone from the top half...
    assert "B200 rental" not in above
    # ...but the full QUICK GLANCE rows are guaranteed in the appendix
    assert "QUICK GLANCE" in appendix_part
    assert "B200 rental" in appendix_part
    assert "Tier 3 — Money" in appendix_part
    # spec: the echoed full QUICK GLANCE sits right after the full THE CALLS block
    assert appendix_part.index("THE CALLS") < appendix_part.index("QUICK GLANCE")


def test_f119_fold_lines_pass_acronym_lint():
    out = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(),
                        state=_wide_state(), thesis_book=_big_book())
    assert reader.lint_acronyms(out.split(reader.APPENDIX_DIVIDER)[0]) == []


def test_f119_under_budget_page_never_folds():
    out = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(),
                        state=build_state(_sc()))
    assert "full rows below the divider" not in out
    # and the appendix carries no duplicated QUICK GLANCE when nothing folded
    assert out.split(reader.APPENDIX_DIVIDER)[1].count("QUICK GLANCE") == 0


# ── F120: assembled above-fold acronym lint blocks the render ────────────────

def _book_with_title(title):
    from gpu_agent.thesis import ThesisBook, ThesisEntry
    return ThesisBook(categoryId="chips.merchant-gpu", entries=[ThesisEntry(
        id="x1", title=title, statement="s", lens="demand", status="registered",
        conviction="high", lastVerdict="strengthened", lastDirection=0, streak=2,
        mechanism="m", falsifiableTrigger="trigger", sensitivity="s",
        createdAsOf="2026-06", lastChangedAsOf="2026-07-08",
        lastJudgedAsOf="2026-07-08")])


def test_f120_novel_acronym_in_live_title_blocks_render_legacy_path():
    import pytest
    book = _book_with_title("ZORPX9 accelerators reset the market")
    with pytest.raises(ValueError) as exc:
        render_report(_sc(), None, _reg(), render_ts="fixed", thesis_book=book)
    assert "ZORPX9" in str(exc.value)
    assert "registry/acronyms.json" in str(exc.value)


def test_f120_novel_acronym_blocks_change_first_path_too():
    import pytest
    book = _book_with_title("ZORPX9 accelerators reset the market")
    st = build_state(_sc())
    with pytest.raises(ValueError, match="ZORPX9"):
        render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(),
                      state=st, thesis_book=book)


def test_f120_stale_paren_id_stripped_from_breaks_if_legacy_path():
    # Round-2 remediation (user-approved 2026-08-20, Option A): the live book's
    # "breaks if" texts embed old-scheme ids as "Label (D1)" — not in today's
    # registry, so label substitution can't remove them. The display layer strips
    # the leftover parenthesized short-code; the stored book text is untouched.
    book = _book_with_title("Hyperscaler spending stays on plan")
    book.entries[0].falsifiableTrigger = (
        "A Hyperscaler capex-revision direction (D1) cuts 2027 guidance "
        "within 2 quarters.")
    out = render_report(_sc(), None, _reg(), render_ts="fixed", thesis_book=book)
    above = out.split(reader.APPENDIX_DIVIDER)[0]
    assert "(D1)" not in above
    assert "capex-revision direction cuts 2027 guidance" in above


def test_f120_stale_paren_id_stripped_from_ranked_calls_too():
    book = _book_with_title("Hyperscaler spending stays on plan")
    book.entries[0].falsifiableTrigger = (
        "Financing conditions (X5) stop appearing for 2 consecutive quarters.")
    st = build_state(_sc())
    out = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(),
                        state=st, thesis_book=book)
    above = out.split(reader.APPENDIX_DIVIDER)[0]
    assert "(X5)" not in above
    assert "Financing conditions stop appearing" in above


def test_f120_strip_is_narrow_legitimate_parens_survive():
    # The strip must not eat real parenthesized prose or product names — only the
    # old-scheme short-code pattern (one capital letter + 1-2 digits).
    from gpu_agent import brief
    book = _book_with_title("Wafer starts hold")
    book.entries[0].falsifiableTrigger = (
        "Cerebras stops reporting (CS-4) shipments (no growth in 2027) "
        "for 2 quarters.")
    calls = brief.render_the_calls(book, _sc(), None, registry=_reg())
    assert "(CS-4)" in calls
    assert "(no growth in 2027)" in calls


def test_f120_strip_stale_paren_ids_unit():
    assert (reader.strip_stale_paren_ids("Label (D1) moves (S10) fast")
            == "Label moves fast")
    assert (reader.strip_stale_paren_ids("keep (no growth in 2027) and (CS-4)")
            == "keep (no growth in 2027) and (CS-4)")
    assert reader.strip_stale_paren_ids("") == ""


def test_f120_strip_never_eats_allowlisted_tokens():
    # Review fix (2026-08-20): "(Q3)" matches the one-capital+digits shape but Q3 is
    # a sanctioned allowlisted token — deleting it would be silent content loss, the
    # opposite of the fail-loud posture. Allowlisted tokens must survive the strip.
    assert (reader.strip_stale_paren_ids("misses guidance (Q3) badly")
            == "misses guidance (Q3) badly")
    assert (reader.strip_stale_paren_ids("both (Q4) and (D1) appear")
            == "both (Q4) and appear")


def test_f119_both_levers_bottomed_still_over_ships_over_budget():
    # Spec-promised (user-accepted degradation mode): when even the QUICK GLANCE fold
    # cannot reach the 88-line budget, the render ships over budget — no exception,
    # no silent content loss beyond the two approved folds.
    from gpu_agent.report import _ABOVE_FOLD_BUDGET
    out = render_report(_sc(), None, _reg(), render_ts="fixed", change=_change(),
                        state=_wide_state(), thesis_book=_big_book(120))
    above = out.split(reader.APPENDIX_DIVIDER)[0]
    assert len(above.splitlines()) > _ABOVE_FOLD_BUDGET   # honest: still over
    assert "full rows below the divider" in above          # both levers did fire


def test_f120_allowlisted_tokens_still_render():
    # DAILY/monthly clean renders keep working — the whole existing suite is the
    # broad green check; this is the targeted one.
    book = _book_with_title("HBM supply stays tight into 2027")
    out = render_report(_sc(), None, _reg(), render_ts="fixed", thesis_book=book)
    assert "HBM supply stays tight" in out
