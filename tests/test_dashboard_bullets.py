import json
from pathlib import Path

import jsonschema
import pytest

from gpu_agent.chartdata.registry import ChartSeries
from gpu_agent.dashboard.bullets import build_bullets

STORY = json.loads(Path("fixtures/dashboard/story-trimmed.json").read_text(encoding="utf-8"))
SCORECARD = json.loads(Path("fixtures/dashboard/scorecard-trimmed.json").read_text(encoding="utf-8"))
SCHEMA = json.loads(Path("web/schema/dashboard.schema.json").read_text(encoding="utf-8"))
REAL_SERIES_DIR = "store/series"

_BULLET_RESOLVER = jsonschema.validators.RefResolver.from_schema(SCHEMA)
_BULLET_VALIDATOR = jsonschema.Draft202012Validator(SCHEMA["$defs"]["bullet"], resolver=_BULLET_RESOLVER)


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


def _row(indicator_id, period, value, estimate_grade=False, unit="USD_B",
         url="https://example.test/src", title="Example source"):
    return {
        "indicatorId": indicator_id, "period": period, "value": value, "unit": unit,
        "publishedAt": f"{period}-15", "capturedAt": "2026-08-05",
        "source": {"url": url, "title": title},
        "estimateGrade": estimate_grade,
        "note": "synthetic test row",
    }


def _assert_no_jargon(s: str) -> None:
    assert "DMI" not in s and "SMI" not in s


def _assert_bullet_plain_english(bullet: dict) -> None:
    _assert_no_jargon(bullet["text"])
    if bullet["noChartReason"] is not None:
        _assert_no_jargon(bullet["noChartReason"])
    chart = bullet["chart"]
    if chart is not None:
        for field in ("title", "unit", "caption"):
            _assert_no_jargon(chart[field])
        # a raw internal unit code (e.g. "revision_direction",
        # "credit_condition_index") always contains an underscore; the
        # chart must only ever show the mapped plain-English value.
        assert "_" not in chart["unit"], f"chart unit looks like a raw code: {chart['unit']!r}"
        src = chart["source"]
        refs = src["basedOn"] if src.get("assessment") else [src]
        for ref in refs:
            _assert_no_jargon(ref["title"])
            _assert_no_jargon(ref["outlet"])


def _validate_bullet_schema(bullet: dict) -> None:
    _BULLET_VALIDATOR.validate(bullet)


