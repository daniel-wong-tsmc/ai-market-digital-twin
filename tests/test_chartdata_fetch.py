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

AMD_CALENDAR = {"amd": "2026-08-04"}


def _seed_amd_file(tmp_path) -> None:
    """Give the AMD series an existing store file, so the missing-file rule
    stops forcing it due and the earnings-window logic is what's under test.
    Every window test needs this -- without it the series is due on every
    date for an unrelated reason (this is exactly why F131's window defect
    stayed invisible in production: store/series/amdDataCenterRevenue.jsonl
    does not exist yet, so AMD was permanently due by accident)."""
    (tmp_path / "amdDataCenterRevenue.jsonl").write_text(
        '{"indicatorId":"amdDataCenterRevenue","period":"2026-Q1"}\n', encoding="utf-8")


def test_due_series_quarterly_due_on_earnings_day_when_file_exists(tmp_path):
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    due = due_series(series, "2026-08-04", AMD_CALENDAR, store_dir=str(tmp_path))
    assert [cs.id for cs in due] == ["amdDataCenterRevenue"]


def test_due_series_quarterly_not_due_mid_quarter_when_file_exists(tmp_path):
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    due = due_series(series, "2026-09-15", AMD_CALENDAR, store_dir=str(tmp_path))
    assert due == []


def test_due_series_quarterly_due_when_file_missing_even_off_earnings_window(tmp_path):
    series = _series_fixture()
    due = due_series(series, "2026-09-15", AMD_CALENDAR, store_dir=str(tmp_path))
    assert [cs.id for cs in due] == ["amdDataCenterRevenue"]


def test_due_series_never_due_for_fetcher_none_series(tmp_path):
    series = _series_fixture()
    due = due_series(series, "2026-08-04", AMD_CALENDAR, store_dir=str(tmp_path))
    ids = {cs.id for cs in due}
    assert "nvdaDataCenterRevenue" not in ids


def test_due_series_never_due_for_monthly_series(tmp_path):
    series = _series_fixture()
    due = due_series(series, "2026-08-04", AMD_CALENDAR, store_dir=str(tmp_path))
    ids = {cs.id for cs in due}
    assert "gpuSpotPrice" not in ids


# ── F131 defect B: the window is forward-only, print day E .. E+14 ─────────
#
# The old window was symmetric +/-3 days, so a series with an existing store
# file went not-due four days after its own print -- in the exact week the
# source page carries fresh numbers -- and was "due" for three days BEFORE
# the print, when there is by definition nothing new to fetch. User ruling
# 2026-08-31: forward-only, E through E+14.

def test_due_series_still_due_five_days_after_the_print(tmp_path):
    """The literal F131 symptom, as observed live on 2026-08-31: five days
    past the print, in the week the source has fresh numbers. Under the old
    +/-3 window this returned [] -- this is the regression test for it."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    due = due_series(series, "2026-08-09", AMD_CALENDAR, store_dir=str(tmp_path))
    assert [cs.id for cs in due] == ["amdDataCenterRevenue"]


def test_due_series_due_on_the_last_day_of_the_window(tmp_path):
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    due = due_series(series, "2026-08-18", AMD_CALENDAR, store_dir=str(tmp_path))
    assert [cs.id for cs in due] == ["amdDataCenterRevenue"]


def test_due_series_not_due_the_day_after_the_window_closes(tmp_path):
    """Paired with a positive control on the last in-window day. On its own an
    empty result proves nothing -- a build that ignored the calendar entirely
    would also return [] here (review finding). The pair pins the boundary."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    assert [cs.id for cs in due_series(series, "2026-08-18", AMD_CALENDAR,
                                        store_dir=str(tmp_path))] \
        == ["amdDataCenterRevenue"]
    assert due_series(series, "2026-08-19", AMD_CALENDAR,
                      store_dir=str(tmp_path)) == []


