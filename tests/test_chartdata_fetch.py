"""F110 Task 4: chart-data fetch framework + AMD data-center revenue fetcher.

The single most important guarantee tested here: run_fetch NEVER raises,
even when fetch_html blows up -- this code runs inside the unattended daily
pipeline, and a broken web page must degrade to "no new data", never to a
crashed run. The second guarantee: appends are idempotent -- running the
same fetch twice must never duplicate a period in the series file.

Fix round 2 (user decision, verbatim): "Follow the link automatically -- the
daily run opens AMD's landing page, finds the newest quarterly-results press
release linked there, and reads the numbers from it. Keeps working every
quarter with nobody touching it." registry/chart-series.json's sourceUrl for
amdDataCenterRevenue is the durable landing page; the fetch path is now
landing page -> discover the detail-page URL -> fetch + parse the detail
page. Every test's fetch_html stub is now URL-aware (returns different HTML
per URL, and raises if asked for a URL neither fixture represents) --
closing the gap the reviewer flagged in round 1, where a stub that ignored
`url` entirely made the wrong-page bug structurally invisible.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gpu_agent.chartdata.fetch import ParseFailed, due_series, run_fetch
from gpu_agent.chartdata.fetchers import amd_dc_revenue
from gpu_agent.chartdata.registry import ChartSeries, load_chart_series

LANDING_FIXTURE_PATH = "fixtures/chartdata/amd-ir-quarterly-results-landing.html"
DETAIL_FIXTURE_PATH = "fixtures/chartdata/amd-ir-q2-2026.html"
REGISTRY_PATH = "registry/chart-series.json"


def _landing_html() -> str:
    return Path(LANDING_FIXTURE_PATH).read_text(encoding="utf-8")


def _detail_html() -> str:
    return Path(DETAIL_FIXTURE_PATH).read_text(encoding="utf-8")


def _series_fixture() -> dict[str, ChartSeries]:
    return load_chart_series(REGISTRY_PATH)


def _landing_url() -> str:
    return _series_fixture()["amdDataCenterRevenue"].sourceUrl


def _real_detail_url() -> str:
    """The exact detail URL discover() finds on the real saved landing
    fixture -- computed once here so tests don't hand-duplicate the literal
    URL string alongside the fixture that's the actual source of truth."""
    return amd_dc_revenue.discover(_landing_html(), _landing_url())


def _stub_fetch_html(calls: list[str] | None = None):
    """A fetch_html stub that returns different HTML per URL: the landing
    fixture for the registry's sourceUrl, the detail fixture for whatever
    URL discover() actually finds on that landing page. Raises on any other
    URL rather than silently returning something -- a test built on this
    stub can only pass if run_fetch requested the RIGHT URL at each step,
    not just 'some URL' (review finding #3/discussion for round 1 -- a stub
    that ignores `url` makes a wrong-page bug invisible). `calls`, if given,
    records every URL requested in order so a test can assert the exact
    fetch sequence."""
    landing_url = _landing_url()
    detail_url = _real_detail_url()

    def _fetch(url: str) -> str:
        if calls is not None:
            calls.append(url)
        if url == landing_url:
            return _landing_html()
        if url == detail_url:
            return _detail_html()
        raise AssertionError(f"unexpected fetch_html call for {url!r}")

    return _fetch


# ── amd_dc_revenue.discover ────────────────────────────────────────────────

def test_discover_finds_the_real_q2_2026_detail_url_on_the_real_landing_page():
    detail_url = amd_dc_revenue.discover(_landing_html(), _landing_url())
    assert detail_url == (
        "https://ir.amd.com/news-events/press-releases/detail/1295/"
        "amd-reports-second-quarter-2026-financial-results")


def test_discover_raises_parsefailed_when_no_quarterly_results_block():
    with pytest.raises(ParseFailed):
        amd_dc_revenue.discover("<html><body>nothing here</body></html>",
                                 "https://ir.amd.com/financial-information/quarterly-results")


def test_discover_raises_parsefailed_when_block_has_no_earnings_release_link():
    html_text = (
        '<div class="box quarterly-results" id="2026-9232-results">'
        '<a href="/slides.pdf" aria-label="Slide Presentation Q2 2026 PDF">Slides</a>'
        '</div>'
    )
    with pytest.raises(ParseFailed):
        amd_dc_revenue.discover(html_text,
                                 "https://ir.amd.com/financial-information/quarterly-results")


