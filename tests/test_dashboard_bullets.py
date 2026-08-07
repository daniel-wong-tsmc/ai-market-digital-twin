import json
from pathlib import Path

import jsonschema
import pytest

from gpu_agent.chartdata.registry import ChartSeries
from gpu_agent.dashboard.bullets import _MAX_CHART_POINTS, _load_plain_units, build_bullets

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
        _assert_no_jargon(bullet["noChartReason"]["reason"])
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
            assert set(b["noChartReason"].keys()) == {"reason", "cause"}
            assert b["noChartReason"]["cause"] in (
                "no-published-number", "estimate-only", "no-plain-name", "too-sparse")


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
    #
    # Round-2 review: scene 2's own visual.label DOES name this indicator,
    # so this must be the "not a plain measurable quantity" reason, not
    # the (also real, but different, and here inapplicable) "no
    # plain-English name yet" reason -- the unit check fires before the
    # title check ever gets a chance to matter.
    bullets = build_bullets(STORY, SCORECARD, {}, REAL_SERIES_DIR)
    scene_two = bullets[1]
    assert scene_two["chart"] is None
    assert scene_two["noChartReason"] is not None
    assert "describe what this number measures" in scene_two["noChartReason"]["reason"]
    assert "no plain-English name" not in scene_two["noChartReason"]["reason"]
    assert scene_two["noChartReason"]["cause"] == "no-plain-name"


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
    # The finding's own indicatorId ("vendorRevenueGuidance") has no series
    # file of its own on disk here -- distinct from the curated series id
    # that fell short of rule 2's point threshold -- so the fallback's own
    # "nobody tracks a number for THIS indicator" branch fires.
    assert b0["noChartReason"]["cause"] == "no-published-number"


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
    assert "estimate" in b0["noChartReason"]["reason"].lower()
    assert b0["noChartReason"]["cause"] == "estimate-only"
    _assert_no_jargon(b0["noChartReason"]["reason"])


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
    assert "estimate" in b0["noChartReason"]["reason"].lower()
    assert b0["noChartReason"]["cause"] == "estimate-only"


def test_fallback_non_measurable_unit_never_charted_even_when_dense(tmp_path):
    # CRITICAL 2 from review: plenty of real, dense, non-estimate history
    # (8 points, 8 months) is not enough on its own -- a raw unit that
    # isn't a real plain-English measurable quantity (here,
    # 'revision_direction', a synthetic net-count index, same as the real
    # hyperscalerCapexRevision series) must never be drawn as a chart. If
    # the plain-unit gate were removed, this would flip to a populated
    # chart.
    #
    # Round-2 review (IMPORTANT): a narrator visual.label IS present here
    # (_PLAIN_VISUAL), so a wrong implementation could still fall into the
    # "no plain-English name yet" reason instead of the true "not a
    # measurable quantity" one -- assert the RIGHT reason, not just *a*
    # reason, and assert the wrong one's distinguishing phrase is absent.
    story = _synthetic_story("Index-only fallback scene", ["f1"], visual=_PLAIN_VISUAL)
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", f"2025-{m:02d}", float(m % 3 - 1),
                 unit="revision_direction") for m in range(1, 9)]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None
    assert "describe what this number measures" in b0["noChartReason"]["reason"]
    assert "no plain-English name" not in b0["noChartReason"]["reason"]
    assert b0["noChartReason"]["cause"] == "no-plain-name"


def test_fallback_without_narrator_supplied_plain_title_never_charted(tmp_path):
    # Plain, measurable unit ("USD") and plenty of dense real history, but
    # no scene.visual.label names this indicator -- there is no honest
    # plain-English title to put on the chart (a mechanically-derived
    # label from a bare id like "someTrackedIndicator" is not narrator
    # copy). If the title-source requirement were dropped in favor of a
    # mechanical camelCase-derived title, this would flip to a populated
    # chart.
    #
    # Round-2 review (IMPORTANT, this is the exact defect the round-1 fix
    # introduced): the number here is a perfectly real, plain, measurable
    # quantity (US$) -- it would be FALSE to tell the reader "this is an
    # internal analytical score, not a plain measured number". The reason
    # given must be the true one: we have the number, we just don't have
    # a plain name for it yet.
    story = _synthetic_story("No-visual fallback scene", ["f1"])  # no visual field
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", f"2025-{m:02d}", float(m), unit="USD")
            for m in range(1, 9)]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is None
    assert b0["noChartReason"] is not None
    assert "no plain-English name for what they measure yet" in b0["noChartReason"]["reason"]
    assert "describe what this number measures" not in b0["noChartReason"]["reason"]
    assert b0["noChartReason"]["cause"] == "no-plain-name"


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
    assert b0["noChartReason"]["cause"] == "no-published-number"
    assert b0["noChartReason"]["reason"].endswith(".")


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