def test_due_series_not_due_the_day_before_the_print(tmp_path):
    """Forward-only: nothing has been published yet, so there is nothing a
    fetch could pick up. The old symmetric window burned three of its seven
    days here. Paired with a positive control on the print day itself."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    assert due_series(series, "2026-08-03", AMD_CALENDAR,
                      store_dir=str(tmp_path)) == []
    assert [cs.id for cs in due_series(series, "2026-08-04", AMD_CALENDAR,
                                        store_dir=str(tmp_path))] \
        == ["amdDataCenterRevenue"]


# ── F131 defect C: each series is scoped to its OWN company's print ────────
#
# The calendar used to arrive as a bare list of dates with the company names
# stripped off, so every quarterly series was tested against every company's
# print date. User ruling 2026-08-31: scope via an explicit `earningsKey` on
# the registry entry, matched against the manifest's earningsDates keys.

def test_due_series_ignores_another_companys_earnings_date(tmp_path):
    """AMD's series must NOT wake up during NVIDIA's earnings week.

    Paired with a positive control: the SAME as-of date, three days after a
    print, does make AMD due when the print is AMD's own. Without that pair an
    empty result could just mean the calendar was ignored."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    assert due_series(series, "2026-08-29", {"nvidia": "2026-08-26"},
                      store_dir=str(tmp_path)) == []
    assert [cs.id for cs in due_series(series, "2026-08-29", {"amd": "2026-08-26"},
                                        store_dir=str(tmp_path))] \
        == ["amdDataCenterRevenue"]


def test_due_series_picks_its_own_date_out_of_a_multi_company_calendar(tmp_path):
    """Both companies in the calendar: AMD is due in AMD's window and quiet
    in NVIDIA's, driven entirely by its own earningsKey."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    calendar = {"nvidia": "2026-08-26", "amd": "2026-08-04"}

    in_amd_window = due_series(series, "2026-08-09", calendar, store_dir=str(tmp_path))
    assert [cs.id for cs in in_amd_window] == ["amdDataCenterRevenue"]

    in_nvda_window = due_series(series, "2026-08-29", calendar, store_dir=str(tmp_path))
    assert in_nvda_window == []


def test_due_series_is_not_due_when_the_calendar_has_no_entry(tmp_path):
    """`due_series` answers only "should I fetch this now?", and the answer is
    still no -- there is no print date to schedule against. What CHANGED under
    ruling Q5 is that this no longer passes silently: run_fetch reports it in
    the staleCalendar bucket (see the Q5 tests below). Paired with a positive
    control so it can't pass merely because the calendar was never consulted."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    assert due_series(series, "2026-08-09", {}, store_dir=str(tmp_path)) == []
    assert [cs.id for cs in due_series(series, "2026-08-09", AMD_CALENDAR,
                                        store_dir=str(tmp_path))] \
        == ["amdDataCenterRevenue"]


def test_due_series_is_not_due_on_an_unparseable_date_in_the_calendar(tmp_path):
    """A junk date must not crash the daily run, and must not be treated as a
    window either. Reported via staleCalendar rather than silently, per Q5."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    assert due_series(series, "2026-08-09", {"amd": "not-a-date"},
                      store_dir=str(tmp_path)) == []
    assert [cs.id for cs in due_series(series, "2026-08-09", AMD_CALENDAR,
                                        store_dir=str(tmp_path))] \
        == ["amdDataCenterRevenue"]


# ── run_fetch: the never-raises + idempotent-append guarantees ────────────

def test_run_fetch_never_raises_when_fetch_html_blows_up(tmp_path):
    series = _series_fixture()

    def _boom(url):
        raise RuntimeError("network is down")

    result = run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
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
    result = run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
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
    result = run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
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
    result = run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
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
    run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
              fetch_html=_stub_fetch_html())
    path = tmp_path / "amdDataCenterRevenue.jsonl"
    first_rows = path.read_text(encoding="utf-8").splitlines()

    result2 = run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
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
    """as_of sits BEFORE AMD's print, so the window simply hasn't opened --
    the routine case. (Past E+14 it would be staleCalendar instead; see the Q5
    tests below.)"""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    result = run_fetch(series, "2026-08-01", AMD_CALENDAR, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert result["fetched"] == []
    assert result["failed"] == []
    # nvdaDataCenterRevenue is no longer lumped in with "not due this week" --
    # see the notFetchable tests below.
    assert set(result["skipped"]) == {"amdDataCenterRevenue", "gpuSpotPrice"}


# ── F131 defect: "no fetcher wired up" must not hide inside 'skipped' ──────
#
# A series with no fetcher can NEVER be fetched, but it used to be reported
# in the same bucket as "not due this week". That is why nvdaDataCenterRevenue
# read as a scheduling hiccup for three consecutive cycles instead of as a
# missing fetcher. User ruling 2026-08-31: give it its own bucket.

def test_run_fetch_reports_a_fetcherless_quarterly_series_as_not_fetchable(tmp_path):
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    result = run_fetch(series, "2026-09-15", AMD_CALENDAR, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert result["notFetchable"] == ["nvdaDataCenterRevenue"]
    assert "nvdaDataCenterRevenue" not in result["skipped"]


def test_run_fetch_reports_not_fetchable_even_inside_the_earnings_window(tmp_path):
    """The live F131 symptom: NVIDIA printed on 2026-08-26 and the series was
    still reported as merely 'skipped' five days later. It must now be
    reported as not fetchable at all, on any date."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    result = run_fetch(series, "2026-08-31", {"nvidia": "2026-08-26"}, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert result["notFetchable"] == ["nvdaDataCenterRevenue"]
    assert "nvdaDataCenterRevenue" not in result["skipped"]