def test_discover_resolves_a_relative_href_against_the_landing_url():
    html_text = (
        '<div class="box quarterly-results" id="2026-9232-results">'
        '<a href="/news-events/press-releases/detail/1295/'
        'amd-reports-second-quarter-2026-financial-results" '
        'aria-label="Earnings Release Q2 2026 HTML">Earnings Release</a>'
        '</div>'
    )
    detail_url = amd_dc_revenue.discover(
        html_text, "https://ir.amd.com/financial-information/quarterly-results")
    assert detail_url == (
        "https://ir.amd.com/news-events/press-releases/detail/1295/"
        "amd-reports-second-quarter-2026-financial-results")


def test_discover_only_looks_inside_the_first_newest_quarter_block():
    """Two quarterly-results blocks; the SECOND one's earnings-release link
    must never be picked, even though it appears earlier in a naive
    (non-block-scoped) search of the whole document."""
    html_text = (
        '<div class="box quarterly-results" id="newest">'
        '<a href="https://ir.amd.com/detail/NEWEST" '
        'aria-label="Earnings Release Q2 2026 HTML">Earnings Release</a>'
        '</div>'
        '<div class="box quarterly-results" id="older">'
        '<a href="https://ir.amd.com/detail/OLDER" '
        'aria-label="Earnings Release Q1 2026 HTML">Earnings Release</a>'
        '</div>'
    )
    detail_url = amd_dc_revenue.discover(
        html_text, "https://ir.amd.com/financial-information/quarterly-results")
    assert detail_url == "https://ir.amd.com/detail/NEWEST"


# ── amd_dc_revenue.parse ──────────────────────────────────────────────────

def test_parse_extracts_at_least_two_quarters_incl_q2_2026():
    points = amd_dc_revenue.parse(_detail_html())
    assert len(points) >= 2
    by_period = {p["period"]: p for p in points}
    assert "2026-Q2" in by_period
    q2 = by_period["2026-Q2"]
    assert q2["value"] == pytest.approx(6.718)
    assert q2["unit"] == "US$ billions"
    assert q2["publishedAt"] == "2026-08-04"
    assert q2["sourceUrl"].startswith("https://ir.amd.com/")
    assert q2["title"]


def test_parse_second_quarter_is_the_prior_quarter_q1_2026():
    points = amd_dc_revenue.parse(_detail_html())
    by_period = {p["period"]: p for p in points}
    assert "2026-Q1" in by_period
    assert by_period["2026-Q1"]["value"] == pytest.approx(5.775)


def test_parse_raises_parsefailed_on_unrecognized_markup():
    with pytest.raises(ParseFailed):
        amd_dc_revenue.parse("<html><body>not an AMD results page</body></html>")


# ── due_series ─────────────────────────────────────────────────────────────

def test_due_series_quarterly_due_on_earnings_day_when_file_exists(tmp_path):
    series = _series_fixture()
    (tmp_path / "amdDataCenterRevenue.jsonl").write_text(
        '{"indicatorId":"amdDataCenterRevenue","period":"2026-Q1"}\n', encoding="utf-8")
    due = due_series(series, "2026-08-04", ["2026-08-04"], store_dir=str(tmp_path))
    assert [cs.id for cs in due] == ["amdDataCenterRevenue"]


def test_due_series_quarterly_not_due_mid_quarter_when_file_exists(tmp_path):
    series = _series_fixture()
    (tmp_path / "amdDataCenterRevenue.jsonl").write_text(
        '{"indicatorId":"amdDataCenterRevenue","period":"2026-Q1"}\n', encoding="utf-8")
    due = due_series(series, "2026-09-15", ["2026-08-04"], store_dir=str(tmp_path))
    assert due == []


def test_due_series_quarterly_due_when_file_missing_even_off_earnings_window(tmp_path):
    series = _series_fixture()
    due = due_series(series, "2026-09-15", ["2026-08-04"], store_dir=str(tmp_path))
    assert [cs.id for cs in due] == ["amdDataCenterRevenue"]