def test_fallback_ref_outlet_with_no_url_is_honest_not_the_headline(tmp_path):
    # MINOR from round-2 review: when a row has no source.url at all,
    # `_outlet_from_url` can't derive a domain -- the old fallback quietly
    # reused the headline as "outlet" again, exactly the bug Important 4
    # fixed on the normal (has-a-url) path. The fallback must be an
    # honest "we don't know", never the headline wearing an outlet's hat.
    story = _synthetic_story("No-url outlet scene", ["f1"], visual=_PLAIN_VISUAL)
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", p, float(i), unit="USD", url=None,
                 title="A Headline That Is Not An Outlet")
            for i, p in enumerate(["2025-01", "2025-02", "2025-03",
                                    "2025-04", "2025-05", "2025-06"])]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    ref = bullets[0]["chart"]["source"]["basedOn"][0]
    assert ref["outlet"] != "A Headline That Is Not An Outlet"
    assert ref["outlet"] != ref["title"]
    assert ref["outlet"] == "Unknown outlet"


# ---------------------------------------------------------------------------
# MINOR: the plain-unit whitelist is loaded from data, not hardcoded, so a
# new legitimate unit can be added without a code change.
# ---------------------------------------------------------------------------

def test_plain_units_loaded_from_registry_file_include_real_units():
    units = _load_plain_units()
    assert units["USD"] == "US$"
    assert units["pct_yoy"] == "%, year over year"


def test_plain_units_falls_back_safely_when_file_missing(tmp_path):
    units = _load_plain_units(str(tmp_path / "does-not-exist.json"))
    # Never crashes, and still returns a usable, non-empty mapping.
    assert units and units.get("USD") == "US$"


def test_plain_units_falls_back_when_units_mapping_is_empty(tmp_path):
    # Round-3 review (silent-failure class): {"units": {}} passes the old
    # `isinstance(units, dict) and all(...)` check -- an empty dict IS a
    # dict, and `all()` over an empty iterable is vacuously True -- so a
    # well-formed-but-empty file silently disabled every chart with no
    # signal at all. An empty mapping must be treated as invalid, exactly
    # like the other malformed shapes, and fall back to the built-in
    # default instead.
    bad_path = tmp_path / "empty-units.json"
    bad_path.write_text(json.dumps({"units": {}}), encoding="utf-8")
    units = _load_plain_units(str(bad_path))
    assert units and units.get("USD") == "US$"


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
    # MINOR from round-2 review: "no" is a common word, not an
    # abbreviation -- it must not swallow the next sentence.
    ("The answer is no. It kept growing.", "The answer is no."),
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


# ---------------------------------------------------------------------------
# Test-coverage gap closed (round-2 review): round 1's fix correctly took
# away the real fixture's only chart (hyperscalerCapexRevision failed the
# measurable-quantity gate), which left NO test proving a chart can ever
# be produced from genuine on-disk data -- only synthetic fixtures covered
# the success path. store/series/odmMonthlyAiRevenue.jsonl is real,
# on-disk, 42 rows, all estimateGrade=false, spanning 42 distinct months,
# unit pct_yoy (a real plain-English measurable quantity) -- it passes
# both the density gate and the plain-quantity gate outright, today.
# ---------------------------------------------------------------------------

