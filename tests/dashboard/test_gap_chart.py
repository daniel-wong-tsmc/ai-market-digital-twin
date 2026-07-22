import json
from pathlib import Path
import pytest
from gpu_agent.dashboard.gap_chart import build_gap_data, spark_svg


def _mk_monthly(tmp_path, as_of, rev, dmi, smi):
    p = tmp_path / f"{as_of}-v{rev}.json"
    p.write_text(json.dumps({
        "asOf": as_of,
        "demandSupply": {"dmiContribution": dmi, "smiContribution": smi},
        "categoryStatus": {"rating": "Strong", "direction": "improving",
                           "reason": "", "constraintLabel": "HBM memory"},
        "dimensionRatings": {}, "findings": [],
    }), encoding="utf-8")
    return p


def test_build_gap_data_levels_and_word(tmp_path):
    _mk_monthly(tmp_path, "2026-05", 1, 1.0, 0.5)
    _mk_monthly(tmp_path, "2026-06", 2, 1.0, 1.0)   # highest rev of month wins
    _mk_monthly(tmp_path, "2026-06", 1, 9.9, 9.9)   # ignored (lower rev)
    _mk_monthly(tmp_path, "2026-07", 1, 2.0, 0.2)
    data = build_gap_data(tmp_path)
    assert [m["key"] for m in data["months"]] == ["2026-05", "2026-06", "2026-07"]
    assert data["months"][-1]["label"] == "Jul"
    assert data["demand"] == [110.0, 120.0, 140.0]   # 100+10*cumsum(1,1,2)
    assert data["supply"] == [105.0, 115.0, 117.0]   # 100+10*cumsum(.5,1,.2)
    assert data["gap_now"] == pytest.approx(23.0)
    assert data["gap_prev"] == pytest.approx(5.0)
    assert data["gap_word"] == "widened"


def test_build_gap_data_daily_files_ignored_and_none_when_thin(tmp_path):
    _mk_monthly(tmp_path, "2026-07", 1, 1.0, 1.0)
    (tmp_path / "2026-07-02-v1.json").write_text("{}", encoding="utf-8")
    assert build_gap_data(tmp_path) is None  # one monthly point is not enough


def test_gap_word_dead_band(tmp_path):
    _mk_monthly(tmp_path, "2026-06", 1, 1.0, 1.0)
    _mk_monthly(tmp_path, "2026-07", 1, 1.02, 1.0)  # gap moves 0.2 < 0.5
    assert build_gap_data(tmp_path)["gap_word"] == "held"


def test_spark_svg_shape():
    svg = spark_svg([1.0, 2.0, 1.5])
    assert svg.startswith("<svg") and "polyline" in svg and "viewBox" in svg
    assert spark_svg([]) == ""
