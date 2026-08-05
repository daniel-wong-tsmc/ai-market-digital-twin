"""F110 Task 4: chart-data fetch framework + AMD data-center revenue fetcher.

The single most important guarantee tested here: run_fetch NEVER raises,
even when fetch_html blows up -- this code runs inside the unattended daily
pipeline, and a broken web page must degrade to "no new data", never to a
crashed run. The second guarantee: appends are idempotent -- running the
same fetch twice must never duplicate a period in the series file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gpu_agent.chartdata.fetch import ParseFailed, due_series, run_fetch
from gpu_agent.chartdata.fetchers import amd_dc_revenue
from gpu_agent.chartdata.registry import ChartSeries, load_chart_series

FIXTURE_PATH = "fixtures/chartdata/amd-ir-q2-2026.html"
REGISTRY_PATH = "registry/chart-series.json"


def _amd_html() -> str:
    return Path(FIXTURE_PATH).read_text(encoding="utf-8")


# ── amd_dc_revenue.parse ──────────────────────────────────────────────────

def test_parse_extracts_at_least_two_quarters_incl_q2_2026():
    points = amd_dc_revenue.parse(_amd_html())
    assert len(points) >= 2
    by_period = {p["period"]: p for p in points}
    assert "2026-Q2" in by_period
    q2 = by_period["2026-Q2"]
    assert q2["value"] == pytest.approx(6.718)
    assert q2["unit"] == "USD bn"
    assert q2["publishedAt"] == "2026-08-04"
    assert q2["sourceUrl"].startswith("https://ir.amd.com/")
    assert q2["title"]


def test_parse_second_quarter_is_the_prior_quarter_q1_2026():
    points = amd_dc_revenue.parse(_amd_html())
    by_period = {p["period"]: p for p in points}
    assert "2026-Q1" in by_period
    assert by_period["2026-Q1"]["value"] == pytest.approx(5.775)


def test_parse_raises_parsefailed_on_unrecognized_markup():
    with pytest.raises(ParseFailed):
        amd_dc_revenue.parse("<html><body>not an AMD results page</body></html>")


# ── due_series ─────────────────────────────────────────────────────────────

def _series_fixture() -> dict[str, ChartSeries]:
    return load_chart_series(REGISTRY_PATH)


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
    series = _series_fixture()
    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                        fetch_html=lambda url: "<html>garbage</html>")
    assert result["fetched"] == []
    assert len(result["failed"]) == 1
    assert result["failed"][0]["id"] == "amdDataCenterRevenue"
    assert "error" in result["failed"][0]


def test_run_fetch_appends_points_in_the_existing_series_row_format(tmp_path):
    series = _series_fixture()
    result = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                        fetch_html=lambda url: _amd_html())

    assert result["failed"] == []
    fetched = {f["id"]: f for f in result["fetched"]}
    assert fetched["amdDataCenterRevenue"]["newPoints"] >= 2

    path = tmp_path / "amdDataCenterRevenue.jsonl"
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    by_period = {r["period"]: r for r in rows}
    row = by_period["2026-Q2"]
    assert row["indicatorId"] == "amdDataCenterRevenue"
    assert row["value"] == pytest.approx(6.718)
    assert row["unit"] == "USD bn"
    assert row["publishedAt"] == "2026-08-04"
    assert row["capturedAt"] == "2026-08-04"
    assert row["source"]["url"].startswith("https://ir.amd.com/")
    assert row["source"]["title"]
    assert row["estimateGrade"] is False


def test_run_fetch_append_is_idempotent_across_two_runs(tmp_path):
    series = _series_fixture()
    run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
              fetch_html=lambda url: _amd_html())
    path = tmp_path / "amdDataCenterRevenue.jsonl"
    first_rows = path.read_text(encoding="utf-8").splitlines()

    result2 = run_fetch(series, "2026-08-04", ["2026-08-04"], str(tmp_path),
                         fetch_html=lambda url: _amd_html())

    second_rows = path.read_text(encoding="utf-8").splitlines()
    assert len(second_rows) == len(first_rows)
    periods = [json.loads(l)["period"] for l in second_rows]
    assert len(periods) == len(set(periods))  # no period duplicated
    # a rerun on the same earnings day finds nothing NEW to add
    fetched2 = {f["id"]: f for f in result2["fetched"]}
    assert fetched2["amdDataCenterRevenue"]["newPoints"] == 0


def test_run_fetch_skips_non_due_series(tmp_path):
    series = _series_fixture()
    (tmp_path / "amdDataCenterRevenue.jsonl").write_text(
        '{"indicatorId":"amdDataCenterRevenue","period":"2026-Q1"}\n', encoding="utf-8")
    result = run_fetch(series, "2026-09-15", ["2026-08-04"], str(tmp_path),
                        fetch_html=lambda url: _amd_html())
    assert result["fetched"] == []
    assert result["failed"] == []
    assert set(result["skipped"]) == set(series)