def test_due_series_never_due_for_fetcher_none_series(tmp_path):
    series = _series_fixture()
    due = due_series(series, "2026-08-04", ["2026-08-04"], store_dir=str(tmp_path))
    ids = {cs.id for cs in due}
    assert "nvdaDataCenterRevenue" not in ids


def test_due_series_never_due_for_monthly_series(tmp_path):
    series = _series_fixture()
    due = due_series(series, "2026-08-04", ["2026-08-04"], store_dir=str(tmp_path))
    ids = {cs.id for cs in due}
    assert "gpuSpotPrice" not in ids


# ── run_fetch: the never-raises + idempotent-append guarantees ────────────

def test_run_fetch_never_raises_when_fetch_html_blows_up(tmp_path):
    series = _series_fixture()

    def _boom(url):
        raise RuntimeError("network is down")

    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                        fetch_html=_boom)

    assert result["fetched"] == []
    failed_ids = [f["id"] for f in result["failed"]]
    assert "amdDataCenterRevenue" in failed_ids
    # The file must be untouched -- no partial/corrupt write on a failed fetch.
    assert not (tmp_path / "amdDataCenterRevenue.jsonl").exists()


def test_run_fetch_reports_failure_dict_shape_and_never_raises_on_parse_failure(tmp_path):
    """The landing fetch + discovery both succeed (garbage HTML still has no
    quarterly-results block, so discovery itself fails first) -- the point is
    the failure surfaces as a normal 'failed' entry, not an exception."""
    series = _series_fixture()
    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                        fetch_html=lambda url: "<html>garbage</html>")
    assert result["fetched"] == []
    assert len(result["failed"]) == 1
    assert result["failed"][0]["id"] == "amdDataCenterRevenue"
    assert "error" in result["failed"][0]


def test_run_fetch_end_to_end_discovers_and_parses_the_real_fixtures(tmp_path):
    """The full two-step path against both real saved fixtures: landing page
    -> discover the real Q2 2026 detail URL -> fetch + parse it -> 6.718."""
    series = _series_fixture()
    calls: list[str] = []
    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                        fetch_html=_stub_fetch_html(calls))

    assert result["failed"] == []
    fetched = {f["id"]: f for f in result["fetched"]}
    assert fetched["amdDataCenterRevenue"]["newPoints"] >= 2

    # Prove the right URL was requested at each step, in order: the landing
    # page first, then the detail page discover() found on it.
    assert calls == [_landing_url(), _real_detail_url()]

    path = tmp_path / "amdDataCenterRevenue.jsonl"
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    by_period = {r["period"]: r for r in rows}
    row = by_period["2026-Q2"]
    assert row["value"] == pytest.approx(6.718)


def test_run_fetch_appends_points_in_the_existing_series_row_format(tmp_path):
    series = _series_fixture()
    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                        fetch_html=_stub_fetch_html())

    assert result["failed"] == []
    fetched = {f["id"]: f for f in result["fetched"]}
    assert fetched["amdDataCenterRevenue"]["newPoints"] >= 2

    path = tmp_path / "amdDataCenterRevenue.jsonl"
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    by_period = {r["period"]: r for r in rows}
    row = by_period["2026-Q2"]
    assert row["indicatorId"] == "amdDataCenterRevenue"
    assert row["value"] == pytest.approx(6.718)
    assert row["unit"] == "US$ billions"
    assert row["publishedAt"] == "2026-08-04"
    assert row["capturedAt"] == "2026-08-04"
    assert row["source"]["url"].startswith("https://ir.amd.com/")
    assert row["source"]["title"]
    assert row["estimateGrade"] is False


def test_run_fetch_append_is_idempotent_across_two_runs(tmp_path):
    series = _series_fixture()
    run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
              fetch_html=_stub_fetch_html())
    path = tmp_path / "amdDataCenterRevenue.jsonl"
    first_rows = path.read_text(encoding="utf-8").splitlines()

    result2 = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                         fetch_html=_stub_fetch_html())

    second_rows = path.read_text(encoding="utf-8").splitlines()
    assert len(second_rows) == len(first_rows)
    periods = [json.loads(l)["period"] for l in second_rows]
    assert len(periods) == len(set(periods))  # no period duplicated
    # Review finding #4: line-count + period-uniqueness alone would still
    # pass if a rerun silently rewrote an existing period's VALUE in place.
    # Assert every pre-existing row is byte-identical after the second run,
    # not just present under the same period label.
    assert second_rows == first_rows
    # a rerun on the same earnings day finds nothing NEW to add
    fetched2 = {f["id"]: f for f in result2["fetched"]}
    assert fetched2["amdDataCenterRevenue"]["newPoints"] == 0