def test_fallback_chart_produced_from_real_on_disk_odm_series():
    real_rows = [json.loads(line) for line in
                 Path("store/series/odmMonthlyAiRevenue.jsonl").read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    assert len(real_rows) >= 6  # sanity: the fixture claim this test relies on
    assert all(r["estimateGrade"] is False for r in real_rows)
    assert len({r["period"][:7] for r in real_rows}) >= 3
    assert real_rows[0]["unit"] == "pct_yoy"

    visual = {"seriesId": "odmMonthlyAiRevenue", "label": "Servers actually shipped"}
    story = _synthetic_story("ODM real-series scene", ["f1"], visual=visual)
    scorecard = _synthetic_scorecard("f1", "odmMonthlyAiRevenue", "odm")

    bullets = build_bullets(story, scorecard, {}, REAL_SERIES_DIR)
    b0 = bullets[0]
    assert b0["chart"] is not None
    assert b0["noChartReason"] is None
    assert b0["chart"]["title"] == "Servers actually shipped"
    assert b0["chart"]["unit"] == "%, year over year"
    assert len(b0["chart"]["points"]) == 10  # capped at _MAX_CHART_POINTS
    _assert_bullet_plain_english(b0)
    _validate_bullet_schema(b0)


# ---------------------------------------------------------------------------
# FINAL REVIEW, Important 4 + Minor 7: the no-chart panels' wording.
# ---------------------------------------------------------------------------

def _all_no_chart_reasons() -> list[dict]:
    """Every {reason, cause} dict the builder can produce, gathered by
    calling it directly rather than by re-typing the sentences here."""
    from gpu_agent.dashboard import bullets as bullets_mod
    return [
        bullets_mod._fallback_reason([], "store/series",
                                     saw_non_measurable_unit=False,
                                     saw_missing_title=False),
        bullets_mod._fallback_reason(["nothingTrackedHere"], "store/series",
                                     saw_non_measurable_unit=False,
                                     saw_missing_title=False),
        bullets_mod._fallback_reason(["gpuSpotPrice"], "store/series",
                                     saw_non_measurable_unit=False,
                                     saw_missing_title=False),
        bullets_mod._fallback_reason(["odmMonthlyAiRevenue"], "store/series",
                                     saw_non_measurable_unit=True,
                                     saw_missing_title=False),
        bullets_mod._fallback_reason(["odmMonthlyAiRevenue"], "store/series",
                                     saw_non_measurable_unit=False,
                                     saw_missing_title=True),
        bullets_mod._fallback_reason(["odmMonthlyAiRevenue"], "store/series",
                                     saw_non_measurable_unit=False,
                                     saw_missing_title=False),
    ]


def test_the_estimates_only_reason_talks_about_the_series_we_track_not_the_bullet():
    # The defect: the panel beside a bullet that cited AMD's own press release
    # said "The only numbers HERE are our own estimates, not published facts."
    # True of the series we track; plainly false about the item the reader is
    # looking at. The sentence must be about what WE track, and must not claim
    # anything about the material sitting next to it.
    from gpu_agent.dashboard.bullets import _fallback_reason

    reason = _fallback_reason(["gpuSpotPrice"], "store/series",
                              saw_non_measurable_unit=False,
                              saw_missing_title=False)
    assert reason == {
        "reason": ("The number we track for this is our own estimate, "
                   "not a published figure, so we don't draw it."),
        "cause": "estimate-only",
    }
    assert "here" not in reason["reason"].lower()
    assert "track" in reason["reason"]


def test_no_chart_reason_never_prints_a_double_hyphen():
    # The mock uses an em dash; three of the six reasons were rendering a
    # literal "--" to the reader.
    for reason in _all_no_chart_reasons():
        assert "--" not in reason["reason"], reason


def test_every_no_chart_reason_is_a_plain_english_sentence():
    for reason in _all_no_chart_reasons():
        assert reason["cause"] in (
            "no-published-number", "estimate-only", "no-plain-name", "too-sparse")
        assert reason["reason"].endswith(".")
        assert "DMI" not in reason["reason"] and "SMI" not in reason["reason"]


# ---------------------------------------------------------------------------
# USER DECISION (interactive, 2026-08-07, follow-up to Task 1 review): a
# fourth cause code, "no-plain-name", was added because the original
# three-code mapping put the two "we have the number but can't yet name it"
# branches under "too-sparse" -- false of both, since neither is a density
# problem (the missing-title branch's own reason sentence says "We have
# real, tracked numbers behind this"). Task 2 renders the cause as the
# reader-facing LEAD line, so a mislabelled cause would print a false
# headline. These two tests pin the fix and guard the regression it exists
# to prevent.
# ---------------------------------------------------------------------------

def test_each_of_the_six_fallback_branches_yields_its_own_true_cause():
    # Every branch `_fallback_reason` can take, and the ONE cause code that
    # is true of it -- across all four codes, not just "a valid code".
    reasons = _all_no_chart_reasons()
    expected_causes = [
        "no-published-number",  # no indicator cited at all
        "no-published-number",  # indicator cited, but no rows on disk
        "estimate-only",        # real rows, but all of them our own estimate
        "no-plain-name",        # real published rows, non-measurable raw unit
        "no-plain-name",        # real published rows, no narrator title yet
        "too-sparse",           # real, named, published rows -- just too few
    ]
    assert [r["cause"] for r in reasons] == expected_causes


def test_too_sparse_is_never_returned_except_by_the_genuine_density_branch():
    # THE REGRESSION THIS FIX EXISTS TO PREVENT: `saw_non_measurable_unit`
    # and `saw_missing_title` must never again be labelled "too-sparse" --
    # neither describes a shortage of data points. "too-sparse" may only
    # come from the one branch where neither flag is set and there ARE real,
    # non-estimate, cited rows (the density catch-all).
    from gpu_agent.dashboard.bullets import _fallback_reason

    too_sparse_cases = [
        # (indicator_ids, saw_non_measurable_unit, saw_missing_title)
        ([], False, False),
        (["nothingTrackedHere"], False, False),
        (["gpuSpotPrice"], False, False),
        (["odmMonthlyAiRevenue"], True, False),
        (["odmMonthlyAiRevenue"], False, True),
        (["odmMonthlyAiRevenue"], True, True),
    ]
    for indicator_ids, non_measurable, missing_title in too_sparse_cases:
        result = _fallback_reason(indicator_ids, "store/series",
                                  saw_non_measurable_unit=non_measurable,
                                  saw_missing_title=missing_title)
        if result["cause"] == "too-sparse":
            assert indicator_ids == ["odmMonthlyAiRevenue"]
            assert non_measurable is False and missing_title is False

    # And the genuine density branch really does still produce it.
    density_only = _fallback_reason(["odmMonthlyAiRevenue"], "store/series",
                                    saw_non_measurable_unit=False,
                                    saw_missing_title=False)
    assert density_only["cause"] == "too-sparse"


# ---------------------------------------------------------------------------
# F114 Task 5: the dashboard PREFERS the narrator's own bullets. The
# mechanical condenser above stays on only as the fallback -- for artifacts
# written before this schema existed, and for days the narrator fell back.
# ---------------------------------------------------------------------------

def _artifact_story(bullets, scenes=None):
    """A story artifact carrying narrator-written bullets. Scenes are still
    present (the narrator always writes them) and still carry the visuals
    that name each tracked series in plain English."""
    story = _synthetic_story("Scene one title", [])
    if scenes is not None:
        story["scenes"] = scenes
    story["bullets"] = bullets
    return story


def _three_artifact_bullets():
    return [
        {"text": "AMD's data centre revenue reached US$4.9 billion in the June quarter.",
         "claimFindingIds": ["f1"]},
        {"text": "SpaceX passed 1.4 gigawatts of computing capacity by the end of June.",
         "claimFindingIds": ["f2"]},
        {"text": "Advanced packaging stays booked out through 2027, holding back 3 rivals.",
         "claimFindingIds": ["f3"]},
    ]


def _three_finding_scorecard():
    return {
        "findings": [
            {"id": "f1", "indicatorId": "vendorRevenueGuidance", "entity": "amd",
             "evidence": [{"source": "AMD Investor Relations", "url": "https://ir.amd.com/q2",
                            "date": "2026-08-04", "tier": "primary"}]},
            {"id": "f2", "indicatorId": "someTrackedIndicator", "entity": "spacex",
             "evidence": [{"source": "Investing.com", "url": "https://example.test/spacex",
                            "date": "2026-08-04", "tier": "secondary"}]},
            {"id": "f3", "indicatorId": "pkgCapacityOrderSpread", "entity": "tsmc",
             "evidence": [{"source": "TechSoda via Substack", "url": "https://example.test/pkg",
                            "date": "2026-07-31", "tier": "secondary"}]},
        ]
    }


def test_artifact_bullets_are_used_verbatim(tmp_path):
    # The whole point of F114: the narrator's own sentence reaches the page
    # untouched -- no title prefix, no first-sentence chopping.
    story = _artifact_story(_three_artifact_bullets())
    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path))

    assert [b["text"] for b in bullets] == [b["text"] for b in _three_artifact_bullets()]
    # Not a trace of the mechanical condenser's "<scene title>. <sentence>" shape.
    assert not any(b["text"].startswith("Scene one title.") for b in bullets)


