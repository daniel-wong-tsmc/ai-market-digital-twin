import datetime as dt
import re
from pathlib import Path

import pytest

from gpu_agent.dashboard.site_build import build_site

FIX = "tests/dashboard/fixtures"
CAT = "chips.merchant-gpu"


def _build(tmp_path, price_fn=lambda d: {"H100": 2.31}):
    return build_site(CAT, FIX, work_dir="work-nonexistent",
                      plain_path=f"{FIX}/plain-2026-07-06.json",
                      out_dir=str(tmp_path / "site"), price_fn=price_fn)


def test_emits_the_full_page_set(tmp_path):
    summary = _build(tmp_path)
    root = tmp_path / "site"
    for rel in ("index.html", "style.css", f"{CAT}/index.html", f"{CAT}/style.css",
                f"{CAT}/appendix.html", f"{CAT}/how/alert.html", f"{CAT}/how/demand.html",
                f"{CAT}/how/supply.html", f"{CAT}/how/gap.html", f"{CAT}/how/featured.html"):
        assert (root / rel).exists(), rel
    assert summary["pages"] >= 8 and summary["featured"] is not None


def test_root_redirect_uses_the_model_category_label(tmp_path):
    # F95 item 4: the redirect label must be the model's human label ("Merchant-GPU
    # Market"), not category_id.title()'d into "Merchant Gpu".
    _build(tmp_path)
    html = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    assert "Merchant-GPU Market" in html
    assert "Merchant Gpu<" not in html


def test_no_price_data_drops_only_the_featured_page(tmp_path):
    _build(tmp_path, price_fn=lambda d: {})
    root = tmp_path / "site"
    assert (root / CAT / "how" / "gap.html").exists()
    # featured falls back to an index metric, so the page still exists:
    assert (root / CAT / "how" / "featured.html").exists()


def test_every_local_href_resolves(tmp_path):
    _build(tmp_path)
    root = tmp_path / "site"
    for html_path in root.rglob("*.html"):
        html = html_path.read_text(encoding="utf-8")
        # F100: the category page now carries the deep-dive panel's self-contained
        # inline <script>, whose JS source contains string literals like
        # "href='+esc(e.url)+'\"" that look like href="..." to this regex but are not
        # real links. Strip script blocks before scanning for hrefs.
        scanned = re.sub(r'(?is)<script\b.*?</script>', '', html)
        for href in re.findall(r'href="([^"]+)"', scanned):
            if href.startswith(("http://", "https://", "#", "mailto:")):
                continue
            # F97: the brief links cross-page fragments (e.g. "appendix.html#dim-
            # momentum", "appendix.html#f-<id>"); only the file part names a real
            # path on disk, so strip any "#..." fragment before resolving.
            file_part = href.split("#", 1)[0]
            target = (html_path.parent / file_part).resolve()
            assert target.exists(), f"{html_path.name} -> {href}"


