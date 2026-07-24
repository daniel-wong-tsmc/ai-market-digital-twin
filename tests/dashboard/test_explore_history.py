"""F101c Task 6: verdict-timeline history page."""
import datetime as dt

from gpu_agent.dashboard import explore_model as em
from gpu_agent.dashboard import explore_render as xr
from gpu_agent.dashboard.gap_chart import render_timeline_svg
from gpu_agent.dashboard.story_render import lint_story_copy
from tests.dashboard.test_explore_fixtures import _explore_store

TODAY = dt.date(2026, 7, 22)


def _timeline(tmp_path):
    root = _explore_store(tmp_path)
    return em.verdict_timeline(root / "chips.merchant-gpu")


def test_render_timeline_svg_contains_all_headlines(tmp_path):
    tl = _timeline(tmp_path)
    headlines = [m["headline"] for m in tl["months"]]
    assert len(headlines) == 2
    svg = render_timeline_svg(tl["gap"], headlines)
    assert svg.count("<svg") == 1 and svg.count("</svg>") == 1
    for h in headlines:
        assert h in svg


def test_render_timeline_svg_empty_data_is_safe():
    assert render_timeline_svg(None, []) == ""


def test_history_page_has_month_details_with_dimension_names(tmp_path):
    tl = _timeline(tmp_path)
    html = xr.render_history_page(tl, TODAY)
    assert '<details id="m-2026-07">' in html
    month = next(m for m in tl["months"] if m["key"] == "2026-07")
    block_start = html.index('<details id="m-2026-07">')
    block_end = html.index("</details>", block_start)
    block = html[block_start:block_end]
    for dim in month["dims"]:
        assert dim in block or xr._DIM_DISPLAY.get(dim, dim) in block
    assert month["constraint"] in block


def test_history_page_has_source_line_and_appendix_link(tmp_path):
    tl = _timeline(tmp_path)
    html = xr.render_history_page(tl, TODAY)
    assert "Source:" in html
    assert 'href="appendix.html"' in html


def test_history_page_svg_carries_both_headlines(tmp_path):
    tl = _timeline(tmp_path)
    html = xr.render_history_page(tl, TODAY)
    for m in tl["months"]:
        assert m["headline"] in html


def test_history_page_is_lint_clean(tmp_path):
    tl = _timeline(tmp_path)
    html = xr.render_history_page(tl, TODAY)
    assert lint_story_copy(html) == []


def test_check_links_resolves_appendix(tmp_path):
    tl = _timeline(tmp_path)
    html = xr.render_history_page(tl, TODAY)
    pages = {
        "chips.merchant-gpu/history.html": html,
        "chips.merchant-gpu/appendix.html": "<h1>Appendix</h1>",
        "chips.merchant-gpu/index.html": "<h1>Today</h1>",
        "style.css": "",
    }
    assert xr.check_links(pages) == []
