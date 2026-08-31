"""F110 Task 4 (review finding #3): CLI coverage for `gpu-agent chart-fetch`.

Zero tests exercised this verb before this file existed -- "exit code 0 even
when fetches fail" is an explicit requirement with no guard, so a refactor
that returned 1 on a fetch failure would have shipped green. These tests
invoke the real `main()` entry point, the same way tests/test_coverage_record.py
does for `coverage-record`.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from gpu_agent.cli import main

REGISTRY = {
    "series": [
        {
            "id": "amdDataCenterRevenue",
            "name": "AMD data center revenue",
            "sourceName": "AMD investor relations",
            "sourceUrl": "https://ir.amd.com/financial-information/quarterly-results",
            "cadence": "quarterly",
            "quality": "hard-fact",
            "topicTags": ["amdDataCenter", "amd"],
            "form": "columns",
            "unit": "USD bn",
            "fetcher": "amd_dc_revenue",
            "earningsKey": "amd",
        },
    ]
}

MANIFEST = {
    "version": "1.0",
    "categoryId": "chips.merchant-gpu",
    "asOf": "2026-08",
    "earningsDates": {"amd": "2026-08-04"},
}


def _write_json(path: pathlib.Path, payload: dict) -> str:
    path.write_text(json.dumps(payload), "utf-8")
    return str(path)


def test_chart_fetch_exits_zero_and_prints_json_when_a_fetch_fails(tmp_path, capsys):
    """The registry's real sourceUrl is a live https:// page this test must never
    touch. Point the registry copy at a URL urllib rejects instantly (no network
    I/O at all -- ValueError: unknown url type) so the fetch deterministically
    fails, and assert the verb still exits 0 with the failure visible in the
    printed JSON summary."""
    registry = json.loads(json.dumps(REGISTRY))
    registry["series"][0]["sourceUrl"] = "not-a-valid-url"
    registry_path = _write_json(tmp_path / "chart-series.json", registry)
    manifest_path = _write_json(tmp_path / "manifest.json", MANIFEST)
    store = tmp_path / "store"

    rc = main(["chart-fetch", "--category", "chips.merchant-gpu", "--as-of", "2026-08-04",
               "--store", str(store), "--manifest", manifest_path,
               "--registry", registry_path])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["fetched"] == []
    failed_ids = [f["id"] for f in out["failed"]]
    assert "amdDataCenterRevenue" in failed_ids
    # a failed fetch must never leave a partial/corrupt series file behind
    assert not (store / "series" / "amdDataCenterRevenue.jsonl").exists()


def test_chart_fetch_prints_the_summary_dict_as_json(tmp_path, capsys):
    """No test in this file may reach the real network (the CLI's default
    fetch_html is a bare urllib call with no injection point) -- pre-seed the
    series file and pick an --as-of BEFORE the earnings date, so the window has
    not opened, nothing is due, and run_fetch never attempts a fetch at all.
    (Before the print rather than long after it: long after is now the
    staleCalendar case, which is a different bucket.) This still proves the
    verb prints run_fetch's exact summary shape as JSON."""
    registry_path = _write_json(tmp_path / "chart-series.json", REGISTRY)
    manifest_path = _write_json(tmp_path / "manifest.json", MANIFEST)
    store = tmp_path / "store"
    series_dir = store / "series"
    series_dir.mkdir(parents=True)
    (series_dir / "amdDataCenterRevenue.jsonl").write_text(
        '{"indicatorId":"amdDataCenterRevenue","period":"2026-Q1","value":5.775}\n',
        encoding="utf-8")

    rc = main(["chart-fetch", "--category", "chips.merchant-gpu", "--as-of", "2026-08-01",
               "--store", str(store), "--manifest", manifest_path,
               "--registry", registry_path])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    # Exact shape of run_fetch's return value, printed verbatim as JSON.
    assert set(out) == {"fetched", "failed", "skipped", "notFetchable", "staleCalendar"}
    assert out["fetched"] == []
    assert out["failed"] == []
    assert out["skipped"] == ["amdDataCenterRevenue"]
    assert out["notFetchable"] == []
    assert out["staleCalendar"] == []