def test_artifact_bullet_sources_come_from_the_bullets_own_finding_ids(tmp_path):
    story = _artifact_story(_three_artifact_bullets())
    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path))

    assert bullets[0]["sources"] == [
        {"title": "AMD Investor Relations", "outlet": "AMD Investor Relations",
         "url": "https://ir.amd.com/q2", "date": "2026-08-04", "tier": "primary"}]
    assert bullets[2]["sources"] == [
        {"title": "TechSoda", "outlet": "Substack",
         "url": "https://example.test/pkg", "date": "2026-07-31", "tier": "secondary"}]


def test_artifact_bullets_keep_the_dashboard_payload_shape(tmp_path):
    story = _artifact_story(_three_artifact_bullets())
    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path))

    assert len(bullets) == 3
    for b in bullets:
        assert set(b.keys()) == {"date", "text", "storyHref", "chart", "noChartReason", "sources"}
        assert (b["chart"] is None) != (b["noChartReason"] is None)
        assert b["date"] == "2026-08-05"
        assert b["storyHref"] == "story/2026-08-05.html"
        _assert_bullet_plain_english(b)
        _validate_bullet_schema(b)


def test_artifact_bullet_hitting_a_curated_series_still_gets_that_chart(tmp_path):
    # Chart matching now keys off the BULLET's own cited findings. Bullet 1
    # cites f1 (entity "amd"), so the curated AMD series must still match.
    story = _artifact_story(_three_artifact_bullets())
    series_reg = {"amdDataCenterRevenue": _series(
        "amdDataCenterRevenue", ["amdDataCenter", "amd"], quality="hard-fact")}
    rows = [_row("amdDataCenterRevenue", f"2025-{m:02d}", 1.0 + m) for m in range(1, 9)]
    _write_jsonl(tmp_path / "amdDataCenterRevenue.jsonl", rows)

    bullets = build_bullets(story, _three_finding_scorecard(), series_reg, str(tmp_path))
    b0 = bullets[0]
    assert b0["chart"] is not None
    assert b0["noChartReason"] is None
    assert b0["chart"]["title"] == "amdDataCenterRevenue"
    assert len(b0["chart"]["points"]) == 8
    # The other two bullets don't cite an "amd" finding, so they must NOT
    # inherit bullet 1's chart -- proof the match is made per bullet.
    assert bullets[1]["chart"] is None and bullets[2]["chart"] is None


