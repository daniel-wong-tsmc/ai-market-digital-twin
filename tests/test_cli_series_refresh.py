# tests/test_cli_series_refresh.py
# NOTE: tests/ is not a package in this repo — never import from another test module;
# each test file carries its own helpers.
import json
import pathlib
from gpu_agent.cli import main
from gpu_agent.series_registry import SeriesRegistry
from gpu_agent.series_store import SeriesPoint, SeriesSource, read_series

REG = "registry/series-indicators.json"

def _point(iid, period, value=1.0, unit="pct_yoy", published=None):
    return SeriesPoint(
        indicatorId=iid, period=period, value=value, unit=unit,
        publishedAt=published or f"{period}-28", capturedAt="2026-07-28",
        source=SeriesSource(url="https://example.com/x", title="t"))

def test_check_writes_gap_report(tmp_path):
    out_file = tmp_path / "gaps.json"
    rc = main(["series-refresh", "--check", "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series"), "--out", str(out_file)])
    assert rc == 0
    gaps = json.loads(out_file.read_text("utf-8"))["gaps"]
    assert gaps and all(g["latestPeriod"] is None for g in gaps)  # empty store: all gap

def test_ingest_exit_0_even_with_rejections(tmp_path, capsys):
    reg = SeriesRegistry.load(REG)
    iid = sorted(reg.specs)[0]
    # 2026-06 is a quarter-end month, so it is valid for either cadence
    good = _point(iid, "2026-06", unit=reg.specs[iid].unit)
    bad = _point(iid, "2026-06", unit="bananas_per_wafer")
    cand = tmp_path / "candidates.json"
    cand.write_text(json.dumps({"candidates": [
        json.loads(good.model_dump_json()), json.loads(bad.model_dump_json())]}), "utf-8")
    rc = main(["series-refresh", "--ingest", str(cand), "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series")])
    assert rc == 0                                   # rejections never block the cycle
    result = json.loads(capsys.readouterr().out)
    assert len(result["written"]) == 1 and len(result["rejected"]) == 1
    assert read_series(tmp_path / "series", iid)[-1].capturedAt == "2026-07-28"

def test_operator_errors_exit_2(tmp_path):
    assert main(["series-refresh", "--as-of", "2026-07-28"]) == 2          # neither flag
    assert main(["series-refresh", "--check", "--ingest", "x",
                 "--as-of", "2026-07-28"]) == 2                            # both flags
    assert main(["series-refresh", "--ingest", str(tmp_path / "absent.json"),
                 "--as-of", "2026-07-28"]) == 2                            # missing file
    assert main(["series-refresh", "--check", "--as-of", "2026-13-99"]) == 2  # bad as-of

def test_check_bad_series_registry_path_exit_2(tmp_path):
    rc = main(["series-refresh", "--check", "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series"),
               "--series-registry", str(tmp_path / "absent-registry.json")])
    assert rc == 2

def test_check_bad_calendar_path_exit_2(tmp_path):
    rc = main(["series-refresh", "--check", "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series"),
               "--calendar", str(tmp_path / "absent-calendar.json")])
    assert rc == 2

def test_check_malformed_calendar_exit_2(tmp_path):
    bad_cal = tmp_path / "calendar.json"
    bad_cal.write_text("not json at all {{{", "utf-8")
    rc = main(["series-refresh", "--check", "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series"),
               "--calendar", str(bad_cal)])
    assert rc == 2

def test_check_calendar_under_covers_registry_exit_2(tmp_path):
    real = json.loads(
        pathlib.Path("registry/series-calendar.json").read_text("utf-8"))
    dropped_key = next(iter(real["seriesCalendar"]))
    del real["seriesCalendar"][dropped_key]
    short_cal = tmp_path / "calendar.json"
    short_cal.write_text(json.dumps(real), "utf-8")
    rc = main(["series-refresh", "--check", "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series"),
               "--calendar", str(short_cal)])
    assert rc == 2


# --- final-review regressions: structural config failures exit 2, not traceback ---

def _cal_arg(tmp_path, text):
    p = tmp_path / "calendar.json"
    p.write_text(text, "utf-8")
    return str(p)

def _reg_arg(tmp_path, text):
    p = tmp_path / "registry.json"
    p.write_text(text, "utf-8")
    return str(p)

def test_calendar_without_series_calendar_key_exit_2(tmp_path):
    rc = main(["series-refresh", "--check", "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series"),
               "--calendar", _cal_arg(tmp_path, "{}")])
    assert rc == 2                                    # was KeyError

def test_calendar_json_is_a_list_exit_2(tmp_path):
    rc = main(["series-refresh", "--check", "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series"),
               "--calendar", _cal_arg(tmp_path, "[]")])
    assert rc == 2                                    # was TypeError

def test_series_registry_entry_not_a_mapping_exit_2(tmp_path):
    rc = main(["series-refresh", "--check", "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series"),
               "--series-registry",
               _reg_arg(tmp_path, json.dumps({"seriesIndicators": {"x": 5}}))])
    assert rc == 2                                    # was TypeError

def test_series_registry_json_is_a_list_exit_2(tmp_path):
    rc = main(["series-refresh", "--check", "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series"),
               "--series-registry", _reg_arg(tmp_path, "[]")])
    assert rc == 2                                    # was AttributeError

def test_ingest_file_with_invalid_utf8_exit_2(tmp_path):
    cand = tmp_path / "candidates.json"
    cand.write_bytes(b'{"candidates": [\xff\xfe]}')
    rc = main(["series-refresh", "--ingest", str(cand), "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series")])
    assert rc == 2                                    # was UnicodeDecodeError

def test_check_out_creates_missing_run_dir(tmp_path):
    """7b writes into work/<run-dir>/ — a missing parent must not traceback."""
    out_file = tmp_path / "work" / "run-dir" / "series-gaps.json"
    rc = main(["series-refresh", "--check", "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series"), "--out", str(out_file)])
    assert rc == 0
    assert json.loads(out_file.read_text("utf-8"))["gaps"]

def test_gap_report_carries_unit_and_latest_construction(tmp_path):
    reg = SeriesRegistry.load(REG)
    out_file = tmp_path / "gaps.json"
    rc = main(["series-refresh", "--check", "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series"), "--out", str(out_file)])
    assert rc == 0
    gaps = json.loads(out_file.read_text("utf-8"))["gaps"]
    for g in gaps:
        assert g["unit"] == reg.specs[g["indicatorId"]].unit
        assert g["latestNote"] is None and g["latestValue"] is None

def test_ingest_rejects_future_period_via_cli(tmp_path, capsys):
    reg = SeriesRegistry.load(REG)
    iid = sorted(reg.specs)[0]
    far = _point(iid, "2099-12", unit=reg.specs[iid].unit, published="2026-07-28")
    cand = tmp_path / "candidates.json"
    cand.write_text(json.dumps(
        {"candidates": [json.loads(far.model_dump_json())]}), "utf-8")
    rc = main(["series-refresh", "--ingest", str(cand), "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series")])
    assert rc == 0                                   # a rejection never blocks the cycle
    result = json.loads(capsys.readouterr().out)
    assert not result["written"] and "future period" in result["rejected"][0]
    assert not (tmp_path / "series").exists()
