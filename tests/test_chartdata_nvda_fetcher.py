"""F134: NVIDIA quarterly Data Center revenue fetcher.

Companion to the AMD fetcher tested in test_chartdata_fetch.py. NVIDIA's
investor site is shaped differently enough from AMD's that four user
rulings (2026-09-01) were needed before this could be written; each
divergence is pinned by a test here so a future reader can see it was
deliberate rather than sloppy:

- Q2 ruling: the registry's sourceUrl is NVIDIA's *financial-reports*
  page, not the quarterly-results page. The quarterly-results page is a
  JavaScript shell whose served HTML contains no press-release links at
  all, so an AMD-style discoverer is impossible against it.
- Q3 ruling: NVIDIA publishes no exact Data Center figure anywhere -- not
  in any table in the release. The number exists only in the release's
  prose subtitle, already rounded by NVIDIA to one decimal in billions.
  We take that published rounding verbatim; ONE point per release, so
  there is no free backfill the way AMD's three-column table gives.
- Q4 ruling: quarters are labelled by the CALENDAR quarter the period
  ends in, matching the AMD series' rule -- so NVIDIA's "Q2 FY2027",
  which ended 2026-07-26, charts as 2026-Q3.

Like the AMD tests, everything here runs against saved fixtures; the
fetcher itself never touches the network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gpu_agent.chartdata import fetch as fetch_mod
from gpu_agent.chartdata.fetch import ParseFailed, run_fetch
from gpu_agent.chartdata.fetchers import nvda_dc_revenue
from gpu_agent.chartdata.registry import load_chart_series

LANDING_FIXTURE_PATH = "fixtures/chartdata/nvda-ir-financial-reports-landing.html"
DETAIL_FIXTURE_PATH = "fixtures/chartdata/nvda-news-q2-fy2027.html"
SHELL_FIXTURE_PATH = "fixtures/chartdata/nvda-ir-quarterly-results-landing.html"
REGISTRY_PATH = "registry/chart-series.json"

REAL_DETAIL_URL = ("https://nvidianews.nvidia.com/news/"
                   "nvidia-announces-financial-results-for-second-quarter-fiscal-2027")


def _landing_html() -> str:
    return Path(LANDING_FIXTURE_PATH).read_text(encoding="utf-8")


def _detail_html() -> str:
    return Path(DETAIL_FIXTURE_PATH).read_text(encoding="utf-8")


def _landing_url() -> str:
    return load_chart_series(REGISTRY_PATH)["nvdaDataCenterRevenue"].sourceUrl


# ── nvda_dc_revenue.discover ───────────────────────────────────────────────

def test_discover_finds_the_real_press_release_on_the_real_landing_page():
    assert nvda_dc_revenue.discover(_landing_html(), _landing_url()) == REAL_DETAIL_URL


def test_discover_raises_parsefailed_when_no_latest_report_block():
    with pytest.raises(ParseFailed):
        nvda_dc_revenue.discover("<html><body>nothing here</body></html>",
                                 _landing_url())


def test_discover_raises_parsefailed_on_the_javascript_shell_page():
    """The registry USED to point at NVIDIA's quarterly-results page. That
    page renders its quarter list in the browser, so the HTML a fetcher
    actually receives carries no links whatsoever. If someone ever points
    sourceUrl back at it, this must fail loudly rather than quietly find
    nothing -- that silent-nothing is the exact shape of the F131 bug this
    whole lane descends from."""
    with pytest.raises(ParseFailed):
        nvda_dc_revenue.discover(
            Path(SHELL_FIXTURE_PATH).read_text(encoding="utf-8"), _landing_url())


def test_discover_raises_parsefailed_when_the_block_has_no_link():
    html_text = ('<div class="module module-embed module-financial-mashup">'
                 '<div class="module-financial-mashup_news">'
                 '<h3>NVIDIA Announces Financial Results</h3>'
                 '</div></div>')
    with pytest.raises(ParseFailed):
        nvda_dc_revenue.discover(html_text, _landing_url())


def test_discover_raises_parsefailed_on_an_unrendered_template_placeholder():
    """NVIDIA's page is built from Mustache templates. A half-rendered page
    would hand us a literal '{{docUrl}}' -- which urljoin would happily turn
    into a real-looking absolute URL. Refuse it instead of fetching garbage."""
    html_text = ('<div class="module module-embed module-financial-mashup">'
                 '<div class="module-financial-mashup_news">'
                 '<div class="module_links"><a href="{{docUrl}}">Read More</a></div>'
                 '</div></div>')
    with pytest.raises(ParseFailed):
        nvda_dc_revenue.discover(html_text, _landing_url())


def test_discover_resolves_a_relative_href_against_the_landing_url():
    html_text = ('<div class="module module-embed module-financial-mashup">'
                 '<div class="module-financial-mashup_news">'
                 '<div class="module_links">'
                 '<a href="/news/some-quarter">Read More</a></div>'
                 '</div></div>')
    assert nvda_dc_revenue.discover(
        html_text, "https://investor.nvidia.com/financial-info/financial-reports/"
        "default.aspx") == "https://investor.nvidia.com/news/some-quarter"


# ── nvda_dc_revenue.parse ──────────────────────────────────────────────────

def test_parse_extracts_the_q2_fy2027_data_center_figure():
    points = nvda_dc_revenue.parse(_detail_html())
    assert len(points) == 1
    p = points[0]
    assert p["value"] == pytest.approx(89.0)
    assert p["unit"] == "US$ billions"
    assert p["publishedAt"] == "2026-08-26"
    assert p["sourceUrl"] == REAL_DETAIL_URL
    assert p["title"]


def test_parse_labels_the_quarter_by_calendar_not_by_nvidias_fiscal_year():
    """Q4 ruling: NVIDIA calls this "Q2 FY2027" and it ended 2026-07-26, so
    the calendar rule the AMD series uses makes it 2026-Q3. Pinned because
    the fiscal-vs-calendar mismatch is genuinely surprising."""
    assert nvda_dc_revenue.parse(_detail_html())[0]["period"] == "2026-Q3"


def test_parse_returns_exactly_one_quarter_because_nvidia_publishes_no_table():
    """Unlike AMD, whose three-column table backfills prior quarters for
    free, NVIDIA's release states Data Center revenue once, in prose. This
    pins that we are not silently inventing extra periods from the
    percentage comparisons sitting next to it."""
    assert len(nvda_dc_revenue.parse(_detail_html())) == 1


def test_parse_raises_parsefailed_on_unrecognized_markup():
    with pytest.raises(ParseFailed):
        nvda_dc_revenue.parse("<html><body>not an NVIDIA release</body></html>")


def _synthetic_release(figure: str = "$89.0 billion",
                       quarter_end: str = "July 26, 2026",
                       article_date: str = "August 26, 2026") -> str:
    return (f"<html><head><title>NVIDIA Announces Results</title>"
            f'<link rel="canonical" href="{REAL_DETAIL_URL}" /></head><body>'
            f"<li>Data Center revenue of {figure}, up 117% from a year ago</li>"
            f"<p>NVIDIA today reported revenue for the second quarter ended "
            f"{quarter_end}, of $96.2 billion.</p>"
            f'<div class="article-date"> {article_date} </div>'
            f"</body></html>")


def test_synthetic_release_is_a_faithful_stand_in_for_the_real_one():
    """Guards the negative tests below: if this scaffold ever stops parsing,
    those tests would pass for the wrong reason (everything raises)."""
    p = nvda_dc_revenue.parse(_synthetic_release())[0]
    assert (p["period"], p["value"], p["publishedAt"]) == ("2026-Q3", 89.0, "2026-08-26")


def test_parse_refuses_a_figure_stated_in_millions_rather_than_converting():
    """The series unit is US$ billions and the standing rule is that numbers
    parse verbatim -- never converted. A millions figure must fail loudly so
    a person looks, not get quietly divided by a thousand."""
    with pytest.raises(ParseFailed):
        nvda_dc_revenue.parse(_synthetic_release(figure="$890.0 million"))


def test_parse_raises_parsefailed_when_the_quarter_end_date_is_missing():
    html_text = _synthetic_release().replace("quarter ended July 26, 2026", "quarter")
    with pytest.raises(ParseFailed):
        nvda_dc_revenue.parse(html_text)


def test_parse_raises_parsefailed_when_the_publication_date_is_missing():
    html_text = _synthetic_release().replace('class="article-date"', 'class="other"')
    with pytest.raises(ParseFailed):
        nvda_dc_revenue.parse(html_text)


def test_parse_raises_parsefailed_on_an_unrecognized_month_name():
    with pytest.raises(ParseFailed):
        nvda_dc_revenue.parse(_synthetic_release(quarter_end="Smarch 26, 2026"))


@pytest.mark.parametrize("quarter_end, expected", [
    ("April 26, 2026", "2026-Q2"),
    ("July 26, 2026", "2026-Q3"),
    ("October 25, 2026", "2026-Q4"),
    ("January 25, 2027", "2027-Q1"),
])
def test_parse_maps_each_nvidia_quarter_end_to_its_calendar_quarter(
        quarter_end, expected):
    """NVIDIA's fiscal quarters end in Apr/Jul/Oct/Jan, so every one of the
    four lands in a different calendar quarter from its fiscal name."""
    assert nvda_dc_revenue.parse(
        _synthetic_release(quarter_end=quarter_end))[0]["period"] == expected


# ── end to end, through run_fetch, against both real fixtures ──────────────

def _stub_fetch_html(calls: list[str] | None = None):
    """URL-aware stub, same discipline as the AMD suite's: it serves the
    landing fixture for the registry's sourceUrl and the release fixture for
    the URL discover() actually finds, and raises for anything else -- so a
    test can only pass if run_fetch asked for the RIGHT page at each step."""
    landing_url = _landing_url()

    def _fetch(url: str) -> str:
        if calls is not None:
            calls.append(url)
        if url == landing_url:
            return _landing_html()
        if url == REAL_DETAIL_URL:
            return _detail_html()
        raise AssertionError(f"unexpected fetch_html call for {url!r}")

    return _fetch


def test_run_fetch_end_to_end_lands_the_real_quarter_in_the_store(tmp_path):
    """The whole path the next live cycle will walk: open NVIDIA's
    financial-reports page, find this quarter's release on it, read the Data
    Center figure, append it."""
    series = {"nvdaDataCenterRevenue":
              load_chart_series(REGISTRY_PATH)["nvdaDataCenterRevenue"]}
    calls: list[str] = []
    result = run_fetch(series, "2026-09-01", {"nvidia": "2026-08-26"},
                       str(tmp_path), fetch_html=_stub_fetch_html(calls))

    assert result["failed"] == []
    assert result["notFetchable"] == []
    assert result["fetched"] == [{"id": "nvdaDataCenterRevenue", "newPoints": 1}]
    # the landing page first, then the release discovered on it -- in order
    assert calls == [_landing_url(), REAL_DETAIL_URL]

    rows = [json.loads(line) for line in
            (tmp_path / "nvdaDataCenterRevenue.jsonl").read_text(
                encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["period"] == "2026-Q3"
    assert rows[0]["value"] == pytest.approx(89.0)
    assert rows[0]["unit"] == "US$ billions"


def test_run_fetch_append_is_idempotent_for_nvidia(tmp_path):
    """One quarter per release means every cycle inside the window re-reads
    the SAME release. Running twice must not duplicate the row."""
    series = {"nvdaDataCenterRevenue":
              load_chart_series(REGISTRY_PATH)["nvdaDataCenterRevenue"]}
    for _ in range(2):
        run_fetch(series, "2026-09-01", {"nvidia": "2026-08-26"}, str(tmp_path),
                  fetch_html=_stub_fetch_html())

    rows = (tmp_path / "nvdaDataCenterRevenue.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(rows) == 1


def test_run_fetch_never_raises_when_nvidias_page_is_unreadable(tmp_path):
    """A 403, a redesign, a half-rendered page -- all must degrade to a
    reported failure, never a crashed cycle."""
    series = {"nvdaDataCenterRevenue":
              load_chart_series(REGISTRY_PATH)["nvdaDataCenterRevenue"]}
    result = run_fetch(series, "2026-09-01", {"nvidia": "2026-08-26"},
                       str(tmp_path),
                       fetch_html=lambda url: "<html>403 Forbidden</html>")
    assert result["fetched"] == []
    assert [f["id"] for f in result["failed"]] == ["nvdaDataCenterRevenue"]


# ── F134 Q1: the shared reader must identify itself ────────────────────────

def test_default_fetch_request_sends_a_browser_user_agent():
    """Both NVIDIA hosts answer 403 to urllib's default, unidentified
    request. Without a User-Agent the fetcher above is correct and still
    useless, so the header is pinned here rather than left to chance."""
    req = fetch_mod._build_request("https://investor.nvidia.com/financial-info/"
                                   "financial-reports/default.aspx")
    ua = req.get_header("User-agent")
    assert ua and "Mozilla/5.0" in ua
    assert "python-urllib" not in ua.lower()


def test_default_fetch_request_preserves_the_url_it_was_given():
    """A header change must not quietly rewrite the address -- AMD's fetcher
    goes through this same helper."""
    url = "https://ir.amd.com/financial-information/quarterly-results"
    assert fetch_mod._build_request(url).full_url == url


# ── F134 Q3: the stored row must admit the figure is NVIDIA's rounding ─────

def test_stored_row_note_records_that_the_figure_is_nvidias_own_rounding(tmp_path):
    """A reader who opens the series file a year from now should be able to
    see, without leaving the file, that this number is rounded as published
    and that the quarter label is a calendar one -- the two things about this
    series a reader would otherwise get wrong."""
    series = {"nvdaDataCenterRevenue":
              load_chart_series(REGISTRY_PATH)["nvdaDataCenterRevenue"]}
    run_fetch(series, "2026-09-01", {"nvidia": "2026-08-26"}, str(tmp_path),
              fetch_html=_stub_fetch_html())
    note = json.loads((tmp_path / "nvdaDataCenterRevenue.jsonl").read_text(
        encoding="utf-8").strip())["note"]

    assert "89.0" in note
    assert "rounded" in note.lower()
    assert "2026-07-26" in note          # the real fiscal quarter end
    assert "Nvidia data center revenue, 2026-Q3" in note   # generic line kept


def test_a_fetcher_that_supplies_no_note_suffix_keeps_the_plain_note(tmp_path):
    """The note hook is optional: AMD supplies nothing and must be
    unaffected."""
    from gpu_agent.chartdata.fetch import _note
    cs = load_chart_series(REGISTRY_PATH)["amdDataCenterRevenue"]
    assert _note(cs, {"period": "2026-Q2"}) == (
        "AMD investor relations: AMD data center revenue, 2026-Q2")
    assert _note(cs, {"period": "2026-Q2", "noteSuffix": "  "}) == (
        "AMD investor relations: AMD data center revenue, 2026-Q2")