def test_two_builds_are_byte_identical(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    build_site(CAT, FIX, "work-nonexistent", f"{FIX}/plain-2026-07-06.json",
               str(a), price_fn=lambda d: {"H100": 2.31})
    build_site(CAT, FIX, "work-nonexistent", f"{FIX}/plain-2026-07-06.json",
               str(b), price_fn=lambda d: {"H100": 2.31})
    fa = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    fb = sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    assert fa == fb
    for rel in fa:
        assert (a / rel).read_bytes() == (b / rel).read_bytes(), rel


def test_build_site_index_is_story(tmp_path):
    # F101a final review (item f): the shared _build()/FIX fixture set has
    # only daily-grain scorecards and no series/ dir, so it degrades to zero
    # scenes/chips (see test_story_page_degrades_gracefully_with_only_daily_
    # scorecards_and_no_series above) -- asserting "the story page has real
    # content" against it would only ever exercise the always-rendered
    # static text, which is exactly the weak-assertion shape the review
    # flagged. Build a small store with a real monthly scorecard and one
    # series file instead, so these assertions can actually break.
    import json
    root = tmp_path / "store"
    cat = root / CAT
    cat.mkdir(parents=True)
    finding = {
        "id": "f-1", "statement": "Memory makers cut back supply.",
        "kind": "measured", "value": {"number": 75.0, "unit": "USD_B"},
        "trend": "rising", "why": "Demand signal strengthened.",
        "impact": {"targets": [CAT], "direction": "positive",
                   "mechanism": "Expands addressable demand."},
        "evidence": [{"source": "Micron call", "url": "https://x.example/a",
                     "date": "2026-06-24", "excerpt": "e", "tier": "primary"}],
        "reasoning": None,
        "confidence": {"level": "high", "basis": "primary source"},
        "dispersion": None, "asOf": "2026-07", "indicatorId": "D2",
        "side": "demand", "polarityDemand": 1, "polaritySupply": 0,
        "magnitude": 3, "entity": "NVIDIA", "observedAt": "2026-07-01",
        "capturedAt": "2026-07-02T00:00:00Z",
    }
    (cat / "2026-07-v1.json").write_text(json.dumps({
        "categoryId": CAT, "asOf": "2026-07",
        "findings": [finding],
        "dimensionRatings": {
            "bottleneck": {"rating": "Weak", "direction": "worsening",
                           "confidence": {"level": "high", "basis": "self-consistency"},
                           "findingIds": ["f-1"], "rationale": "Memory makers cut back supply."}},
        "demandSupply": {"dmiContribution": 1.0, "smiContribution": 0.2,
                         "sdgi": 0.4, "sdgiDirection": "demand-led"},
        "narrative": "n", "confidence": {"level": "high", "basis": "n"},
        "sources": [], "dimensionStatus": {},
        "categoryStatus": {"rating": "Strong", "direction": "steady",
                          "bottleneck": "bottleneck", "reason": "r.",
                          "constraintLabel": "HBM"},
    }), encoding="utf-8")
    (cat / "2026-06-v1.json").write_text((cat / "2026-07-v1.json").read_text(
        encoding="utf-8").replace('"2026-07"', '"2026-06"'), encoding="utf-8")
    series = root / "series"
    series.mkdir()
    (series / "gpuRentalOnDemand.jsonl").write_text("\n".join(json.dumps({
        "indicatorId": "gpuRentalOnDemand", "period": p, "value": v, "unit": "x",
        "publishedAt": p + "-28",
        "source": {"url": "https://src.example/gpu", "title": "gpu source"},
    }) for p, v in [("2026-05", 15.1), ("2026-06", 14.6)]), encoding="utf-8")

    summary = build_site(CAT, str(cat), "work-nonexistent", None,
                         str(tmp_path / "site"), price_fn=lambda d: {"H100": 2.31},
                         today=dt.date(2026, 7, 16))
    idx = (tmp_path / "site" / CAT / "index.html").read_text(encoding="utf-8")
    # "The story, step by step" is a hard-coded literal that renders
    # unconditionally whenever the story section exists at all -- pin it
    # together with real scene markup (which only renders when there's
    # actual scene content) so this can't pass on a build with zero scenes.
    assert "The story, step by step" in idx
    assert '<article class="st-scene' in idx
    # "says who?" alone is satisfied by the KPI band's static caption even
    # when the page has zero chips -- pin it together with a real per-chip
    # evidence hookup so this can't pass on a build with zero chips.
    assert "says who?" in idx
    assert 'data-ev="kpi:' in idx
    assert 'id="ev-data"' in idx
    assert "Executive Brief" not in idx
    assert summary["story_lint"] == []
    css = (tmp_path / "site" / CAT / "style.css").read_text(encoding="utf-8")
    # style.css is SITE_CSS + BRIEF_CSS + DASHBOARD_CSS + STORY_CSS concatenated
    # (site_build.py). `.st-chip in css` alone would only ever prove STORY_CSS's
    # own literal text landed in a constant STORY_CSS itself defines -- it can
    # never fail. Assert one marker rule from each bundle instead, so dropping
    # any bundle from the concatenation (including the older appendix/"how"-page
    # rules that still need to ship) breaks this test.
    assert ".how" in css  # SITE_CSS -- appendix/"how" pages' crumb/tile chrome
    assert ".hero" in css  # BRIEF_CSS -- retired brief's rules, still shared
    assert ".kcard" in css  # DASHBOARD_CSS -- deep-dive drawer's KPI cards
    assert ".st-chip" in css and ".ev-panel" in css  # STORY_CSS -- this page's own rules
    assert ".xp-" in css  # EXPLORE_CSS -- the Explore layer's own scaffold rules


def test_style_css_includes_dashboard_theme(tmp_path):
    _build(tmp_path)
    css = (tmp_path / "site" / CAT / "style.css").read_text(encoding="utf-8")
    assert ".kcard" in css and ".dd-drawer" in css


def test_appendix_has_dimension_and_finding_anchors(tmp_path):
    build_site(CAT, FIX, "work-nonexistent", f"{FIX}/plain-2026-07-06.json",
               str(tmp_path / "site"), today=dt.date(2026, 7, 16))
    ap = (tmp_path / "site" / CAT / "appendix.html").read_text(encoding="utf-8")
    assert 'id="dimensions"' in ap and 'id="dim-' in ap and 'id="f-' in ap


def test_build_site_lint_gate_aborts_build(tmp_path, monkeypatch):
    # Task 8 Decision A item 2: retargeted from the retired brief lint
    # (lint_exec_copy) to the story-page copy lint that now gates the index
    # write, keeping this a real abort test rather than a stale mechanism check.
    import datetime as dt
    import gpu_agent.dashboard.site_build as sb
    monkeypatch.setattr(sb, "lint_story_copy",
                        lambda html: ["because no alert rule fired"])
    with pytest.raises(ValueError):
        build_site(CAT, FIX, "work-nonexistent", f"{FIX}/plain-2026-07-06.json",
                   str(tmp_path / "site"), today=dt.date(2026, 7, 16))
    # a copy-lint violation aborts before the story index is written
    assert not (tmp_path / "site" / CAT / "index.html").exists()


def test_story_page_degrades_gracefully_with_only_daily_scorecards_and_no_series(tmp_path):
    # Built against a category with no monthly scorecards (only a legacy
    # daily-grain one, which the story page's own monthly-over-daily guard
    # -- a settled, do-not-change rule -- never surfaces) and no series/
    # dir at all: the story page must degrade honestly (no chart, no empty
    # KPI band/caption, no empty "story, step by step" section) instead of
    # emitting a shell that reads as broken. build_site itself (fed by
    # site_model.py's own daily-tolerant selector) must still succeed.
    import json
    root = tmp_path / "store"
    cat = root / CAT
    cat.mkdir(parents=True)

    scorecard = {
        "categoryId": CAT, "asOf": "2026-07-06", "findings": [],
        "dimensionRatings": {},
        "demandSupply": {"dmiContribution": 0.5, "smiContribution": 0.1,
                         "sdgi": 0.4, "sdgiDirection": "demand-led"},
        "narrative": "n", "confidence": {"level": "high", "basis": "n"},
        "sources": [], "dimensionStatus": {},
        "categoryStatus": {"rating": "Strong", "direction": "steady",
                          "bottleneck": "bottleneck", "reason": "r.",
                          "constraintLabel": "HBM"},
    }
    (cat / "2026-07-06-v1.json").write_text(json.dumps(scorecard), encoding="utf-8")

    summary = build_site(CAT, str(cat), "work-nonexistent", None,
                         str(tmp_path / "site"), price_fn=lambda d: {},
                         today=dt.date(2026, 7, 16))
    assert summary["story_lint"] == []
    idx = (tmp_path / "site" / CAT / "index.html").read_text(encoding="utf-8")
    # Narrowed per final review: "<svg" not in idx is over-broad and would
    # break the first time any decorative graphic (e.g. a sparkline) is
    # added to the degraded page. What this test actually cares about is
    # the demand-vs-supply gap chart specifically, which render_gap_svg
    # renders as an <svg class="gapchart" ...> element (gap_chart.py) --
    # assert that one element is absent, not svg elements in general.
    assert 'class="gapchart"' not in idx
    assert "Not enough" in idx
    assert "says who?" not in idx
    assert "The story, step by step" not in idx
    assert "picked by today's story" not in idx


def test_brief_evidence_anchors_resolve_in_appendix(tmp_path):
    # F97 acceptance criterion 6: every evidence link the brief (index.html) points at
    # (#f-<finding-id>, #dim-<dimension-name>) must resolve to a real anchor in
    # appendix.html. A competing SAME-MONTH legacy daily scorecard (fewer dimensions,
    # a different finding id) sits alongside the monthly deep-read in the same category
    # dir, so this reproduces the real-store bug: if any of the three "latest scorecard"
    # selectors (load_scorecards, build.py's build_model, site_model.py's
    # build_site_model) still preferred the daily over the monthly, a #dim-<name>
    # anchor for a dimension only the monthly has (moat, unitEconomics) would dead-end.
    # F100 retarget: the brief surfaced dimensions via the deep-dive panel's embedded
    # JSON blob instead of appendix.html# links; the assertions checked the same
    # regression through that blob.
    # Task 8 Decision C retarget: index.html is now the F101 story page. Its own
    # evidence blob ("ev-data") is keyed by claim id ("kpi:...", "scene:N"), not by
    # dimension name, AND story_model.py's scene-building (see its _add_scenes) only
    # ever surfaces the bottleneck, momentum, and unitEconomics dimensions -- it has no
    # code path that puts moat, competitiveStructure, or strategicRisk on the page at
    # all. So the regression guard now splits across the two pages that still exist:
    #  - unitEconomics (which story_model DOES expose) is checked through the story
    #    page itself: the "Where supply is gaining" scene is only built when
    #    dims.get("unitEconomics") is truthy, which is true only for the monthly
    #    scorecard in this fixture (the daily has no unitEconomics dimension at all) --
    #    so that scene's presence in index.html is direct proof that build_story_model's
    #    own selector (brief_model.latest_monthly, which story_model.py reuses) chose
    #    the monthly read over the daily.
    #  - moat (which story_model has NO path to expose, regardless of which scorecard
    #    wins) is checked the pre-F100 way, directly against appendix.html: a
    #    #dim-moat anchor there is still proof that site_model.py's own (unchanged by
    #    this lane) selector also chose the monthly read.
    import json
    root = tmp_path / "store"
    cat = root / CAT
    cat.mkdir(parents=True)

    def dim(rating="Mixed", direction="steady", conf="high", rationale="reason"):
        return {"rating": rating, "direction": direction,
                "confidence": {"level": conf, "basis": "self-consistency"},
                "findingIds": ["src-abc-2026-07-1"], "rationale": rationale}

    dims = {d: dim(rationale=f"{d} reason.") for d in
            ("momentum", "unitEconomics", "competitiveStructure",
             "moat", "bottleneck", "strategicRisk")}

    finding = {
        "id": "src-abc-2026-07-1", "statement": "Big demand move this month.",
        "kind": "measured", "value": {"number": 75.0, "unit": "USD_B"},
        "trend": "rising", "why": "Demand signal strengthened.",
        "impact": {"targets": [CAT], "direction": "positive",
                   "mechanism": "Expands addressable demand."},
        "evidence": [{"source": "IR", "url": "https://example.com/ir",
                     "date": "2026-07-02", "excerpt": "excerpt text.",
                     "tier": "primary"}],
        "reasoning": None,
        "confidence": {"level": "high", "basis": "primary source"},
        "dispersion": None, "asOf": "2026-07", "indicatorId": "D2",
        "side": "demand", "polarityDemand": 1, "polaritySupply": 0,
        "magnitude": 3, "entity": "NVIDIA", "observedAt": "2026-07-01",
        "capturedAt": "2026-07-02T00:00:00Z",
    }

    scorecard = {
        "categoryId": CAT, "asOf": "2026-07", "findings": [finding],
        "dimensionRatings": dims,
        "demandSupply": {"dmiContribution": 0.5, "smiContribution": 0.1,
                         "sdgi": 0.4, "sdgiDirection": "demand-led"},
        "narrative": "n", "confidence": {"level": "high", "basis": "n"},
        "sources": [], "dimensionStatus": {},
        "categoryStatus": {"rating": "Strong", "direction": "steady",
                          "bottleneck": "bottleneck", "reason": "r.",
                          "constraintLabel": "HBM"},
    }
    (cat / "2026-07-v1.json").write_text(json.dumps(scorecard), encoding="utf-8")

    # Competing legacy daily: same month, higher-sorting filename ("2026-07-06" >
    # "2026-07" lexicographically), but only 4 of 6 dimensions and a different finding
    # id — a stand-in for a real pre-cadence-change intra-month scorecard.
    daily_dims = {d: dim(rationale=f"{d} daily reason.") for d in
                 ("momentum", "competitiveStructure", "bottleneck", "strategicRisk")}
    daily_finding = {**finding, "id": "daily-legacy-2026-07-06-1",
                     "observedAt": "2026-07-06", "asOf": "2026-07-06",
                     "capturedAt": "2026-07-06T00:00:00Z"}
    daily_scorecard = {**scorecard, "asOf": "2026-07-06", "findings": [daily_finding],
                       "dimensionRatings": daily_dims}
    (cat / "2026-07-06-v1.json").write_text(json.dumps(daily_scorecard), encoding="utf-8")

    impl = root / "implications" / CAT
    impl.mkdir(parents=True)
    (impl / "2026-07.json").write_text(json.dumps({"lines": [
        {"watchItem": "Wafer exposure.", "dimensions": ["momentum"],
         "thesisIds": [], "findingIds": ["src-abc-2026-07-1"]}]}), encoding="utf-8")

    build_site(CAT, str(cat), "work-nonexistent", None, str(tmp_path / "site"),
               today=dt.date(2026, 7, 16))
    site = tmp_path / "site" / CAT
    index = (site / "index.html").read_text(encoding="utf-8")
    appendix = (site / "appendix.html").read_text(encoding="utf-8")

    # story_model.py's own "latest scorecard" selector (brief_model.latest_monthly,
    # reused verbatim by build_story_model) chose the monthly read over the
    # same-month daily: proven by the unitEconomics-only scene existing at all. The
    # daily scorecard has no "unitEconomics" dimension, so if it had wrongly won,
    # story_model.py's `dims.get("unitEconomics")` check would be falsy and this
    # scene would never be built.
    assert "Where supply is gaining" in index, (
        "story page should surface the unitEconomics scene, proving "
        "build_story_model's selector chose the monthly scorecard over the daily")
    assert 'id="ev-data"' in index, "story page should embed its evidence blob"

    # site_model.py's selector (unchanged by this lane) also chose the monthly read:
    # moat has no code path onto the story page at all (story_model.py's
    # _add_scenes only ever builds bottleneck/momentum/unitEconomics scenes), so its
    # half of the regression guard stays on appendix.html, exactly as it did before
    # F100 introduced the now-retired deep-dive-panel blob.
    assert 'id="dim-moat"' in appendix, "dead dimension anchor: moat"
    assert 'id="dim-unitEconomics"' in appendix, "dead dimension anchor: unitEconomics"



# --- F101c Task 7: Explore-layer emission + narrative-first wiring + link gate

import json as _json

from tests.dashboard.test_explore_fixtures import _explore_store, _wiki_page


def _full_scorecard(as_of, *, rationale, finding_id="f-1", entity="NVIDIA"):
    """A schema-complete monthly scorecard (build_site_model validates the full
    report schema via report.load_scorecard, unlike the lenient story reader)."""
    finding = {
        "id": finding_id, "statement": "Nvidia demand kept climbing.",
        "kind": "measured", "value": {"number": 75.0, "unit": "USD_B"},
        "trend": "rising", "why": "Demand signal grew.",
        "impact": {"targets": [CAT], "direction": "positive",
                   "mechanism": "Expands addressable demand."},
        "evidence": [{"source": "Micron call", "url": "https://x.example/a",
                      "date": "2026-06-24", "excerpt": "e", "tier": "primary"}],
        "reasoning": None,
        "confidence": {"level": "high", "basis": "primary source"},
        "dispersion": None, "asOf": as_of, "indicatorId": "D2",
        "side": "demand", "polarityDemand": 1, "polaritySupply": 0,
        "magnitude": 3, "entity": entity, "observedAt": "2026-07-01",
        "capturedAt": "2026-07-02T00:00:00Z",
    }
    return {
        "categoryId": CAT, "asOf": as_of, "findings": [finding],
        "dimensionRatings": {"bottleneck": {
            "rating": "Weak", "direction": "worsening",
            "confidence": {"level": "high", "basis": "self-consistency"},
            "findingIds": [finding_id], "rationale": rationale}},
        "demandSupply": {"dmiContribution": 2.0, "smiContribution": 0.2,
                         "sdgi": 0.4, "sdgiDirection": "demand-led"},
        "narrative": "n", "confidence": {"level": "high", "basis": "n"},
        "sources": [], "dimensionStatus": {},
        "categoryStatus": {"rating": "Strong", "direction": "steady",
                           "bottleneck": "bottleneck", "reason": "r.",
                           "constraintLabel": "HBM"},
    }


def _full_explore_store(tmp_path, rationale="Memory makers cut back supply badly this quarter."):
    # _explore_store gives wiki entities, standalone findings and story
    # artifacts, but its monthly scorecards are the lenient story-reader shape.
    # Overwrite them with schema-complete ones so build_site_model validates.
    root = _explore_store(tmp_path)
    cat = root / CAT
    for m in ("2026-06", "2026-07"):
        (cat / f"{m}-v1.json").write_text(
            _json.dumps(_full_scorecard(m, rationale=rationale)), encoding="utf-8")
    return root


def test_emits_the_explore_page_families(tmp_path):
    root = _full_explore_store(tmp_path)
    summary = build_site(CAT, str(root / CAT), "work-nonexistent", None,
                         str(tmp_path / "site"), price_fn=lambda d: {},
                         today=dt.date(2026, 7, 22))
    site = tmp_path / "site" / CAT
    for rel in ("story/index.html", "findings/index.html", "series/index.html",
                "entities/index.html", "entities/nvidia.html", "entities/tsmc.html",
                "history.html"):
        assert (site / rel).exists(), rel
    # every narrated day gets its own permalink
    assert (site / "story" / "2026-07-22.html").exists()
    assert (site / "story" / "2026-07-21.html").exists()
    assert summary["explore_pages"] >= 8


def test_front_index_links_findings_page(tmp_path):
    root = _full_explore_store(tmp_path)
    build_site(CAT, str(root / CAT), "work-nonexistent", None,
               str(tmp_path / "site"), price_fn=lambda d: {},
               today=dt.date(2026, 7, 22))
    idx = (tmp_path / "site" / CAT / "index.html").read_text(encoding="utf-8")
    assert 'href="findings/"' in idx


def _wired_store(tmp_path):
    # Assembler path (no story artifact for `today`): a dimension rationale
    # mentions the entity title past word 6 so it lands in the scene tail and
    # gets entity-linked; a matching wiki entity supplies the link target.
    root = tmp_path / "store"
    cat = root / CAT
    cat.mkdir(parents=True)
    rationale = "The main supply constraint now clearly runs through Nvidia order books."
    for m in ("2026-06", "2026-07"):
        (cat / f"{m}-v1.json").write_text(
            _json.dumps(_full_scorecard(m, rationale=rationale)), encoding="utf-8")
    series = root / "series"
    series.mkdir()
    (series / "gpuRentalOnDemand.jsonl").write_text("\n".join(_json.dumps({
        "indicatorId": "gpuRentalOnDemand", "period": p, "value": v, "unit": "x",
        "publishedAt": p + "-28",
        "source": {"url": "https://src.example/g", "title": "g"},
    }) for p, v in [("2026-05", 15.1), ("2026-06", 14.6)]), encoding="utf-8")
    findings = root / "findings"
    findings.mkdir()
    (findings / "fa.json").write_text(_json.dumps({
        "id": "fa", "statement": "Nvidia demand finding.", "side": "demand",
        "entity": "nvidia", "observedAt": "2026-07-20",
        "impact": {"targets": [CAT], "direction": "positive", "mechanism": "m"},
        "evidence": [{"source": "s", "url": "https://x.example/z",
                      "date": "2026-07-20", "tier": "primary"}],
    }), encoding="utf-8")
    wiki = root / "wiki" / "entity"
    wiki.mkdir(parents=True)
    (wiki / "nvidia.md").write_text(_wiki_page("nvidia", "Nvidia"), encoding="utf-8")
    return root


def test_scene_prose_carries_entity_link(tmp_path):
    root = _wired_store(tmp_path)
    build_site(CAT, str(root / CAT), "work-nonexistent", None,
               str(tmp_path / "site"), price_fn=lambda d: {},
               today=dt.date(2026, 7, 16))
    idx = (tmp_path / "site" / CAT / "index.html").read_text(encoding="utf-8")
    assert '<a href="entities/nvidia.html">Nvidia</a>' in idx


def test_front_index_panel_explore_carries_dim(tmp_path):
    root = _wired_store(tmp_path)
    build_site(CAT, str(root / CAT), "work-nonexistent", None,
               str(tmp_path / "site"), price_fn=lambda d: {},
               today=dt.date(2026, 7, 16))
    idx = (tmp_path / "site" / CAT / "index.html").read_text(encoding="utf-8")
    assert "#dim=" in idx


def test_link_gate_aborts_on_dead_href(tmp_path, monkeypatch):
    import gpu_agent.dashboard.site_build as sb
    monkeypatch.setattr(sb, "render_findings_page",
                        lambda *a, **k: '<a href="does-not-exist.html">x</a>')
    root = _full_explore_store(tmp_path)
    with pytest.raises(ValueError):
        build_site(CAT, str(root / CAT), "work-nonexistent", None,
                   str(tmp_path / "site"), price_fn=lambda d: {},
                   today=dt.date(2026, 7, 22))


def _explore_targets(html):
    # Pull each evidence entry's `explore` href out of the ev-data JSON blob.
    # check_links structurally can't see these (they're JSON, and only become an
    # href via JS at runtime), so they need their own disk-resolve assertion.
    import re as _re
    m = _re.search(r'<script type="application/json" id="ev-data">(.*?)</script>',
                   html, _re.S)
    assert m, "ev-data blob missing"
    data = _json.loads(m.group(1))
    return [v["explore"] for v in data.values()
            if isinstance(v, dict) and v.get("explore")]


def test_evidence_explore_targets_resolve_on_both_surfaces(tmp_path):
    # Closes the gate blind spot: the pre-filtered "see everything we have →"
    # explore CTA lives in the lint-stripped ev-data JSON, so check_links never
    # sees it. Assert it resolves to a really-emitted page on BOTH the front
    # page (category root, depth 0) and a story permalink (one dir down).
    root = _full_explore_store(tmp_path)
    build_site(CAT, str(root / CAT), "work-nonexistent", None,
               str(tmp_path / "site"), price_fn=lambda d: {},
               today=dt.date(2026, 7, 22))
    site = tmp_path / "site" / CAT

    idx = (site / "index.html").read_text(encoding="utf-8")
    front = _explore_targets(idx)
    assert any("#dim=" in t for t in front), "no pre-filtered findings CTA on front page"
    for t in front:
        file_part = t.split("#", 1)[0]
        assert (site / file_part).resolve().exists(), f"front-page dead explore: {t}"

    perm = (site / "story" / "2026-07-22.html").read_text(encoding="utf-8")
    for t in _explore_targets(perm):
        file_part = t.split("#", 1)[0]
        assert (site / "story" / file_part).resolve().exists(), f"permalink dead explore: {t}"