def test_artifact_bullet_chart_label_is_found_on_a_different_scene(tmp_path):
    # The Option C decision (user, 2026-08-06): a narrator bullet has no
    # `visual` of its own, so the chart's plain-English title is looked up
    # across the WHOLE story by seriesId equality -- never by pairing bullet
    # i with scene i.
    #
    # Here bullet 2 cites the indicator whose label lives on scene THREE. A
    # positional pairing (bullet 2 <-> scene 2) would find no label at all
    # and fall to an honest no-chart reason. Matching on seriesId finds
    # "Memory factory spending" and charts it.
    scenes = [
        {"n": 1, "title": "Scene one", "paragraphs": ["One. Two."], "claimFindingIds": [],
         "visual": {"kind": "spark", "seriesId": "someOtherIndicator",
                     "label": "A completely different number"}},
        {"n": 2, "title": "Scene two", "paragraphs": ["One. Two."], "claimFindingIds": []},
        {"n": 3, "title": "Scene three", "paragraphs": ["One. Two."], "claimFindingIds": [],
         "visual": {"kind": "spark", "seriesId": "someTrackedIndicator",
                     "label": "Memory factory spending"}},
    ]
    story = _artifact_story(_three_artifact_bullets(), scenes=scenes)
    # Bullet 2 cites f2 -> someTrackedIndicator, labelled only on scene 3.
    rows = [_row("someTrackedIndicator", f"2025-{m:02d}", float(m), unit="USD")
            for m in range(1, 9)]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path))
    b1 = bullets[1]
    assert b1["chart"] is not None, "cross-scene seriesId lookup did not find the label"
    assert b1["chart"]["title"] == "Memory factory spending"
    assert b1["chart"]["title"] != "A completely different number"
    _assert_bullet_plain_english(b1)
    _validate_bullet_schema(b1)


def test_artifact_bullet_with_no_matching_series_id_anywhere_gets_an_honest_no_chart(tmp_path):
    # Same dense, plain-unit history as the test above, but NO scene names
    # this series, so there is no honest plain-English title for it. The
    # bullet must get the honest reason -- never a chart wearing some other
    # series' label, and never a bare indicator code as its title.
    scenes = [
        {"n": 1, "title": "Scene one", "paragraphs": ["One. Two."], "claimFindingIds": [],
         "visual": {"kind": "spark", "seriesId": "someOtherIndicator",
                     "label": "A completely different number"}},
        {"n": 2, "title": "Scene two", "paragraphs": ["One. Two."], "claimFindingIds": []},
        {"n": 3, "title": "Scene three", "paragraphs": ["One. Two."], "claimFindingIds": []},
    ]
    story = _artifact_story(_three_artifact_bullets(), scenes=scenes)
    rows = [_row("someTrackedIndicator", f"2025-{m:02d}", float(m), unit="USD")
            for m in range(1, 9)]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path))
    b1 = bullets[1]
    assert b1["chart"] is None
    assert "no plain-English name for what they measure yet" in b1["noChartReason"]["reason"]
    assert b1["noChartReason"]["cause"] == "no-plain-name"


def test_mechanical_scene_never_borrows_a_label_from_another_scene(tmp_path):
    # The other half of Option C: generalising the lookup must NOT loosen the
    # MECHANICAL path. A scene's chart title still has to come from that
    # scene's own visual. Here scene 1 cites the indicator, but only scene 3
    # names it -- on the mechanical path (no artifact bullets) that must stay
    # an honest no-chart, exactly as it is today.
    story = {
        "storyDate": "2026-08-05",
        "scenes": [
            {"n": 1, "title": "Scene one", "paragraphs": ["One. Two."],
             "claimFindingIds": ["f1"]},
            {"n": 2, "title": "Scene two", "paragraphs": ["One. Two."], "claimFindingIds": []},
            {"n": 3, "title": "Scene three", "paragraphs": ["One. Two."], "claimFindingIds": [],
             "visual": {"kind": "spark", "seriesId": "someTrackedIndicator",
                         "label": "Memory factory spending"}},
        ],
    }
    scorecard = _synthetic_scorecard("f1", "someTrackedIndicator", "market")
    rows = [_row("someTrackedIndicator", f"2025-{m:02d}", float(m), unit="USD")
            for m in range(1, 9)]
    _write_jsonl(tmp_path / "someTrackedIndicator.jsonl", rows)

    bullets = build_bullets(story, scorecard, {}, str(tmp_path))
    assert bullets[0]["chart"] is None
    assert "no plain-English name for what they measure yet" in bullets[0]["noChartReason"]["reason"]
    assert bullets[0]["noChartReason"]["cause"] == "no-plain-name"


def test_story_with_bullets_none_takes_the_mechanical_path(tmp_path):
    # A day the narrator fell back writes the assembler story with no
    # bullets. That must land on the mechanical condenser, unchanged.
    story = _artifact_story(None)
    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path))
    assert bullets[0]["text"] == "Scene one title. First sentence here."


