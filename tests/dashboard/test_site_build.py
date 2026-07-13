import re
from pathlib import Path

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
            target = (html_path.parent / href).resolve()
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