def _synthetic_story(scene_title, claim_ids, visual=None):
    scene = {"n": 1, "title": scene_title, "paragraphs": ["First sentence here. More words follow."],
              "claimFindingIds": claim_ids}
    if visual is not None:
        scene["visual"] = visual
    return {
        "storyDate": "2026-08-05",
        "scenes": [
            scene,
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
        _assert_bullet_plain_english(b)
        _validate_bullet_schema(b)
        if b["noChartReason"] is not None:
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


def test_real_story_scene_two_has_no_chart_after_the_measurable_quantity_gate():
    # Controller ruling (review): hyperscalerCapexRevision's unit is
    # 'revision_direction' -- an internal net-count index (buyers revising
    # spend up minus down), not a real measurable quantity. Even though it
    # has 27 real, dense, non-estimate rows, it must NOT be charted: an
    # executive reading a line chart with a y-axis would wrongly conclude
    # something physical rose or fell. This is the documented, honest
    # consequence of the fix -- not a bug.
    bullets = build_bullets(STORY, SCORECARD, {}, REAL_SERIES_DIR)
    scene_two = bullets[1]
    assert scene_two["chart"] is None
    assert scene_two["noChartReason"] is not None
    assert "internal analytical score" in scene_two["noChartReason"]


# ---------------------------------------------------------------------------
# Rule 2 (registered series) + honesty gate: chartable is respected.
# ---------------------------------------------------------------------------

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
    _assert_bullet_plain_english(b0)
    _validate_bullet_schema(b0)


def test_registry_match_below_point_threshold_falls_through(tmp_path):
    # Only 3 points on disk -- below the brief's >=4 rule-2 threshold. If
    # that threshold were removed/weakened this would incorrectly chart.
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
    _assert_no_jargon(b0["noChartReason"])


def test_registered_hard_fact_series_with_all_estimate_rows_on_disk_not_charted(tmp_path):
    # IMPORTANT 6 from review: the registry's quality flag can be wrong
    # relative to what's actually on disk (store/series/ has other
    # writers). A series REGISTERED as hard-fact whose jsonl rows are all
    # estimateGrade=true must still be refused -- the row-level ground
    # truth wins over the registry's claim. If rule 2 only checked
    # cs.chartable and never filtered rows by estimateGrade, this test
    # would flip to a populated chart.
    story = _synthetic_story("Mis-registered scene", ["f1"])
    scorecard = _synthetic_scorecard("f1", "hbmSupplyCapex", "market")
    series_reg = {"hbmSupplyCapex": _series(
        "hbmSupplyCapex", ["hbmSupplyCapex"], quality="hard-fact")}
    rows = [_row("hbmSupplyCapex", f"2025-{m:02d}", 1.0 + m, estimate_grade=True)
            for m in range(1, 9)]
    _write_jsonl(tmp_path / "hbmSupplyCapex.jsonl", rows)

    bullets = build_bullets(story, scorecard, series_reg, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None


# ---------------------------------------------------------------------------
# Rule 3 (fallback: the scene's own indicator history) density gate.
# ---------------------------------------------------------------------------

_PLAIN_VISUAL = {"seriesId": "someTrackedIndicator", "label": "Some Tracked Number"}


def test_fallback_dense_non_estimate_history_yields_chart(tmp_path):
    story = _synthetic_story("Dense fallback scene", ["f1"], visual=_PLAIN_VISUAL)
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", p, float(i), unit="USD")
            for i, p in enumerate(["2025-01", "2025-02", "2025-03",
                                    "2025-04", "2025-05", "2025-06"])]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is not None
    assert b0["noChartReason"] is None
    assert len(b0["chart"]["points"]) == 6
    assert b0["chart"]["title"] == "Some Tracked Number"
    assert b0["chart"]["unit"] == "US$"
    _assert_bullet_plain_english(b0)
    _validate_bullet_schema(b0)


def test_fallback_below_six_points_falls_to_no_chart(tmp_path):
    # 5 points, 5 distinct months, all non-estimate, plain unit+title both
    # present -- one short of the brief's fixed threshold (>=6 points), so
    # density alone must be why this fails. If _MIN_FALLBACK_POINTS were
    # dropped to e.g. 1, this test would flip to a populated chart.
    story = _synthetic_story("Thin fallback scene", ["f1"], visual=_PLAIN_VISUAL)
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", p, float(i), unit="USD")
            for i, p in enumerate(["2025-01", "2025-02", "2025-03",
                                    "2025-04", "2025-05"])]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None


def test_fallback_enough_points_but_too_few_months_falls_to_no_chart(tmp_path):
    # 6 points but crammed into 2 distinct months -- fails the "spanning >=
    # 3 distinct months" leg of the density gate even though point count
    # alone would pass. If the month-span check were removed, this would
    # flip to a populated chart.
    story = _synthetic_story("Same-month fallback scene", ["f1"], visual=_PLAIN_VISUAL)
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", "2025-01", float(d), unit="USD") for d in range(1, 4)]
    rows += [_row("someTrackedIndicator", "2025-02", float(d), unit="USD") for d in range(1, 4)]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None


def test_fallback_estimate_grade_rows_excluded_from_density_count(tmp_path):
    # 8 rows on disk, but all marked estimateGrade True -- an estimate-only
    # history must never be charted regardless of point count. If the
    # estimateGrade filter were removed, this would flip to a populated
    # chart.
    story = _synthetic_story("Estimate-only fallback scene", ["f1"], visual=_PLAIN_VISUAL)
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", f"2025-{m:02d}", float(m), estimate_grade=True, unit="USD")
            for m in range(1, 9)]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None
    assert "estimate" in b0["noChartReason"].lower()