def test_pre_f114_story_without_a_bullets_key_takes_the_mechanical_path(tmp_path):
    # An artifact written before this schema existed has no `bullets` key at
    # all -- not even None. It must still render.
    story = _synthetic_story("Scene one title", [])
    assert "bullets" not in story
    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path))
    assert bullets[0]["text"] == "Scene one title. First sentence here."


def test_story_with_the_wrong_number_of_bullets_takes_the_mechanical_path(tmp_path):
    # The schema requires exactly 3. A malformed artifact carrying 2 must
    # fall back rather than ship a short payload the dashboard can't validate.
    story = _artifact_story(_three_artifact_bullets()[:2])
    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path))
    assert len(bullets) == 3
    assert bullets[0]["text"] == "Scene one title. First sentence here."


# ---------------------------------------------------------------------------
# F113 Task 5: the verified-research step, between the curated match and the
# findings fallback.
#
# A quarantine record only ever reaches the page when it was written for
# TODAY's story and stamped with THIS bullet's index. Everything else about
# it -- a stale date, a chart form the page cannot draw, an index nobody
# asked for -- must leave the day's output exactly as it was before this
# step existed.
# ---------------------------------------------------------------------------

RESEARCH_POINTS = [
    {"label": "Q1 2026", "value": 12.0, "sourceUrl": "https://example.test/mtk-q1",
     "publishedAt": "2026-04-30"},
    {"label": "Q2 2026", "value": 14.5, "sourceUrl": "https://example.test/mtk-q2",
     "publishedAt": "2026-07-31"},
    {"label": "Q3 2026", "value": 15.2, "sourceUrl": "https://example.test/mtk-q3",
     "publishedAt": "2026-08-04"},
]


def _write_quarantine(research_dir: Path, *, date="2026-08-05", bullet_index=1,
                      series_name="MediaTek edge AI shipments", slug_name=None,
                      unit="million units", form="line",
                      source_name="TrendForce", points=None, extra=None) -> Path:
    """One accepted candidate exactly as `verify.accept_research` writes it:
    the CandidateSeries fields verbatim plus the `bulletIndex` stamp."""
    record = {
        "seriesName": series_name,
        "unit": unit,
        "form": form,
        "sourceName": source_name,
        "points": RESEARCH_POINTS if points is None else points,
        "pair": False,
        "notes": "",
        "bulletIndex": bullet_index,
    }
    record.update(extra or {})
    research_dir.mkdir(parents=True, exist_ok=True)
    path = research_dir / f"{date}-{slug_name or 'mediatek-edge-ai-shipments'}.json"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def _research_story():
    """Three narrator bullets, each citing its own finding, so a quarantine
    record can be aimed at one bullet index and proven not to leak onto the
    other two."""
    return _artifact_story(_three_artifact_bullets())


def test_verified_research_charts_a_bullet_with_no_curated_match(tmp_path):
    story = _research_story()
    research_dir = tmp_path / "research-series"
    _write_quarantine(research_dir, bullet_index=1)

    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path / "series"),
                            research_dir=str(research_dir))
    chart = bullets[0]["chart"]
    assert chart is not None
    assert bullets[0]["noChartReason"] is None
    assert chart["researched"] is True
    assert chart["form"] == "line"
    assert chart["title"] == "MediaTek edge AI shipments"
    assert chart["unit"] == "million units"
    assert chart["caption"] == "Found today — single source: TrendForce."
    assert [p["value"] for p in chart["points"]] == [12.0, 14.5, 15.2]
    assert [p["label"] for p in chart["points"]] == ["Q1 2026", "Q2 2026", "Q3 2026"]
    # Every point keeps the exact page its number was re-found on.
    assert [p["sourceUrl"] for p in chart["points"]] == [
        "https://example.test/mtk-q1", "https://example.test/mtk-q2",
        "https://example.test/mtk-q3"]
    assert all(p["hollow"] is False for p in chart["points"])
    _validate_bullet_schema(bullets[0])
    _assert_bullet_plain_english(bullets[0])


def test_verified_research_reaches_only_the_bullet_index_it_was_researched_for(tmp_path):
    story = _research_story()
    research_dir = tmp_path / "research-series"
    _write_quarantine(research_dir, bullet_index=2)

    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path / "series"),
                            research_dir=str(research_dir))
    assert bullets[0]["chart"] is None
    assert bullets[1]["chart"] is not None
    assert bullets[1]["chart"]["researched"] is True
    assert bullets[2]["chart"] is None