def test_run_fetch_skips_non_due_series(tmp_path):
    series = _series_fixture()
    (tmp_path / "amdDataCenterRevenue.jsonl").write_text(
        '{"indicatorId":"amdDataCenterRevenue","period":"2026-Q1"}\n', encoding="utf-8")
    result = run_fetch(series, "2026-09-15", ["2026-08-04"], str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert result["fetched"] == []
    assert result["failed"] == []
    assert set(result["skipped"]) == set(series)


# ── review finding #1: a corrupt line must never silently wipe history ────

def test_run_fetch_with_a_corrupt_existing_line_fails_and_leaves_file_untouched(tmp_path):
    series = _series_fixture()
    path = tmp_path / "amdDataCenterRevenue.jsonl"
    good_rows = (
        '{"indicatorId":"amdDataCenterRevenue","period":"2025-Q3","value":1.0}\n'
        '{"indicatorId":"amdDataCenterRevenue","period":"2025-Q4","value":1.1}\n'
        '{"indicatorId":"amdDataCenterRevenue","period":"2026-Q1","value":5.775}\n'
    )
    corrupt_line = '{"indicatorId":"amdDataCenterRevenue","period":"2026-Q2 TRUNCATED\n'
    original_content = good_rows + corrupt_line
    path.write_text(original_content, encoding="utf-8")

    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                        fetch_html=_stub_fetch_html())

    # The three genuine historical quarters must NOT have vanished -- the
    # file on disk must be byte-for-byte exactly what it was before the call.
    assert path.read_text(encoding="utf-8") == original_content
    failed_ids = [f["id"] for f in result["failed"]]
    assert "amdDataCenterRevenue" in failed_ids
    assert result["fetched"] == []


# ── review finding #2: run_fetch must never raise, even on a bad argument ─

def test_run_fetch_never_raises_when_series_argument_is_none():
    result = run_fetch(None, "2026-08-04", ["2026-08-04"], "store/series",
                        fetch_html=lambda url: "")
    assert result["fetched"] == []
    assert result["skipped"] == []
    assert result["failed"] and result["failed"][0]["id"] == "*"


def test_run_fetch_never_raises_when_earnings_dates_argument_is_none():
    series = _series_fixture()
    result = run_fetch(series, "2026-08-04", None, "store/series",
                        fetch_html=lambda url: "")
    assert result["fetched"] == []
    assert result["skipped"] == []
    assert result["failed"] and result["failed"][0]["id"] == "*"


def test_run_fetch_never_raises_when_store_dir_argument_is_none():
    series = _series_fixture()
    result = run_fetch(series, "2026-08-04", ["2026-08-04"], None,
                        fetch_html=lambda url: "")
    assert result["fetched"] == []
    assert result["skipped"] == []
    assert result["failed"] and result["failed"][0]["id"] == "*"


def test_run_fetch_never_raises_when_series_values_are_plain_dicts(tmp_path):
    series = {"amdDataCenterRevenue": {"id": "amdDataCenterRevenue",
                                        "cadence": "quarterly", "fetcher": "amd_dc_revenue"}}
    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                        fetch_html=lambda url: "")
    assert result["fetched"] == []
    assert result["skipped"] == []
    assert result["failed"] and result["failed"][0]["id"] == "*"


# ── fix round 2: discovery is now part of the never-raises surface ───────