def test_fallback_non_measurable_unit_never_charted_even_when_dense(tmp_path):
    # CRITICAL 2 from review: plenty of real, dense, non-estimate history
    # (8 points, 8 months) is not enough on its own -- a raw unit that
    # isn't a real plain-English measurable quantity (here,
    # 'revision_direction', a synthetic net-count index, same as the real
    # hyperscalerCapexRevision series) must never be drawn as a chart. If
    # the plain-unit gate were removed, this would flip to a populated
    # chart.
    story = _synthetic_story("Index-only fallback scene", ["f1"], visual=_PLAIN_VISUAL)
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", f"2025-{m:02d}", float(m % 3 - 1),
                 unit="revision_direction") for m in range(1, 9)]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None
    assert "internal analytical score" in b0["noChartReason"]


def test_fallback_without_narrator_supplied_plain_title_never_charted(tmp_path):
    # Plain, measurable unit ("USD") and plenty of dense real history, but
    # no scene.visual.label names this indicator -- there is no honest
    # plain-English title to put on the chart (a mechanically-derived
    # label from a bare id like "someTrackedIndicator" is not narrator
    # copy). If the title-source requirement were dropped in favor of a
    # mechanical camelCase-derived title, this would flip to a populated
    # chart.
    story = _synthetic_story("No-visual fallback scene", ["f1"])  # no visual field
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", f"2025-{m:02d}", float(m), unit="USD")
            for m in range(1, 9)]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None


def test_fallback_chart_never_titled_a_bare_indicator_code(tmp_path):
    # IMPORTANT 5 from review: scene 3 in the real story cites indicator
    # ids like "S9"/"S10" -- if a series file for one of those ever
    # appears, the chart must never be titled the bare code "S9". Covers
    # both the plain-title requirement above and the acronym/jargon check,
    # using a code-shaped id.
    story = _synthetic_story("Coded indicator scene", ["f1"])  # no visual field
    scorecard = _synthetic_scorecard("f1", "S9", "market")
    rows = [_row("S9", f"2025-{m:02d}", float(m), unit="USD") for m in range(1, 9)]
    _write_jsonl(tmp_path / "S9.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None  # no plain title available -> honest no-chart, never "S9"


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


# ---------------------------------------------------------------------------
# CRITICAL 1: fallback chart source is an honest synthesis, not one
# misattributed article.
# ---------------------------------------------------------------------------

def test_fallback_chart_source_is_an_assessment_over_distinct_refs(tmp_path):
    story = _synthetic_story("Multi-source scene", ["f1"], visual=_PLAIN_VISUAL)
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [
        _row("someTrackedIndicator", "2025-01", 1.0, unit="USD",
             url="https://alpha.example/a", title="Alpha article"),
        _row("someTrackedIndicator", "2025-02", 2.0, unit="USD",
             url="https://beta.example/b", title="Beta article"),
        _row("someTrackedIndicator", "2025-03", 3.0, unit="USD",
             url="https://gamma.example/c", title="Gamma article"),
        _row("someTrackedIndicator", "2025-04", 4.0, unit="USD",
             url="https://alpha.example/a", title="Alpha article"),  # duplicate url
        _row("someTrackedIndicator", "2025-05", 5.0, unit="USD",
             url="https://delta.example/d", title="Delta article"),
        _row("someTrackedIndicator", "2025-06", 6.0, unit="USD",
             url="https://epsilon.example/e", title="Epsilon article"),
    ]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    chart = bullets[0]["chart"]
    assert chart is not None
    src = chart["source"]
    # An assessment ref, not a single plain ref pretending to be "the" source.
    assert src["assessment"] is True
    assert "basedOn" in src
    urls = [r["url"] for r in src["basedOn"]]
    assert len(urls) == len(set(urls)) == 5  # 6 rows, 1 duplicate url -> 5 distinct
    # The one CRITICAL-1 regression this guards: no single row's own
    # article stands in as the caption's "the" source of the whole series.
    assert "Source: " not in chart["caption"]
    _validate_bullet_schema(bullets[0])


# ---------------------------------------------------------------------------
# IMPORTANT 4: outlet is derived from the URL's own domain, never the
# article headline.
# ---------------------------------------------------------------------------

def test_fallback_ref_outlet_is_domain_not_headline(tmp_path):
    story = _synthetic_story("Outlet scene", ["f1"], visual=_PLAIN_VISUAL)
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", p, float(i), unit="USD",
                 url="https://www.cnbc.com/2026/06/10/oracle-q4-earnings.html",
                 title="Oracle beats on earnings, but stock drops on plans to raise "
                       "another $20 billion - CNBC")
            for i, p in enumerate(["2025-01", "2025-02", "2025-03",
                                    "2025-04", "2025-05", "2025-06"])]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    ref = bullets[0]["chart"]["source"]["basedOn"][0]
    assert ref["outlet"] == "cnbc.com"
    assert ref["outlet"] != ref["title"]
    assert "$20 billion" not in ref["outlet"]