def test_verified_research_wins_over_the_findings_fallback(tmp_path):
    """The findings fallback must not even be consulted: bullet 2's own cited
    indicator here has a dense, plainly-named, non-estimate history that DOES
    chart on its own (asserted first, without the research dir), yet the
    researched series is what the reader gets."""
    scenes = _synthetic_story("Scene one title", [])["scenes"]
    scenes[1] = {"n": 2, "title": "Scene two", "paragraphs": ["One. Two."],
                 "claimFindingIds": [],
                 "visual": {"kind": "spark", "seriesId": "someTrackedIndicator",
                             "label": "Memory factory spending"}}
    story = _artifact_story(_three_artifact_bullets(), scenes=scenes)
    series_dir = tmp_path / "series"
    _write_jsonl(series_dir / "someTrackedIndicator.jsonl",
                 [_row("someTrackedIndicator", f"2025-{m:02d}", float(m), unit="USD")
                  for m in range(1, 9)])

    without = build_bullets(story, _three_finding_scorecard(), {}, str(series_dir))
    assert without[1]["chart"] is not None
    assert without[1]["chart"]["title"] == "Memory factory spending"
    assert without[1]["chart"]["researched"] is False

    research_dir = tmp_path / "research-series"
    _write_quarantine(research_dir, bullet_index=2)
    with_research = build_bullets(story, _three_finding_scorecard(), {}, str(series_dir),
                                  research_dir=str(research_dir))
    assert with_research[1]["chart"]["researched"] is True
    assert with_research[1]["chart"]["title"] == "MediaTek edge AI shipments"
    # The fallback's own assessment-style source never appears.
    assert with_research[1]["chart"]["source"].get("assessment") is None


def test_a_curated_match_still_beats_a_researched_series(tmp_path):
    story = _synthetic_story("AMD scene title", ["f1"])
    scorecard = _synthetic_scorecard("f1", "vendorRevenueGuidance", "amd")
    series_reg = {"amdDataCenterRevenue": _series(
        "amdDataCenterRevenue", ["amdDataCenter", "amd"], quality="hard-fact")}
    series_dir = tmp_path / "series"
    _write_jsonl(series_dir / "amdDataCenterRevenue.jsonl",
                 [_row("amdDataCenterRevenue", f"2025-{m:02d}", 1.0 + m) for m in range(1, 9)])
    research_dir = tmp_path / "research-series"
    _write_quarantine(research_dir, bullet_index=1)

    bullets = build_bullets(story, scorecard, series_reg, str(series_dir),
                            research_dir=str(research_dir))
    assert bullets[0]["chart"]["researched"] is False
    assert bullets[0]["chart"]["title"] == "amdDataCenterRevenue"


def test_a_quarantine_file_from_another_story_date_is_ignored(tmp_path):
    """Yesterday's researched series is not today's news. The story date is
    the only date these records carry, so a stale file must never be drawn."""
    story = _research_story()
    assert story["storyDate"] == "2026-08-05"
    research_dir = tmp_path / "research-series"
    _write_quarantine(research_dir, date="2026-08-04", bullet_index=1)

    with_stale = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path / "series"),
                               research_dir=str(research_dir))
    without = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path / "series"))
    assert with_stale == without
    assert with_stale[0]["chart"] is None


def test_no_quarantine_file_leaves_the_days_bullets_byte_identical(tmp_path):
    """The whole point of the guard: on a day the researcher found nothing,
    the page must be exactly what it was before this step existed."""
    story = _research_story()
    series_dir = tmp_path / "series"
    _write_jsonl(series_dir / "someTrackedIndicator.jsonl",
                 [_row("someTrackedIndicator", f"2025-{m:02d}", float(m), unit="USD")
                  for m in range(1, 9)])
    empty_dir = tmp_path / "research-series"
    empty_dir.mkdir()

    baseline = build_bullets(story, _three_finding_scorecard(), {}, str(series_dir))
    assert baseline == build_bullets(story, _three_finding_scorecard(), {}, str(series_dir),
                                     research_dir=str(empty_dir))
    # A research directory that was never created at all behaves the same.
    assert baseline == build_bullets(story, _three_finding_scorecard(), {}, str(series_dir),
                                     research_dir=str(tmp_path / "nope"))


def test_a_quarantine_record_with_an_undrawable_form_is_ignored(tmp_path):
    """The chart forms the page can draw are fixed. A record naming anything
    else is skipped quietly -- never passed through to fail schema validation
    and take the whole day's dashboard down with it."""
    story = _research_story()
    research_dir = tmp_path / "research-series"
    _write_quarantine(research_dir, bullet_index=1, form="pie")

    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path / "series"),
                            research_dir=str(research_dir))
    assert bullets[0]["chart"] is None
    assert bullets[0]["noChartReason"] is not None


def test_an_unreadable_quarantine_file_is_ignored(tmp_path):
    """Text that isn't valid JSON."""
    story = _research_story()
    research_dir = tmp_path / "research-series"
    research_dir.mkdir(parents=True)
    (research_dir / "2026-08-05-broken.json").write_text("{not json", encoding="utf-8")

    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path / "series"),
                            research_dir=str(research_dir))
    assert bullets[0]["chart"] is None