def test_run_fetch_leaves_a_monthly_series_in_skipped_not_not_fetchable(tmp_path):
    """gpuSpotPrice has no fetcher here either, but it is not broken -- it is
    maintained end to end by price-sync (gpu_agent/price_local.py). Only a
    series this module OWNS and cannot fetch is a problem worth flagging."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    result = run_fetch(series, "2026-09-15", AMD_CALENDAR, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert "gpuSpotPrice" in result["skipped"]
    assert "gpuSpotPrice" not in result["notFetchable"]


@pytest.mark.parametrize("as_of, expected_bucket", [
    # before the print: the window has not opened, AMD sits in 'skipped'
    ("2026-08-01", "skipped"),
    # inside AMD's own window: AMD moves into 'fetched'
    ("2026-08-09", "fetched"),
    # past E+14 with a store file: AMD moves into 'staleCalendar'
    ("2026-09-15", "staleCalendar"),
])
def test_run_fetch_every_registry_series_lands_in_exactly_one_bucket(
        tmp_path, as_of, expected_bucket):
    """No series may be double-counted or silently dropped between the five
    buckets -- the property that makes the summary trustworthy at a glance.

    Parametrised across all three states one series can be in on purpose: with
    nothing ever due, 'fetched' and 'failed' are both empty and the test would
    only ever check skipped + notFetchable, which is close to tautological
    (review finding). These cases walk one series through three buckets."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    result = run_fetch(series, as_of, AMD_CALENDAR, str(tmp_path),
                        fetch_html=_stub_fetch_html())

    buckets = {
        "fetched": [f["id"] for f in result["fetched"]],
        "failed": [f["id"] for f in result["failed"]],
        "skipped": list(result["skipped"]),
        "notFetchable": list(result["notFetchable"]),
        "staleCalendar": list(result["staleCalendar"]),
    }
    reported = [sid for ids in buckets.values() for sid in ids]
    assert sorted(reported) == sorted(series)
    assert len(reported) == len(set(reported))
    # and the AMD series really did move, rather than the totals just adding up
    assert "amdDataCenterRevenue" in buckets[expected_bucket]
    assert result["notFetchable"] == ["nvdaDataCenterRevenue"]


# ── F131 Q5: an unusable earnings calendar is reported, never a quiet skip ──
#
# The scheduler now correctly asks "has THIS company reported recently?" -- but
# nothing keeps the calendar current. It is hand-edited, and nothing in the repo
# refreshes it. Once a series' store file exists, a missing/unparseable/stale
# calendar entry made it quietly never-due again, forever, looking exactly like
# a routine skip. That is this lane's own headline bug class in a new place.
# User ruling 2026-08-31: reportable condition, not a skip.
#
# It gets its own bucket rather than joining notFetchable because the two need
# DIFFERENT actions: notFetchable means "somebody must build a fetcher",
# staleCalendar means "somebody must update the earnings date". Merging them
# would hide which one you are looking at.

