# tests/test_cli_series_refresh.py
# NOTE: tests/ is not a package in this repo — never import from another test module;
# each test file carries its own helpers.
import datetime
import json
from gpu_agent.cli import main
from gpu_agent.series_registry import SeriesRegistry
from gpu_agent.series_store import SeriesPoint, SeriesSource, read_series

REG = "registry/series-indicators.json"

def _point(iid, period, value=1.0, unit="pct_yoy", published=None):
    return SeriesPoint(
        indicatorId=iid, period=period, value=value, unit=unit,
        publishedAt=published or f"{period}-28", capturedAt="2026-07-28",
        source=SeriesSource(url="https://example.com/x", title="t"))

def test_check_writes_gap_report(tmp_path, capsys):
    out_file = tmp_path / "gaps.json"
    rc = main(["series-refresh", "--check", "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series"), "--out", str(out_file)])
    assert rc == 0
    gaps = json.loads(out_file.read_text("utf-8"))["gaps"]
    assert gaps and all(g["latestPeriod"] is None for g in gaps)  # empty store: all gap

def test_ingest_exit_0_even_with_rejections(tmp_path, capsys):
    reg = SeriesRegistry.load(REG)
    iid = sorted(reg.specs)[0]
    good = _point(iid, "2026-07", unit=reg.specs[iid].unit)
    bad = _point(iid, "2026-07", unit="bananas_per_wafer")
    cand = tmp_path / "candidates.json"
    cand.write_text(json.dumps({"candidates": [
        json.loads(good.model_dump_json()), json.loads(bad.model_dump_json())]}), "utf-8")
    rc = main(["series-refresh", "--ingest", str(cand), "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series")])
    assert rc == 0                                   # rejections never block the cycle
    result = json.loads(capsys.readouterr().out)
    assert len(result["written"]) == 1 and len(result["rejected"]) == 1
    assert read_series(tmp_path / "series", iid)[-1].capturedAt == "2026-07-28"

def test_operator_errors_exit_2(tmp_path, capsys):
    assert main(["series-refresh", "--as-of", "2026-07-28"]) == 2          # neither flag
    assert main(["series-refresh", "--check", "--ingest", "x",
                 "--as-of", "2026-07-28"]) == 2                            # both flags
    assert main(["series-refresh", "--ingest", str(tmp_path / "absent.json"),
                 "--as-of", "2026-07-28"]) == 2                            # missing file
    assert main(["series-refresh", "--check", "--as-of", "2026-13-99"]) == 2  # bad as-of