def test_a_quarantine_file_of_corrupt_bytes_is_ignored(tmp_path):
    """Bytes that are not valid UTF-8 at all -- a truncated write, a disk
    fault, a file that arrived through something other than the verifier.

    Distinct from the bad-JSON case above: decoding fails BEFORE the JSON
    parser is ever reached, so a handler that only catches JSON errors lets
    the failure escape and takes the whole day's dashboard export down with
    it. A quarantine record is never worth a blank page.
    """
    story = _research_story()
    research_dir = tmp_path / "research-series"
    research_dir.mkdir(parents=True)
    # 0xFF is not a legal UTF-8 byte in any position.
    (research_dir / "2026-08-05-corrupt.json").write_bytes(b'{"seriesName": "\xff\xfe\x00bad"}')
    # ...and a good record for another bullet still comes through, so this
    # proves the bad file is SKIPPED, not that the whole step gave up.
    _write_quarantine(research_dir, bullet_index=2)

    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path / "series"),
                            research_dir=str(research_dir))
    assert bullets[0]["chart"] is None
    assert bullets[1]["chart"] is not None
    assert bullets[1]["chart"]["researched"] is True


def test_a_true_bullet_index_does_not_pass_for_bullet_one(tmp_path):
    """In Python `True == 1`, so a record carrying `bulletIndex: true` would
    quietly match bullet 1 on a plain equality check. The verifier always
    writes a real integer taken from the answer filename, so a boolean means
    the record came from somewhere else -- and a chart on the page is too
    strong a claim to hang on an accident of how Python compares types."""
    story = _research_story()
    research_dir = tmp_path / "research-series"
    _write_quarantine(research_dir, extra={"bulletIndex": True})

    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path / "series"),
                            research_dir=str(research_dir))
    assert all(b["chart"] is None for b in bullets)


def test_a_floating_point_bullet_index_does_not_pass_either(tmp_path):
    story = _research_story()
    research_dir = tmp_path / "research-series"
    _write_quarantine(research_dir, extra={"bulletIndex": 1.0})

    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path / "series"),
                            research_dir=str(research_dir))
    assert all(b["chart"] is None for b in bullets)


def test_a_quarantine_record_with_no_bullet_index_is_ignored(tmp_path):
    """`accept_research` stamps every record it writes, so a record without
    one did not come through the trust gate -- it is not trusted here."""
    story = _research_story()
    research_dir = tmp_path / "research-series"
    _write_quarantine(research_dir, extra={"bulletIndex": None})

    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path / "series"),
                            research_dir=str(research_dir))
    assert all(b["chart"] is None for b in bullets)


def test_the_researched_chart_names_its_single_source_and_links_to_it(tmp_path):
    story = _research_story()
    research_dir = tmp_path / "research-series"
    _write_quarantine(research_dir, bullet_index=1)

    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path / "series"),
                            research_dir=str(research_dir))
    source = bullets[0]["chart"]["source"]
    assert source["outlet"] == "TrendForce"
    assert source["title"] == "MediaTek edge AI shipments"
    # The link and the date must describe the same page. Review finding: the
    # url came from the FIRST point and the date from the LAST, so the popover
    # dated a page by a different page's publication date.
    assert source["url"] == "https://example.test/mtk-q3"
    assert source["date"] == "2026-08-04"
    last_point = RESEARCH_POINTS[-1]
    assert source["url"] == last_point["sourceUrl"]
    assert source["date"] == last_point["publishedAt"]


def test_a_researched_series_longer_than_the_chart_cap_keeps_its_latest_points(tmp_path):
    story = _research_story()
    points = [{"label": f"M{i}", "value": float(i),
               "sourceUrl": "https://example.test/long", "publishedAt": "2026-08-01"}
              for i in range(1, 15)]
    research_dir = tmp_path / "research-series"
    _write_quarantine(research_dir, bullet_index=1, points=points)

    bullets = build_bullets(story, _three_finding_scorecard(), {}, str(tmp_path / "series"),
                            research_dir=str(research_dir))
    chart = bullets[0]["chart"]
    assert len(chart["points"]) == _MAX_CHART_POINTS
    assert chart["points"][-1]["label"] == "M14"


def test_the_researched_chart_matches_what_accept_research_actually_writes(tmp_path):
    """Cross-task contract: the file this step reads is produced by
    `verify.accept_research`, so the shape under test is taken from that
    writer rather than from a hand-written guess about it."""
    from gpu_agent.chartdata.research import CandidateSeries

    cand = CandidateSeries(
        seriesName="MediaTek edge AI shipments", unit="million units", form="line",
        sourceName="TrendForce", points=RESEARCH_POINTS,
    ).model_copy(update={"bulletIndex": 1})
    research_dir = tmp_path / "research-series"
    research_dir.mkdir(parents=True)
    (research_dir / "2026-08-05-mediatek-edge-ai-shipments.json").write_text(
        cand.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")

    bullets = build_bullets(_research_story(), _three_finding_scorecard(), {},
                            str(tmp_path / "series"), research_dir=str(research_dir))
    assert bullets[0]["chart"] is not None
    assert bullets[0]["chart"]["researched"] is True
    assert bullets[0]["chart"]["caption"] == "Found today — single source: TrendForce."
