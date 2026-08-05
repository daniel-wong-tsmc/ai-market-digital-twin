import json
from pathlib import Path

import pytest

from gpu_agent.chartdata.registry import ChartSeries
from gpu_agent.dashboard.bullets import build_bullets

STORY = json.loads(Path("fixtures/dashboard/story-trimmed.json").read_text(encoding="utf-8"))
SCORECARD = json.loads(Path("fixtures/dashboard/scorecard-trimmed.json").read_text(encoding="utf-8"))
REAL_SERIES_DIR = "store/series"


def _series(id_, tags, quality="hard-fact", form="columns", unit="USD bn",
            name=None, source_name="Test source", source_url="https://example.test/x"):
    return ChartSeries(
        id=id_, name=name or id_, sourceName=source_name, sourceUrl=source_url,
        cadence="quarterly", quality=quality, topicTags=tuple(tags), form=form,
        unit=unit, fetcher=None,
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _row(indicator_id, period, value, estimate_grade=False, unit="USD bn",
         url="https://example.test/src", title="Example source"):
    return {
        "indicatorId": indicator_id, "period": period, "value": value, "unit": unit,
        "publishedAt": f"{period}-15", "capturedAt": "2026-08-05",
        "source": {"url": url, "title": title},
        "estimateGrade": estimate_grade,
        "note": "synthetic test row",
    }


# ---------------------------------------------------------------------------
# Real-fixture test: exactly 3 bullets, real data, XOR always holds.
# ---------------------------------------------------------------------------

def test_real_story_yields_exactly_three_bullets_with_valid_xor():
    bullets = build_bullets(STORY, SCORECARD, {}, REAL_SERIES_DIR)
    assert len(bullets) == 3
    for b in bullets:
        assert set(b.keys()) == {"date", "text", "storyHref", "chart", "noChartReason", "sources"}
        # exactly one of chart/noChartReason is populated -- never both, never neither.
        assert (b["chart"] is None) != (b["noChartReason"] is None)
        assert "DMI" not in b["text"] and "SMI" not in b["text"]
        if b["noChartReason"] is not None:
            assert "DMI" not in b["noChartReason"] and "SMI" not in b["noChartReason"]
            assert b["noChartReason"].startswith("No chart.")


def test_real_story_bullet_text_uses_scene_title_and_first_sentence():
    bullets = build_bullets(STORY, SCORECARD, {}, REAL_SERIES_DIR)
    assert bullets[0]["text"].startswith("AMD delivered, and it does not add chips this year.")
    assert "AMD reported the quarter the market was waiting for." in bullets[0]["text"]


def test_first_sentence_not_cut_at_a_decimal_point():
    # Scene 2's own first paragraph starts "SpaceX ended the June quarter
    # with 1.4 gigawatts..." -- a naive "stop at the first '.' found" scan
    # would truncate the bullet to "...with 1." A real sentence boundary
    # (period followed by whitespace) must be used instead.
    bullets = build_bullets(STORY, SCORECARD, {}, REAL_SERIES_DIR)
    text = bullets[1]["text"]
    assert "1.4 gigawatts" in text
    assert not text.rstrip().endswith("with 1.")
    assert text.endswith("year.")


def test_real_story_scene_two_gets_a_fallback_chart_from_real_hyperscaler_history():
    # hyperscalerCapexRevision.jsonl on disk is real, hard-fact (estimateGrade
    # false throughout) history spanning many months -- dense enough to
    # legitimately back scene 2's own cited finding (indicatorId
    # hyperscalerCapexRevision), so this bullet must carry a chart, not a
    # noChartReason.
    bullets = build_bullets(STORY, SCORECARD, {}, REAL_SERIES_DIR)
    scene_two = bullets[1]
    assert scene_two["chart"] is not None
    assert scene_two["noChartReason"] is None
    assert len(scene_two["chart"]["points"]) <= 10
    assert len(scene_two["chart"]["points"]) >= 6


# ---------------------------------------------------------------------------
# Rule 2 (registered series) + honesty gate: chartable is respected.
# ---------------------------------------------------------------------------

def _synthetic_story(scene_title, claim_ids):
    return {
        "storyDate": "2026-08-05",
        "scenes": [
            {"n": 1, "title": scene_title, "paragraphs": ["First sentence here. More words follow."],
             "claimFindingIds": claim_ids},
            {"n": 2, "title": "Filler scene two", "paragraphs": ["Filler sentence one. More."],
             "claimFindingIds": []},
            {"n": 3, "title": "Filler scene three", "paragraphs": ["Filler sentence two. More."],
             "claimFindingIds": []},
            {"n": 4, "title": "What to watch from here", "paragraphs": ["Skip me. Skip."],
             "claimFindingIds": []},
        ],
    }


def _synthetic_scorecard(finding_id, indicator_id, entity):
    return {
        "findings": [
            {"id": finding_id, "indicatorId": indicator_id, "entity": entity,
             "evidence": [{"source": "Test outlet", "url": "https://example.test/e",
                            "date": "2026-08-01", "tier": "primary"}]},
        ]
    }


def test_registry_match_with_enough_points_yields_chart(tmp_path):
    story = _synthetic_story("AMD scene title", ["f1"])
    scorecard = _synthetic_scorecard("f1", "vendorRevenueGuidance", "amd")
    series_reg = {"amdDataCenterRevenue": _series(
        "amdDataCenterRevenue", ["amdDataCenter", "amd"], quality="hard-fact")}
    rows = [_row("amdDataCenterRevenue", f"2025-{m:02d}", 1.0 + m) for m in range(1, 9)]
    _write_jsonl(tmp_path / "amdDataCenterRevenue.jsonl", rows)

    bullets = build_bullets(story, scorecard, series_reg, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is not None
    assert b0["noChartReason"] is None
    assert len(b0["chart"]["points"]) == 8
    assert b0["chart"]["form"] == "columns"


def test_registry_match_below_point_threshold_falls_through(tmp_path):
    # Only 3 points on disk -- below the brief's >=4 rule-2 threshold. If that
    # threshold were removed/weakened this would incorrectly produce a chart.
    story = _synthetic_story("AMD thin scene", ["f1"])
    scorecard = _synthetic_scorecard("f1", "vendorRevenueGuidance", "amd")
    series_reg = {"amdDataCenterRevenue": _series(
        "amdDataCenterRevenue", ["amdDataCenter", "amd"], quality="hard-fact")}
    rows = [_row("amdDataCenterRevenue", f"2025-{m:02d}", 1.0 + m) for m in range(1, 4)]
    _write_jsonl(tmp_path / "amdDataCenterRevenue.jsonl", rows)

    bullets = build_bullets(story, scorecard, series_reg, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None


def test_estimate_grade_series_never_charted_even_with_plenty_of_points(tmp_path):
    # gpuSpotPrice is quality=estimate -> chartable is False. This must be
    # honored even though its jsonl has plenty of points: a small chart must
    # never be drawn from an estimate. If `series.chartable` were ignored
    # here, this test would flip to a populated chart.
    story = _synthetic_story("GPU price scene", ["f1"])
    scorecard = _synthetic_scorecard("f1", "gpuSpotPrice", "market")
    series_reg = {"gpuSpotPrice": _series(
        "gpuSpotPrice", ["gpuSpotPrice"], quality="estimate", form="line", unit="USD")}
    rows = [_row("gpuSpotPrice", f"2025-{m:02d}", 30000.0, estimate_grade=True)
            for m in range(1, 9)]
    _write_jsonl(tmp_path / "gpuSpotPrice.jsonl", rows)

    bullets = build_bullets(story, scorecard, series_reg, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None
    assert "estimate" in b0["noChartReason"].lower()
    assert "DMI" not in b0["noChartReason"] and "SMI" not in b0["noChartReason"]


# ---------------------------------------------------------------------------
# Rule 3 (fallback: the scene's own indicator history) density gate.
# ---------------------------------------------------------------------------

def test_fallback_dense_non_estimate_history_yields_chart(tmp_path):
    story = _synthetic_story("Dense fallback scene", ["f1"])
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", p, float(i))
            for i, p in enumerate(["2025-01", "2025-02", "2025-03",
                                    "2025-04", "2025-05", "2025-06"])]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is not None
    assert b0["noChartReason"] is None
    assert len(b0["chart"]["points"]) == 6


def test_fallback_below_six_points_falls_to_no_chart(tmp_path):
    # 5 points, 5 distinct months, all non-estimate -- one short of the
    # brief's fixed threshold (>=6 points). If _MIN_FALLBACK_POINTS were
    # dropped to e.g. 1, this test would flip to a populated chart.
    story = _synthetic_story("Thin fallback scene", ["f1"])
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", p, float(i))
            for i, p in enumerate(["2025-01", "2025-02", "2025-03",
                                    "2025-04", "2025-05"])]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None


def test_fallback_enough_points_but_too_few_months_falls_to_no_chart(tmp_path):
    # 6 points but crammed into 2 distinct months -- fails the "spanning >= 3
    # distinct months" leg of the density gate even though the point count
    # alone would pass. If the month-span check were removed, this would
    # flip to a populated chart.
    story = _synthetic_story("Same-month fallback scene", ["f1"])
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", f"2025-01-{d:02d}"[:7], float(d))
            for d in range(1, 4)]
    rows += [_row("someTrackedIndicator", f"2025-02-{d:02d}"[:7], float(d))
             for d in range(1, 4)]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None


def test_fallback_estimate_grade_rows_excluded_from_density_count(tmp_path):
    # 8 rows on disk, but they're all marked estimateGrade True -- an
    # estimate-only history must never be charted regardless of point
    # count. If the estimateGrade filter were removed, this would flip to a
    # populated chart.
    story = _synthetic_story("Estimate-only fallback scene", ["f1"])
    scorecard = _synthetic_scorecard("f1", "someEstimatedIndicator", "market")
    rows = [_row("someEstimatedIndicator", f"2025-{m:02d}", float(m), estimate_grade=True)
            for m in range(1, 9)]
    _write_jsonl(tmp_path / "someEstimatedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None
    assert "estimate" in b0["noChartReason"].lower()


def test_no_matching_indicator_at_all_yields_honest_no_chart_reason(tmp_path):
    story = _synthetic_story("Untracked scene", ["f1"])
    scorecard = _synthetic_scorecard("f1", "totallyUntrackedIndicator", "market")

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None
    assert b0["noChartReason"].startswith("No chart.")


def test_sources_come_from_refs_for_finding_ids(tmp_path):
    story = _synthetic_story("Sourced scene", ["f1"])
    scorecard = _synthetic_scorecard("f1", "totallyUntrackedIndicator", "market")

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["sources"] == [{"title": "Test outlet", "outlet": "Test outlet",
                               "url": "https://example.test/e", "date": "2026-08-01",
                               "tier": "primary"}]