# ---------------------------------------------------------------------------
# CRITICAL 3: exactly 3 bullets, always -- fails loudly and early on a
# short story day instead of silently shipping 1 or 2 bullets.
# ---------------------------------------------------------------------------

def test_fewer_than_three_qualifying_scenes_raises_clearly():
    short_story = {
        "storyDate": "2026-08-05",
        "scenes": [
            {"n": 1, "title": "Only scene", "paragraphs": ["One sentence."],
             "claimFindingIds": []},
            {"n": 2, "title": "What to watch from here", "paragraphs": ["Skip."],
             "claimFindingIds": []},
        ],
    }
    with pytest.raises(ValueError, match="found 1"):
        build_bullets(short_story, {"findings": []}, {}, "store/series")


def test_zero_qualifying_scenes_raises_clearly():
    empty_story = {"storyDate": "2026-08-05", "scenes": []}
    with pytest.raises(ValueError, match="found 0"):
        build_bullets(empty_story, {"findings": []}, {}, "store/series")


# ---------------------------------------------------------------------------
# MINOR 8: title-punctuation stripping handles '?'/'!' too, not just '.'.
# ---------------------------------------------------------------------------

def test_bullet_title_ending_in_question_mark_not_double_punctuated(tmp_path):
    story = _synthetic_story("Is AMD winning?", ["f1"])
    scorecard = _synthetic_scorecard("f1", "totallyUntrackedIndicator", "market")
    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    assert bullets[0]["text"].startswith("Is AMD winning. ")
    assert "winning?." not in bullets[0]["text"]


# ---------------------------------------------------------------------------
# Abbreviations must not be mistaken for sentence ends.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("paragraph,expected_start", [
    ("The U.S. market grew fast. It kept growing.", "The U.S. market grew fast."),
    ("Dr. Smith said demand is strong. Everyone agreed.", "Dr. Smith said demand is strong."),
    ("This is a footnote, e.g. the market moved. Then it moved again.",
     "This is a footnote, e.g. the market moved."),
])
def test_first_sentence_not_truncated_by_abbreviations(tmp_path, paragraph, expected_start):
    story = {
        "storyDate": "2026-08-05",
        "scenes": [
            {"n": 1, "title": "Abbreviation scene", "paragraphs": [paragraph],
             "claimFindingIds": []},
            {"n": 2, "title": "Filler two", "paragraphs": ["Filler. Filler."], "claimFindingIds": []},
            {"n": 3, "title": "Filler three", "paragraphs": ["Filler. Filler."], "claimFindingIds": []},
            {"n": 4, "title": "What to watch from here", "paragraphs": ["Skip."], "claimFindingIds": []},
        ],
    }
    bullets = build_bullets(story, {"findings": []}, {}, str(tmp_path))
    assert bullets[0]["text"] == f"Abbreviation scene. {expected_start}"
