"""F101c Task 7: narrative-first wiring inside the shared front-page renderers.

These pin the LINK-TARGET changes to story_render/story_model: explore-band
tiles route to the deep pages, the gap-chart label opens the history page, the
closing strip's archive links point at the story archive, KPI-chip and scene
evidence-panel `explore` hrefs point at the series/findings pages, and entity
titles in scene prose become links when (and only when) an `entity_links` map
is supplied.
"""
import datetime as dt
import json

from gpu_agent.dashboard import story_render as sr
from gpu_agent.dashboard.story_model import build_story_model
from gpu_agent.dashboard.story_render import _scene_html, render_story_page

CAT = "chips.merchant-gpu"


def _scene(n=1, paragraphs=None):
    return {"n": n, "accent": "amber", "title": "Test scene",
            "paragraphs": paragraphs or ["Some plain words making up scene body text."],
            "visual": {"series": [], "label": ""},
            "source_line": "Source: test data", "related": []}


# --- _scene_html entity_links parameter --------------------------------------

def test_scene_html_default_is_byte_identical_to_no_param():
    scene = _scene(paragraphs=["The market clearly still leans on Nvidia orders today."])
    assert _scene_html(scene) == _scene_html(scene, entity_links=None)


def test_scene_html_links_first_entity_title_occurrence():
    # "Nvidia" sits past the first six words, so it lands in the paragraph
    # tail (outside the evidence-trigger anchor) and must be wrapped.
    scene = _scene(paragraphs=["The market clearly still leans on Nvidia orders today.",
                               "Nvidia again here."])
    html = _scene_html(scene, entity_links={"Nvidia": "entities/nvidia.html"})
    assert '<a href="entities/nvidia.html">Nvidia</a>' in html
    # first occurrence per scene only -> linked exactly once
    assert html.count('<a href="entities/nvidia.html">') == 1


# --- explore band + closing strip + gap-chart label --------------------------

def _model(tmp_path):
    from tests.dashboard.test_story_model import _store
    return build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))


def test_explore_band_tiles_route_to_deep_pages(tmp_path):
    html = render_story_page(_model(tmp_path))
    # Directory routes (Option A) -- Cloudflare serves each dir's index.html.
    assert 'href="entities/"' in html
    assert 'href="findings/"' in html
    assert 'href="series/"' in html
    assert 'href="history.html"' in html
    # the retired catch-all target is gone from the explore band
    assert 'class="st-tile" href="appendix.html"' not in html


def test_closing_strip_story_archive_links_story_route(tmp_path):
    html = render_story_page(_model(tmp_path))
    assert 'href="story/"' in html
    assert '<a href="#">story archive →</a>' not in html


def test_gap_chart_label_links_history(tmp_path):
    html = render_story_page(_model(tmp_path))
    assert 'href="history.html"' in html
    assert "the gap, this week" in html


# --- story_model evidence-panel explore hrefs --------------------------------

def _impact_store(tmp_path):
    root = tmp_path / "store"
    cat = root / CAT
    cat.mkdir(parents=True)
    finding = {
        "id": "f-1", "statement": "Nvidia demand kept climbing.",
        "impact": {"targets": [CAT], "direction": "positive", "mechanism": "m"},
        "evidence": [{"source": "Micron call", "url": "https://x.example/a",
                      "date": "2026-06-24", "excerpt": "e", "tier": "primary"}],
        "entity": "NVIDIA", "side": "demand", "observedAt": "2026-07-01",
    }
    for m in ("2026-06", "2026-07"):
        (cat / f"{m}-v1.json").write_text(json.dumps({
            "asOf": m, "findings": [finding],
            "demandSupply": {"dmiContribution": 2.0, "smiContribution": 0.2},
            "dimensionRatings": {"bottleneck": {
                "rating": "Weak", "direction": "worsening", "findingIds": ["f-1"],
                "rationale": "Memory makers cut back supply badly this quarter."}},
            "categoryStatus": {"rating": "Strong", "direction": "steady",
                               "bottleneck": "b", "reason": "r.", "constraintLabel": "HBM"},
        }), encoding="utf-8")
    series = root / "series"
    series.mkdir()
    (series / "gpuRentalOnDemand.jsonl").write_text("\n".join(json.dumps({
        "indicatorId": "gpuRentalOnDemand", "period": p, "value": v, "unit": "x",
        "publishedAt": p + "-28",
        "source": {"url": "https://src.example/g", "title": "g"},
    }) for p, v in [("2026-05", 15.1), ("2026-06", 14.6)]), encoding="utf-8")
    return root


def test_scene_evidence_explore_is_findings_hash(tmp_path):
    m = build_story_model(CAT, _impact_store(tmp_path), dt.date(2026, 7, 16))
    scene = next(s for s in m["scenes"] if s["title"] == "What tightened")
    ev = m["evidence"][f"scene:{scene['n']}"]
    assert ev["explore"].startswith("../findings/index.html#")
    assert "dim=" in ev["explore"]
    assert "entity=nvidia" in ev["explore"]


def test_kpi_evidence_explore_is_series_anchor(tmp_path):
    m = build_story_model(CAT, _impact_store(tmp_path), dt.date(2026, 7, 16))
    ev = m["evidence"]["kpi:gpuRentalOnDemand"]
    assert ev["explore"] == "../series/#s-gpuRentalOnDemand"
