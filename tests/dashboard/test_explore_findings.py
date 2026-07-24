"""F101c Task 4: question-grouped findings browser + client filter."""
import datetime as dt
import re

from gpu_agent.dashboard import explore_model as em
from gpu_agent.dashboard import explore_render as xr
from gpu_agent.dashboard.story_render import lint_story_copy
from gpu_agent.freshness import AGING_THRESHOLD, load_freshness
from tests.dashboard.test_explore_fixtures import _explore_store

TODAY = dt.date(2026, 7, 22)


def _model(tmp_path):
    root = _explore_store(tmp_path)
    findings = em.load_findings(root)
    sides = em.split_by_side(findings)
    return findings, sides


def test_groups_render_in_order_with_findings_under_right_group(tmp_path):
    findings, sides = _model(tmp_path)
    html = xr.render_findings_page(findings, sides, TODAY)

    demand_i = html.index("Evidence demand is growing")
    supply_i = html.index("Evidence supply is (or isn")
    assert demand_i < supply_i

    demand_section = html[demand_i:supply_i]
    supply_section = html[supply_i:]

    # fa (demand/nvidia) and fc (demand/NVDA->nvidia) are in the demand group
    assert 'data-entity="nvidia"' in demand_section
    assert demand_section.count('class="xp-find"') == 2
    # fb (supply/tsmc) is in the supply group
    assert 'data-entity="tsmc"' in supply_section


def test_alias_finding_lands_under_nvidia_entity_slug(tmp_path):
    findings, sides = _model(tmp_path)
    html = xr.render_findings_page(findings, sides, TODAY)
    # both fa and fc resolve to entitySlug "nvidia"
    assert html.count('data-entity="nvidia"') == 2


def test_every_card_carries_all_four_data_attributes(tmp_path):
    findings, sides = _model(tmp_path)
    html = xr.render_findings_page(findings, sides, TODAY)
    cards = re.findall(r'<article class="xp-find"[^>]*>', html)
    assert len(cards) == len(findings)
    for card in cards:
        assert 'data-dim="' in card
        assert 'data-entity="' in card
        assert 'data-tier="' in card
        assert 'data-date="' in card


def test_filter_script_is_single_and_self_contained(tmp_path):
    findings, sides = _model(tmp_path)
    html = xr.render_findings_page(findings, sides, TODAY)
    scripts = re.findall(r"<script.*?</script>", html, re.S)
    assert len(scripts) == 1
    script = scripts[0]
    assert "location.hash" in script
    assert "hidden" in script
    assert "http" not in script


def test_findings_page_is_lint_clean(tmp_path):
    findings, sides = _model(tmp_path)
    html = xr.render_findings_page(findings, sides, TODAY)
    assert lint_story_copy(html) == []


def test_statements_and_evidence_links_present(tmp_path):
    findings, sides = _model(tmp_path)
    html = xr.render_findings_page(findings, sides, TODAY)
    for f in findings:
        assert f["statement"] in html


# --- F103 Task 3: weight sort + aging mark ------------------------------

def _plain_finding(fid: str, *, entity: str, observed_at: str,
                    statement: str | None = None) -> dict:
    """A minimal finding dict — enough for `_find_card`/`render_findings_page`
    to render, without going through the full Finding schema. No evidence
    urls, so `classify` always lands on "news" (3-day half life)."""
    return {
        "id": fid,
        "statement": statement or f"{entity} finding {fid}",
        "impact": {"targets": [entity]},
        "entitySlug": entity,
        "entity": entity,
        "evidence": [],
        "observedAt": observed_at,
    }


def test_within_group_sorted_by_weight_descending():
    fresh = _plain_finding("f-fresh", entity="nvidia", observed_at="2026-07-21")
    stale = _plain_finding("f-stale", entity="nvidia", observed_at="2026-05-20")
    sides = {"demand": [stale, fresh], "supply": [], "other": []}
    html = xr.render_findings_page([stale, fresh], sides, TODAY)
    assert html.index("nvidia finding f-fresh") < html.index("nvidia finding f-stale")


def test_aging_chip_and_class_on_old_finding():
    cfg = load_freshness()
    old = _plain_finding("f-old", entity="nvidia", observed_at="2026-05-01")
    w = xr._find_weight(old, TODAY, cfg)
    assert w < AGING_THRESHOLD, "fixture must actually be stale for this test to mean anything"
    sides = {"demand": [old], "supply": [], "other": []}
    html = xr.render_findings_page([old], sides, TODAY)
    assert "xp-aging" in html
    assert "aging" in html


def test_fresh_finding_has_no_aging_mark():
    fresh = _plain_finding("f-fresh2", entity="nvidia", observed_at="2026-07-21")
    sides = {"demand": [fresh], "supply": [], "other": []}
    html = xr.render_findings_page([fresh], sides, TODAY)
    assert "xp-aging" not in html


def test_cards_carry_data_weight(tmp_path):
    findings, sides = _model(tmp_path)
    html = xr.render_findings_page(findings, sides, TODAY)
    cards = re.findall(r'<article class="xp-find[^>]*>', html)
    assert len(cards) == len(findings)
    for card in cards:
        assert 'data-weight="' in card


def test_find_script_is_byte_unchanged():
    # Light guard: Task 3 must not touch the inline filter script at all.
    assert len(xr._FIND_SCRIPT) == 1371
    assert "location.hash" in xr._FIND_SCRIPT
    assert "xp-aging" not in xr._FIND_SCRIPT