def test_run_fetch_reports_a_stale_calendar_entry(tmp_path):
    """The live 2026-08-31 case: AMD printed 2026-08-04, so its window closed
    on 08-18. With a store file present the series would otherwise sit in
    'skipped' forever, indistinguishable from "not due this week"."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    result = run_fetch(series, "2026-08-31", AMD_CALENDAR, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert result["staleCalendar"] == ["amdDataCenterRevenue"]
    assert "amdDataCenterRevenue" not in result["skipped"]


def test_run_fetch_reports_a_calendar_with_no_entry_for_this_series(tmp_path):
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    result = run_fetch(series, "2026-08-09", {}, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert result["staleCalendar"] == ["amdDataCenterRevenue"]


def test_run_fetch_reports_an_unparseable_calendar_date(tmp_path):
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    result = run_fetch(series, "2026-08-09", {"amd": "not-a-date"}, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert result["staleCalendar"] == ["amdDataCenterRevenue"]


def test_run_fetch_before_the_print_is_a_routine_skip_not_a_stale_calendar(tmp_path):
    """The window simply has not opened yet. The calendar is fine and nobody
    needs to do anything, so this must stay an ordinary skip -- otherwise the
    new bucket cries wolf for most of every quarter."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    result = run_fetch(series, "2026-08-01", AMD_CALENDAR, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert result["staleCalendar"] == []
    assert "amdDataCenterRevenue" in result["skipped"]


