"""F101c Task 5: series page + entity dossier pages + entities index."""
import datetime as dt

from gpu_agent.dashboard import explore_model as em
from gpu_agent.dashboard import explore_render as xr
from gpu_agent.dashboard.story_render import lint_story_copy
from tests.dashboard.test_explore_fixtures import _explore_store

TODAY = dt.date(2026, 7, 22)


def _row(value, *, unit="$/hr", title="Cloud Price Tracker",
         url="https://example.com/a", date="2026-07-20"):
    return {"value": value, "unit": unit,
            "source": {"title": title, "url": url}, "publishedAt": date}


def _series():
    # gpuRentalOnDemand has real rows; every other indicator in
    # series_groups() is intentionally left empty so the "no data yet"
    # path is exercised for the whole rest of the page.
    return {
        "gpuRentalOnDemand": [
            _row(3.10, date="2026-07-10"),
            _row(2.95, date="2026-07-20"),
        ],
    }


def test_series_page_group_headings_render_in_order():
    html = xr.render_series_page(_series(), TODAY)
    groups = em.series_groups()
    positions = [html.index(g["label"]) for g in groups]
    assert positions == sorted(positions)


def test_series_page_has_kpi_anchor_id():
    html = xr.render_series_page(_series(), TODAY)
    assert 'id="s-gpuRentalOnDemand"' in html


def test_series_page_has_meaning_lines():
    html = xr.render_series_page(_series(), TODAY)
    for meaning in em.SERIES_MEANING.values():
        assert meaning in html


def test_series_page_has_source_table_row():
    html = xr.render_series_page(_series(), TODAY)
    assert "Cloud Price Tracker" in html
    assert "2026-07-20" in html


def test_series_page_empty_series_renders_no_data_yet_without_crash():
    html = xr.render_series_page({}, TODAY)
    assert "no data yet" in html.lower()


def test_series_page_is_lint_clean():
    html = xr.render_series_page(_series(), TODAY)
    assert lint_story_copy(html) == []


def test_entity_page_role_line_and_markdown_and_finding_card(tmp_path):
    root = _explore_store(tmp_path)
    findings = em.load_findings(root)
    roles = em.entity_roles(findings)
    entities = {e["slug"]: e for e in em.load_entities(root)}
    tsmc = entities["tsmc"]
    role = roles["tsmc"]
    assert role == "where the supply bottleneck lives"

    html = xr.render_entity_page(tsmc, role, findings, {}, TODAY)
    assert "where the supply bottleneck lives" in html
    assert "<h2>" in html  # from markdown_to_html(body_md)
    # the tsmc finding (fb) card must be present
    tsmc_finding = next(f for f in findings if f["entitySlug"] == "tsmc")
    assert tsmc_finding["statement"] in html
    assert "<script" not in html


def test_entity_page_is_lint_clean(tmp_path):
    root = _explore_store(tmp_path)
    findings = em.load_findings(root)
    roles = em.entity_roles(findings)
    entities = {e["slug"]: e for e in em.load_entities(root)}
    tsmc = entities["tsmc"]
    html = xr.render_entity_page(tsmc, roles["tsmc"], findings, {}, TODAY)
    assert lint_story_copy(html) == []


def test_entity_page_owned_series_chart(tmp_path):
    root = _explore_store(tmp_path)
    findings = em.load_findings(root)
    roles = em.entity_roles(findings)
    entities = {e["slug"]: e for e in em.load_entities(root)}
    tsmc = entities["tsmc"]
    series = {"pkgCapacityOrderSpread": [_row(1.0, unit="pts"), _row(1.4, unit="pts")]}
    html = xr.render_entity_page(tsmc, roles["tsmc"], findings, series, TODAY)
    assert "<svg" in html


def test_entities_index_groups_both_fixtures(tmp_path):
    root = _explore_store(tmp_path)
    findings = em.load_findings(root)
    roles = em.entity_roles(findings)
    entities = em.load_entities(root)
    html = xr.render_entities_index(entities, roles)

    supply_i = html.index("TSMC")
    buyers_i = html.index("Nvidia")
    # tsmc (supply bottleneck) must render before nvidia (demand driver)
    # given the fixed group order supply chain / buyers / makers / other.
    assert supply_i < buyers_i
    assert lint_story_copy(html) == []
