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
    summary = _build(tmp_path)          # existing helper @test_site_build.py:13
    idx = (tmp_path / "site" / CAT / "index.html").read_text(encoding="utf-8")
    assert "The story, step by step" in idx
    assert "says who?" in idx
    assert 'id="ev-data"' in idx
    assert "Executive Brief" not in idx
    assert summary["story_lint"] == []
    css = (tmp_path / "site" / CAT / "style.css").read_text(encoding="utf-8")
    assert ".st-chip" in css and ".ev-panel" in css


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


def test_brief_evidence_anchors_resolve_in_appendix(tmp_path):
    # F97 acceptance criterion 6: every evidence link the brief (index.html) points at
    # (#f-<finding-id>, #dim-<dimension-name>) must resolve to a real anchor in
    # appendix.html. A competing SAME-MONTH legacy daily scorecard (fewer dimensions,
    # a different finding id) sits alongside the monthly deep-read in the same category
    # dir, so this reproduces the real-store bug: if any of the three "latest scorecard"
    # selectors (load_scorecards, build.py's build_model, site_model.py's
    # build_site_model) still preferred the daily over the monthly, a #dim-<name>
    # anchor for a dimension only the monthly has (moat, unitEconomics) would dead-end.
    # F100 retarget: the brief now surfaces dimensions via the deep-dive panel's
    # embedded JSON blob instead of appendix.html# links; the assertions below check
    # the same regression through that blob.
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
    # F100: the brief no longer emits <a href="appendix.html#..."> links; the
    # dimensions it surfaces now live in the deep-dive panel's embedded JSON blob
    # (id="dd-data"), keyed by dimension name. The F97 regression intent survives:
    # every dimension the brief surfaces must resolve to a real #dim-<name> anchor in
    # the appendix (brief & appendix must agree on the winning MONTHLY scorecard).
    m = re.search(r'id="dd-data"[^>]*>(.*?)</script>', index, re.S)
    assert m, "brief should embed the deep-dive data blob"
    dd = json.loads(m.group(1))          # json.loads decodes the < escapes
    dims = set(dd.keys())
    assert dims, "deep-dive blob should carry the brief's dimensions"
    # the monthly (6 dims incl. moat + unitEconomics) must have won over the same-month
    # legacy daily (4 dims); if the daily wrongly won, these keys would be absent.
    assert {"moat", "unitEconomics"} <= dims, "monthly scorecard must win over same-month daily"
    for name in dims:
        assert f'id="dim-{name}"' in appendix, f"dead dimension anchor: {name}"