def test_run_fetch_inside_the_window_is_not_a_stale_calendar(tmp_path):
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    result = run_fetch(series, "2026-08-09", AMD_CALENDAR, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert result["staleCalendar"] == []
    assert [f["id"] for f in result["fetched"]] == ["amdDataCenterRevenue"]


def test_run_fetch_a_due_series_is_never_also_reported_stale(tmp_path):
    """A missing store file forces the series due even with a stale calendar.
    It is being fetched right now, so it is not waiting on anybody."""
    series = _series_fixture()
    result = run_fetch(series, "2026-08-31", AMD_CALENDAR, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert result["staleCalendar"] == []
    assert [f["id"] for f in result["fetched"]] == ["amdDataCenterRevenue"]


def test_run_fetch_no_fetcher_beats_stale_calendar(tmp_path):
    """nvdaDataCenterRevenue has BOTH problems on 2026-08-31 (no fetcher, and
    a calendar entry whose window closed on 09-09). Building a fetcher is the
    prerequisite, so it must report as notFetchable and appear nowhere else."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    result = run_fetch(series, "2026-09-30", AMD_CALENDAR, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert result["notFetchable"] == ["nvdaDataCenterRevenue"]
    assert "nvdaDataCenterRevenue" not in result["staleCalendar"]


def test_run_fetch_monthly_series_are_never_reported_stale(tmp_path):
    """gpuSpotPrice is not scheduled off an earnings date at all."""
    series = _series_fixture()
    _seed_amd_file(tmp_path)
    result = run_fetch(series, "2026-08-31", AMD_CALENDAR, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert "gpuSpotPrice" not in result["staleCalendar"]
    assert "gpuSpotPrice" in result["skipped"]


# ── F131 Q6: an unparseable --as-of is an operator error, not a quiet no-op ──

def test_run_fetch_fails_loudly_on_an_unparseable_as_of(tmp_path):
    """It used to return [] with nothing recorded, so a whole cycle that did
    nothing at all printed a clean-looking summary of routine skips. Same
    principle as the non-mapping calendar guard: a config error must surface."""
    series = _series_fixture()
    result = run_fetch(series, "not-a-date", AMD_CALENDAR, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert result["fetched"] == []
    assert result["skipped"] == []
    assert result["notFetchable"] == []
    assert result["staleCalendar"] == []
    assert result["failed"] and result["failed"][0]["id"] == "*"
    assert "as_of_date" in result["failed"][0]["error"]


def test_due_series_raises_on_an_unparseable_as_of(tmp_path):
    series = _series_fixture()
    with pytest.raises(ValueError, match="as_of_date"):
        due_series(series, "2026-13-45", AMD_CALENDAR, store_dir=str(tmp_path))


def test_run_fetch_buckets_use_the_series_id_not_the_dict_key(tmp_path):
    """The four-bucket partition must not rest on the caller's dict being
    keyed by series id. A hand-built dict with a mismatched key used to put one
    series in two buckets at once (review finding)."""
    series = _series_fixture()
    remapped = {"WRONGKEY": series["nvdaDataCenterRevenue"]}
    result = run_fetch(remapped, "2026-09-15", AMD_CALENDAR, str(tmp_path),
                        fetch_html=_stub_fetch_html())
    assert result["notFetchable"] == ["nvdaDataCenterRevenue"]
    assert result["skipped"] == []


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

    result = run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
                        fetch_html=_stub_fetch_html())

    # The three genuine historical quarters must NOT have vanished -- the
    # file on disk must be byte-for-byte exactly what it was before the call.
    assert path.read_text(encoding="utf-8") == original_content
    failed_ids = [f["id"] for f in result["failed"]]
    assert "amdDataCenterRevenue" in failed_ids
    assert result["fetched"] == []


# ── review finding #2: run_fetch must never raise, even on a bad argument ─

def test_run_fetch_never_raises_when_series_argument_is_none():
    result = run_fetch(None, "2026-08-04", AMD_CALENDAR, "store/series",
                        fetch_html=lambda url: "")
    assert result["fetched"] == []
    assert result["skipped"] == []
    assert result["notFetchable"] == []
    assert result["staleCalendar"] == []
    assert result["failed"] and result["failed"][0]["id"] == "*"


def test_run_fetch_never_raises_when_earnings_dates_argument_is_none():
    series = _series_fixture()
    result = run_fetch(series, "2026-08-04", None, "store/series",
                        fetch_html=lambda url: "")
    assert result["fetched"] == []
    assert result["skipped"] == []
    assert result["notFetchable"] == []
    assert result["staleCalendar"] == []
    assert result["failed"] and result["failed"][0]["id"] == "*"


def test_run_fetch_never_raises_but_fails_loudly_on_the_old_list_calendar_shape(tmp_path):
    """F131: the calendar used to be a bare list of dates. If some caller
    still passes one, it must fail LOUDLY -- a list silently matches no
    company key, which would leave every quarterly series quietly never-due
    and recreate the very bug this lane fixed."""
    series = _series_fixture()
    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                        fetch_html=lambda url: "")
    assert result["fetched"] == []
    assert result["skipped"] == []
    assert result["notFetchable"] == []
    assert result["staleCalendar"] == []
    assert result["failed"] and result["failed"][0]["id"] == "*"
    assert "mapping" in result["failed"][0]["error"]


def test_run_fetch_never_raises_when_store_dir_argument_is_none():
    series = _series_fixture()
    result = run_fetch(series, "2026-08-04", AMD_CALENDAR, None,
                        fetch_html=lambda url: "")
    assert result["fetched"] == []
    assert result["skipped"] == []
    assert result["notFetchable"] == []
    assert result["staleCalendar"] == []
    assert result["failed"] and result["failed"][0]["id"] == "*"


def test_run_fetch_never_raises_when_series_values_are_plain_dicts(tmp_path):
    series = {"amdDataCenterRevenue": {"id": "amdDataCenterRevenue",
                                        "cadence": "quarterly", "fetcher": "amd_dc_revenue"}}
    result = run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
                        fetch_html=lambda url: "")
    assert result["fetched"] == []
    assert result["skipped"] == []
    assert result["notFetchable"] == []
    assert result["staleCalendar"] == []
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
    result = run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
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

    result = run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
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

    result = run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
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

    run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
              fetch_html=_stub_fetch_html())

    assert path.read_text(encoding="utf-8") == before


def test_equal_newest_quarter_is_allowed_and_backfills_older_periods(tmp_path):
    """Store's newest == parse's newest (2026-Q2): NOT a violation
    (user-approved 2026-08-20: same-or-newer allowed). The fetch succeeds
    and the two older parsed periods backfill as new rows."""
    series = _series_fixture()
    _seed_store_row(tmp_path, "2026-Q2")

    result = run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
                       fetch_html=_stub_fetch_html())

    assert result["failed"] == []
    assert result["fetched"] == [{"id": "amdDataCenterRevenue", "newPoints": 2}]


def test_first_ever_fetch_with_no_store_file_passes_the_staleness_check(tmp_path):
    """Missing store file: staleness check is vacuous (user-approved
    2026-08-20); the fetch appends all parsed periods normally."""
    series = _series_fixture()

    result = run_fetch(series, "2026-08-04", AMD_CALENDAR, str(tmp_path),
                       fetch_html=_stub_fetch_html())

    assert result["failed"] == []
    assert result["fetched"] == [{"id": "amdDataCenterRevenue", "newPoints": 3}]
