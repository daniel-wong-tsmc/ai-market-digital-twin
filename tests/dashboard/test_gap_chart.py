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


def test_impossible_month_filename_is_skipped_not_crashed(tmp_path):
    # A scorecard filename can match the "YYYY-MM-vN.json" pattern with an
    # impossible month (e.g. "2026-13-v1.json") and still exist on disk.
    # Such a file must be skipped, not crash the build when something later
    # turns the key into a real month (dt.date(...), the month-label table).
    _mk_monthly(tmp_path, "2026-05", 1, 1.0, 0.5)
    _mk_monthly(tmp_path, "2026-06", 1, 1.0, 1.0)
    (tmp_path / "2026-13-v1.json").write_text(json.dumps({
        "asOf": "2026-13",
        "demandSupply": {"dmiContribution": 5.0, "smiContribution": 5.0},
        "categoryStatus": {"rating": "Strong", "direction": "improving",
                           "reason": "", "constraintLabel": "HBM memory"},
        "dimensionRatings": {}, "findings": [],
    }), encoding="utf-8")
    data = build_gap_data(tmp_path)
    assert [m["key"] for m in data["months"]] == ["2026-05", "2026-06"]


def test_gap_word_dead_band(tmp_path):
    _mk_monthly(tmp_path, "2026-06", 1, 1.0, 1.0)
    _mk_monthly(tmp_path, "2026-07", 1, 1.02, 1.0)  # gap moves 0.2 < 0.5
    assert build_gap_data(tmp_path)["gap_word"] == "held"


def test_spark_svg_shape():
    svg = spark_svg([1.0, 2.0, 1.5])
    assert svg.startswith("<svg") and "polyline" in svg and "viewBox" in svg
    assert spark_svg([]) == ""


from gpu_agent.dashboard.gap_chart import render_gap_svg


def _data(tmp_path):
    _mk_monthly(tmp_path, "2026-05", 1, 1.0, 0.5)
    _mk_monthly(tmp_path, "2026-06", 1, 1.0, 1.0)
    _mk_monthly(tmp_path, "2026-07", 1, 2.0, 0.2)
    return build_gap_data(tmp_path)


def test_render_gap_svg_structure(tmp_path):
    svg = render_gap_svg(_data(tmp_path))
    assert svg.count("<svg") == 1 and svg.count("</svg>") == 1
    assert "polyline" in svg and "polygon" in svg          # lines + shaded gap
    assert "the gap, this week" in svg
    assert "What buyers want (demand)" in svg
    assert "What can be shipped (supply)" in svg
    assert "orders vs. chips shipped, indexed" in svg
    assert 'stroke-dasharray' in svg                        # now-line
    assert ">Jul<" in svg and ">May<" in svg                # month ticks


def test_render_gap_svg_callout_is_panel_trigger(tmp_path):
    svg = render_gap_svg(_data(tmp_path), callouts=[
        {"month_key": "2026-06", "text": "Jun: memory makers cut back",
         "claim": "callout:1"}])
    assert 'data-ev="callout:1"' in svg
    assert "Jun: memory makers cut back" in svg


def test_render_gap_svg_escapes_callout_text(tmp_path):
    svg = render_gap_svg(_data(tmp_path), callouts=[
        {"month_key": "2026-06", "text": "<img src=x>", "claim": None}])
    assert "<img" not in svg and "&lt;img" in svg