def test_run_fetch_fails_when_landing_page_has_no_matching_link(tmp_path):
    """Discovery finds a quarterly-results block but no earnings-release
    link inside it -- must land in 'failed', never raise, never write."""
    series = _series_fixture()
    no_link_landing_html = (
        '<div class="box quarterly-results" id="2026-9232-results">'
        '<a href="/slides.pdf" aria-label="Slide Presentation Q2 2026 PDF">Slides</a>'
        '</div>'
    )
    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                        fetch_html=lambda url: no_link_landing_html)
    assert result["fetched"] == []
    failed_ids = [f["id"] for f in result["failed"]]
    assert "amdDataCenterRevenue" in failed_ids
    assert not (tmp_path / "amdDataCenterRevenue.jsonl").exists()


def test_run_fetch_fails_when_detail_fetch_blows_up_after_successful_discovery(tmp_path):
    """Discovery succeeds (real landing fixture, real detail URL found) but
    the SECOND fetch_html call (for the discovered detail URL) blows up --
    must still land in 'failed', never raise, never write."""
    series = _series_fixture()
    landing_url = _landing_url()
    detail_url = _real_detail_url()

    def _fetch(url):
        if url == landing_url:
            return _landing_html()
        if url == detail_url:
            raise RuntimeError("detail page fetch timed out")
        raise AssertionError(f"unexpected fetch_html call for {url!r}")

    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                        fetch_html=_fetch)
    assert result["fetched"] == []
    failed_ids = [f["id"] for f in result["failed"]]
    assert "amdDataCenterRevenue" in failed_ids
    assert "detail page fetch timed out" in result["failed"][0]["error"]
    assert not (tmp_path / "amdDataCenterRevenue.jsonl").exists()

# ── F112(a): staleness guard -- a strictly-older newest parsed quarter must
#    become a loud 'failed' entry, never a quiet success (user-approved
#    2026-08-20: log-and-skip; same-or-newer allowed; empty store vacuous). ──

def _seed_store_row(tmp_path, period: str) -> Path:
    """Write a single minimal series row for amdDataCenterRevenue so the
    store's newest period is `period`. Shape mirrors _row()'s output."""
    path = tmp_path / "amdDataCenterRevenue.jsonl"
    row = {
        "indicatorId": "amdDataCenterRevenue",
        "period": period,
        "value": 9.999,
        "unit": "US$ billions",
        "publishedAt": "2026-11-03",
        "capturedAt": "2026-11-03",
        "source": {"url": "https://example.test", "title": "seed"},
        "estimateGrade": False,
        "note": "seed row for staleness tests",
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path


def test_run_fetch_fails_loudly_when_parsed_quarter_is_older_than_stored(tmp_path):
    series = _series_fixture()
    _seed_store_row(tmp_path, "2026-Q3")

    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                       fetch_html=_stub_fetch_html())

    assert result["fetched"] == []
    assert len(result["failed"]) == 1
    failure = result["failed"][0]
    assert failure["id"] == "amdDataCenterRevenue"
    assert "StalenessViolation" in failure["error"]
    # the loud line must name both quarters so the cycle log is diagnosable
    assert "2026-Q2" in failure["error"]
    assert "2026-Q3" in failure["error"]


def test_staleness_violation_leaves_the_store_file_byte_identical(tmp_path):
    series = _series_fixture()
    path = _seed_store_row(tmp_path, "2026-Q3")
    before = path.read_text(encoding="utf-8")

    run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
              fetch_html=_stub_fetch_html())

    assert path.read_text(encoding="utf-8") == before


def test_equal_newest_quarter_is_allowed_and_backfills_older_periods(tmp_path):
    """Store's newest == parse's newest (2026-Q2): NOT a violation
    (user-approved 2026-08-20: same-or-newer allowed). The fetch succeeds
    and the two older parsed periods backfill as new rows."""
    series = _series_fixture()
    _seed_store_row(tmp_path, "2026-Q2")

    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                       fetch_html=_stub_fetch_html())

    assert result["failed"] == []
    assert result["fetched"] == [{"id": "amdDataCenterRevenue", "newPoints": 2}]


def test_first_ever_fetch_with_no_store_file_passes_the_staleness_check(tmp_path):
    """Missing store file: staleness check is vacuous (user-approved
    2026-08-20); the fetch appends all parsed periods normally."""
    series = _series_fixture()

    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                       fetch_html=_stub_fetch_html())

    assert result["failed"] == []
    assert result["fetched"] == [{"id": "amdDataCenterRevenue", "newPoints": 3}]
