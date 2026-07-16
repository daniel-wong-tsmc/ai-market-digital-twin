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
        for href in re.findall(r'href="([^"]+)"', html):
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


def test_build_site_index_is_brief(tmp_path):
    # F97: the category index.html is now the executive brief, not the F95 page.
    # This fixture store has only dated daily scorecards (no monthly YYYY-MM-vN.json),
    # so the brief renders defensively-thin (no agenda band, verdict "—") but the
    # masthead and the cold-start "Standing calls" header are always present.
    summary = build_site(CAT, FIX, "work-nonexistent", f"{FIX}/plain-2026-07-06.json",
                         str(tmp_path / "site"), today=dt.date(2026, 7, 16))
    html = (tmp_path / "site" / CAT / "index.html").read_text(encoding="utf-8")
    assert "Executive Brief" in html and "Standing calls" in html
    assert summary["brief_lint"] == []
    css = (tmp_path / "site" / "style.css").read_text(encoding="utf-8")
    assert ".kpis" in css and "status-elevated" in css


def test_appendix_has_dimension_and_finding_anchors(tmp_path):
    build_site(CAT, FIX, "work-nonexistent", f"{FIX}/plain-2026-07-06.json",
               str(tmp_path / "site"), today=dt.date(2026, 7, 16))
    ap = (tmp_path / "site" / CAT / "appendix.html").read_text(encoding="utf-8")
    assert 'id="dimensions"' in ap and 'id="dim-' in ap and 'id="f-' in ap


def test_build_site_lint_gate_aborts_build(tmp_path, monkeypatch):
    import datetime as dt
    import gpu_agent.dashboard.site_build as sb
    monkeypatch.setattr(sb, "lint_exec_copy",
                        lambda html: ["because no alert rule fired"])
    with pytest.raises(ValueError):
        build_site(CAT, FIX, "work-nonexistent", f"{FIX}/plain-2026-07-06.json",
                   str(tmp_path / "site"), today=dt.date(2026, 7, 16))
    # a register violation aborts before the brief index is written
    assert not (tmp_path / "site" / CAT / "index.html").exists()