def test_chart_fetch_does_not_wake_a_series_on_another_companys_earnings_date(
        tmp_path, capsys):
    """F131 defect C, end to end through the CLI. The manifest carries both
    companies' print dates; --as-of sits three days after NVIDIA's print and
    well outside AMD's. AMD's series must stay quiet.

    Before the fix the CLI handed run_fetch `earningsDates.values()` -- a bare
    list with the company names stripped off -- so AMD matched NVIDIA's date
    and would have been fetched here. No network is reachable in this test, so
    a regression shows up as a 'failed' entry rather than a silent pass."""
    # sourceUrl is deliberately un-fetchable: if this assertion ever regresses,
    # the CLI must fail fast rather than make a real 20-second request to
    # ir.amd.com. No test in this file may reach the live network.
    registry = json.loads(json.dumps(REGISTRY))
    registry["series"][0]["sourceUrl"] = "not-a-valid-url"
    registry_path = _write_json(tmp_path / "chart-series.json", registry)
    # AMD's print is in the FUTURE here, so its own window has not opened and
    # its calendar entry is perfectly usable. That isolates the one thing under
    # test: AMD must not be woken by NVIDIA's print. (An AMD date in the past
    # would land it in staleCalendar and prove nothing about scoping.)
    manifest = {**MANIFEST,
                "earningsDates": {"amd": "2026-09-20", "nvidia": "2026-08-26"}}
    manifest_path = _write_json(tmp_path / "manifest.json", manifest)
    store = tmp_path / "store"
    series_dir = store / "series"
    series_dir.mkdir(parents=True)
    (series_dir / "amdDataCenterRevenue.jsonl").write_text(
        '{"indicatorId":"amdDataCenterRevenue","period":"2026-Q1","value":5.775}\n',
        encoding="utf-8")

    rc = main(["chart-fetch", "--category", "chips.merchant-gpu", "--as-of", "2026-08-29",
               "--store", str(store), "--manifest", manifest_path,
               "--registry", registry_path])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["fetched"] == []
    assert out["failed"] == []
    assert out["skipped"] == ["amdDataCenterRevenue"]


def test_chart_fetch_is_due_five_days_after_its_own_print(tmp_path, capsys):
    """F131 defect B, end to end: five days past AMD's own print the series
    must be DUE. Under the old +/-3 window it was already out of the window.
    The registry copy points at an unfetchable URL, so 'due' shows up as a
    failed fetch attempt -- which is the proof the scheduler tried at all."""
    registry = json.loads(json.dumps(REGISTRY))
    registry["series"][0]["sourceUrl"] = "not-a-valid-url"
    registry_path = _write_json(tmp_path / "chart-series.json", registry)
    manifest_path = _write_json(tmp_path / "manifest.json", MANIFEST)
    store = tmp_path / "store"
    series_dir = store / "series"
    series_dir.mkdir(parents=True)
    (series_dir / "amdDataCenterRevenue.jsonl").write_text(
        '{"indicatorId":"amdDataCenterRevenue","period":"2026-Q1","value":5.775}\n',
        encoding="utf-8")

    rc = main(["chart-fetch", "--category", "chips.merchant-gpu", "--as-of", "2026-08-09",
               "--store", str(store), "--manifest", manifest_path,
               "--registry", registry_path])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["skipped"] == []
    assert [f["id"] for f in out["failed"]] == ["amdDataCenterRevenue"]


def test_chart_fetch_reports_a_stale_earnings_calendar(tmp_path, capsys):
    """F131 Q5, end to end. The manifest is hand-edited and nothing refreshes
    it; AMD's recorded print is 2026-08-04, so by 2026-09-15 its window closed
    a month ago. With a store file present the series would otherwise sit in
    'skipped' forever, looking exactly like "not due this week"."""
    registry_path = _write_json(tmp_path / "chart-series.json", REGISTRY)
    manifest_path = _write_json(tmp_path / "manifest.json", MANIFEST)
    store = tmp_path / "store"
    series_dir = store / "series"
    series_dir.mkdir(parents=True)
    (series_dir / "amdDataCenterRevenue.jsonl").write_text(
        '{"indicatorId":"amdDataCenterRevenue","period":"2026-Q1","value":5.775}\n',
        encoding="utf-8")

    rc = main(["chart-fetch", "--category", "chips.merchant-gpu", "--as-of", "2026-09-15",
               "--store", str(store), "--manifest", manifest_path,
               "--registry", registry_path])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["staleCalendar"] == ["amdDataCenterRevenue"]
    assert out["skipped"] == []


def test_chart_fetch_rejects_an_unparseable_as_of_at_the_argument_level(tmp_path):
    """F131 Q6, CLI half. The verb never even reaches run_fetch with a bad
    date: argparse rejects it first and exits non-zero. Pinned here because it
    is what makes the CLI path safe, and because it documents why the Q6 guard
    inside run_fetch is for direct/library callers rather than this one."""
    registry_path = _write_json(tmp_path / "chart-series.json", REGISTRY)
    manifest_path = _write_json(tmp_path / "manifest.json", MANIFEST)

    with pytest.raises(SystemExit) as exc:
        main(["chart-fetch", "--category", "chips.merchant-gpu", "--as-of", "nonsense",
              "--store", str(tmp_path / "store"), "--manifest", manifest_path,
              "--registry", registry_path])
    assert exc.value.code != 0


def test_chart_fetch_errors_loudly_on_a_missing_manifest(tmp_path, capsys):
    registry_path = _write_json(tmp_path / "chart-series.json", REGISTRY)
    store = tmp_path / "store"

    rc = main(["chart-fetch", "--category", "chips.merchant-gpu", "--as-of", "2026-08-04",
               "--store", str(store), "--manifest", str(tmp_path / "does-not-exist.json"),
               "--registry", registry_path])

    assert rc == 1
    assert "error" in capsys.readouterr().err
