import re

from gpu_agent.dashboard.site_model import build_site_model
from gpu_agent.dashboard.site_render import (
    HOW_LINKS, page, render_category_page, render_index_redirect,
)
from gpu_agent.reader import lint_acronyms

FIX = "tests/dashboard/fixtures"
CAT = "chips.merchant-gpu"


def _model():
    return build_site_model(CAT, FIX, work_dir="work-nonexistent",
                            plain_path=f"{FIX}/plain-2026-07-06.json",
                            price_fn=lambda d: {"H100": 2.31})


def _text_above_appendix(html):
    cut = html.split('id="appendix-links"')[0]
    return re.sub(r"<[^>]+>", " ", cut)


def test_category_page_structure_and_links():
    html = render_category_page(_model())
    assert html.startswith("<!doctype html>")
    for href in HOW_LINKS.values():
        assert f'href="{href}"' in html
    assert 'id="appendix-links"' in html
    assert "Why it reads this way" in html
    assert "MERCHANT GPU" in html
    assert "2026-07-06" in html


def test_featured_tile_renders_value_and_reason_link():
    html = render_category_page(_model())
    assert "$2.31/GPU-hr" in html
    assert 'href="how/featured.html"' in html


def test_no_featured_drops_tile_and_link():
    m = _model()
    m["featured"] = None
    m["why"] = [w for w in m["why"] if w["topic"] != "featured"]
    html = render_category_page(m)
    assert 'href="how/featured.html"' not in html


def test_implication_section_conditional():
    m = _model()
    assert "For TSMC" not in render_category_page(m)
    m["implication"] = {"lines": ["Watch CoWoS allocation notes."]}
    html = render_category_page(m)
    assert "For TSMC" in html and "Watch CoWoS allocation notes." in html


def test_above_fold_text_passes_acronym_lint_and_no_slop():
    html = render_category_page(_model())
    text = _text_above_appendix(html)
    assert lint_acronyms(text) == []
    for slop in ("delve", "leverage", "seamless", "tapestry"):
        assert slop not in text.lower()


def test_render_is_deterministic_and_clockless():
    m = _model()
    assert render_category_page(m) == render_category_page(m)
    import gpu_agent.dashboard.site_render as sr
    import inspect
    src = inspect.getsource(sr)
    assert "datetime.now" not in src and "date.today" not in src


def test_index_redirect_points_at_category():
    html = render_index_redirect("chips.merchant-gpu/index.html", "Merchant GPU")
    assert 'http-equiv="refresh"' in html and "chips.merchant-gpu/index.html" in html


def test_populated_calls_render_top5_names_oneliners_and_breaks_if(tmp_path):
    # Every other test uses work_dir="work-nonexistent" (calls=[]); this one pins the
    # populated branch of _calls(): the top-5 cap, real call names (the `name` key from
    # parse_calls), the one-liner rest list, and a breaks-if line.
    work = tmp_path / "work" / "daily-2026-07-06"
    work.mkdir(parents=True)
    with open(f"{FIX}/report-2026-07-06.txt", encoding="utf-8", errors="replace") as fh:
        (work / "report.txt").write_text(fh.read(), encoding="utf-8")
    m = build_site_model(CAT, FIX, work_dir=str(tmp_path / "work"),
                         plain_path=f"{FIX}/plain-2026-07-06.json",
                         price_fn=lambda d: {"H100": 2.31})
    html = render_category_page(m)
    assert "The top calls (5 of 14)" in html      # fixture report carries 14 calls
    assert "NVDA demand durability" in html       # a known call name from the fixture
    assert 'class="callmore"' in html             # calls 6..14 render as one-liners
    assert "breaks if:" in html
