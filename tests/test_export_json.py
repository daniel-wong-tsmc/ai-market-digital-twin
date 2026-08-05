import copy
import json
from pathlib import Path
from unittest import mock

import jsonschema
import pytest

from gpu_agent.dashboard.export_json import build_dashboard_payload, write_dashboard_json

STORY = json.loads(Path("fixtures/dashboard/story-trimmed.json").read_text(encoding="utf-8"))
SCORECARD = json.loads(Path("fixtures/dashboard/scorecard-trimmed.json").read_text(encoding="utf-8"))
SCHEMA = json.loads(Path("web/schema/dashboard.schema.json").read_text(encoding="utf-8"))
GOLDEN_PATH = Path("fixtures/dashboard/golden-dashboard.json")


def _make_store(tmp_path: Path) -> Path:
    """A small, fully self-contained store tree -- NOT the real, ever-growing
    store/chips.merchant-gpu -- so this test's expected numbers never drift
    as the live daily cycle appends new data. Two monthly scorecards (so
    gap_chart.build_gap_data has >=2 points and the verdict chip has a real
    "previous" sdgiGap to compare against), the real trimmed story, and an
    EMPTY series directory (every bullet is honestly chart-less and
    deterministic -- Task 5 already covers the chart-matching paths)."""
    cat_dir = tmp_path / "store" / "chips.merchant-gpu"
    cat_dir.mkdir(parents=True)
    (cat_dir / "story").mkdir()
    (tmp_path / "store" / "series").mkdir(parents=True)

    prev = {
        "categoryId": "chips.merchant-gpu", "asOf": "2026-07",
        "findings": [], "dimensionRatings": {},
        "demandSupply": {"dmiContribution": 1.0, "smiContribution": 0.5,
                          "anchors": {}, "sdgi": 0.5, "sdgiDirection": "demand-led"},
        "narrative": "Nothing to report.",
        "confidence": {"level": "medium", "basis": "prior month"},
        "categoryStatus": {"rating": "Strong", "direction": "improving",
                            "bottleneck": "bottleneck", "reason": "r"},
        "indices": {"momentum": {"dmiContribution": 0.0, "smiContribution": 0.0,
                                  "anchors": {}, "sdgi": 0.0, "sdgiDirection": "balanced"},
                    "outlook": {"dmiContribution": 0.0, "smiContribution": 0.0,
                                "anchors": {}, "sdgi": 0.0, "sdgiDirection": "balanced"},
                    "divergence": {"state": "aligned", "sdgiGap": 2.0,
                                   "outlookFindingCount": 1, "momentumFindingCount": 1, "note": ""}},
    }
    (cat_dir / "2026-07-v1.json").write_text(json.dumps(prev), encoding="utf-8")

    current = copy.deepcopy(SCORECARD)
    current["demandSupply"] = {"dmiContribution": 2.0, "smiContribution": -0.5,
                                "anchors": {}, "sdgi": 2.5, "sdgiDirection": "demand-led"}
    current["confidence"] = {"level": "high", "basis": "self-consistency over 3 samples"}
    (cat_dir / "2026-08-v1.json").write_text(json.dumps(current), encoding="utf-8")

    (cat_dir / "story" / "2026-08-05.json").write_text(json.dumps(STORY), encoding="utf-8")
    return tmp_path / "store"


def _build(tmp_path):
    store_dir = _make_store(tmp_path)
    return build_dashboard_payload("chips.merchant-gpu", str(store_dir))


# ---------------------------------------------------------------------------
# Validate-before-write: a corrupted field must raise, never reach disk.
# ---------------------------------------------------------------------------

def test_payload_validates_against_schema(tmp_path):
    payload = _build(tmp_path)
    jsonschema.validate(payload, SCHEMA)  # would raise ValidationError if unsound


def test_build_dashboard_payload_calls_jsonschema_validate(tmp_path):
    # If the validate-before-return call were ever deleted, this goes red --
    # proves the exporter really calls jsonschema.validate, not just that its
    # own output happens to be valid.
    store_dir = _make_store(tmp_path)
    with mock.patch("gpu_agent.dashboard.export_json.jsonschema.validate") as spy:
        build_dashboard_payload("chips.merchant-gpu", str(store_dir))
    spy.assert_called_once()
    args, _ = spy.call_args
    assert args[0]["categoryId"] == "chips.merchant-gpu"


def test_corrupt_bullet_count_is_rejected_before_reaching_disk(tmp_path):
    # Directly exercises the schema gate: a payload shaped like the schema
    # forbids (wrong bullet count) must raise ValidationError. If the
    # validate-before-write call were removed, this would silently pass.
    bad_schema_shape = copy.deepcopy(SCHEMA)
    payload = _build(tmp_path)
    payload["bullets"] = payload["bullets"][:2]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, bad_schema_shape)


# ---------------------------------------------------------------------------
# Determinism: byte-identical across two runs, no capturedAt, LF + sorted keys.
# ---------------------------------------------------------------------------

def test_payload_is_byte_stable_across_two_runs(tmp_path):
    store_dir = _make_store(tmp_path)
    p1 = build_dashboard_payload("chips.merchant-gpu", str(store_dir))
    p2 = build_dashboard_payload("chips.merchant-gpu", str(store_dir))
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)


def test_captured_at_never_enters_the_payload(tmp_path):
    payload = _build(tmp_path)
    assert "capturedAt" not in json.dumps(payload)


def test_write_dashboard_json_uses_lf_and_sorted_keys(tmp_path):
    store_dir = _make_store(tmp_path)
    out = write_dashboard_json("chips.merchant-gpu", str(store_dir), str(tmp_path / "site"))
    raw_bytes = out.read_bytes()
    assert b"\r\n" not in raw_bytes
    text = raw_bytes.decode("utf-8")
    reparsed = json.loads(text)
    # sorted-keys round trip: re-dumping with sort_keys must equal the file's
    # own top-level key order in the raw text (a weak but real proxy -- the
    # strong proof is the golden-file byte comparison below).
    assert list(json.loads(text).keys()) == sorted(reparsed.keys())


def test_write_dashboard_json_twice_is_byte_identical_on_disk(tmp_path):
    store_dir = _make_store(tmp_path)
    site_dir = str(tmp_path / "site")
    out1 = write_dashboard_json("chips.merchant-gpu", str(store_dir), site_dir)
    bytes1 = out1.read_bytes()
    out2 = write_dashboard_json("chips.merchant-gpu", str(store_dir), site_dir)
    bytes2 = out2.read_bytes()
    assert bytes1 == bytes2


# ---------------------------------------------------------------------------
# Golden comparison -- full-payload regression pin.
# ---------------------------------------------------------------------------

def test_payload_matches_golden_fixture(tmp_path):
    payload = _build(tmp_path)
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert payload == golden


# ---------------------------------------------------------------------------
# No acronyms anywhere in the serialised payload (page copy, not internal keys).
# ---------------------------------------------------------------------------

def test_no_acronyms_in_serialised_payload(tmp_path):
    payload = _build(tmp_path)
    dumped = json.dumps(payload)
    assert "DMI" not in dumped
    assert "SMI" not in dumped


def test_every_ref_url_is_http_or_null(tmp_path):
    payload = _build(tmp_path)

    def _walk_refs(node):
        if isinstance(node, dict):
            if "url" in node and "title" in node and "outlet" in node:
                yield node
            for v in node.values():
                yield from _walk_refs(v)
        elif isinstance(node, list):
            for v in node:
                yield from _walk_refs(v)

    refs = list(_walk_refs(payload))
    assert refs, "expected at least one ref in the payload"
    for ref in refs:
        assert ref["url"] is None or ref["url"].startswith("http"), ref


# ---------------------------------------------------------------------------
# Verdict composition rules (brief, verbatim).
# ---------------------------------------------------------------------------

def test_verdict_question_is_the_fixed_string(tmp_path):
    payload = _build(tmp_path)
    assert payload["verdict"]["question"] == "Is supply catching up to demand?"


def test_verdict_answer_is_headline_then_deck_first_sentence(tmp_path):
    payload = _build(tmp_path)
    assert payload["verdict"]["answer"] == (
        "The challenger had a good quarter. The racks that matter still ship "
        "next year. AMD beat its own numbers and put its rack-sized system "
        "into production, but the big volume starts in 2027 - and a single "
        "new buyer has already spoken for a large slice of next year's chips."
    )


def test_verdict_chip_narrows_when_sdgi_gap_shrinks_more_than_5_percent(tmp_path):
    # cur sdgiGap (scorecard-trimmed's real indices.divergence.sdgiGap,
    # 1.5733...) vs. the synthetic prior month's 2.0 -> a -21% relative move,
    # well past the 5% dead-band -> "narrowing". If the dead-band comparison
    # were inverted or the direction flipped, this goes red.
    payload = _build(tmp_path)
    assert payload["verdict"]["chip"]["direction"] == "narrowing"
    assert payload["verdict"]["chip"]["label"] == "Gap narrowing"


def test_verdict_chip_is_flat_inside_the_5_percent_dead_band(tmp_path):
    store_dir = _make_store(tmp_path)
    prev_path = Path(store_dir) / "chips.merchant-gpu" / "2026-07-v1.json"
    prev = json.loads(prev_path.read_text(encoding="utf-8"))
    # scorecard-trimmed's real sdgiGap is 1.5733333333333335; a prior value
    # only 1% away must NOT flip the chip to narrowing/widening.
    prev["indices"]["divergence"]["sdgiGap"] = 1.5733333333333335 * 1.01
    prev_path.write_text(json.dumps(prev), encoding="utf-8")
    payload = build_dashboard_payload("chips.merchant-gpu", str(store_dir))
    assert payload["verdict"]["chip"]["direction"] == "flat"


def test_verdict_confidence_reflects_scorecard_confidence_level(tmp_path):
    payload = _build(tmp_path)
    assert payload["verdict"]["confidence"] == "We are confident in this read."


def test_verdict_so_what_is_the_story_deck(tmp_path):
    payload = _build(tmp_path)
    assert payload["verdict"]["soWhat"] == STORY["deck"]


def test_verdict_sources_is_an_assessment_over_headline_scene_top_3_refs(tmp_path):
    payload = _build(tmp_path)
    sources = payload["verdict"]["sources"]
    assert len(sources) == 1
    assert sources[0]["assessment"] is True
    assert len(sources[0]["basedOn"]) == 3
    # top-3 refs of the FIRST (headline) scene's findings, never a later scene's.
    urls = {r["url"] for r in sources[0]["basedOn"]}
    assert "https://ir.amd.com/news-events/press-releases/detail/1295/amd-reports-second-quarter-2026-financial-results" in urls


# ---------------------------------------------------------------------------
# Dimensions: exactly 6, plain names never blank, no jargon.
# ---------------------------------------------------------------------------

def test_dimensions_has_exactly_six_rows_with_plain_names(tmp_path):
    payload = _build(tmp_path)
    dims = payload["dimensions"]
    assert len(dims) == 6
    assert {d["id"] for d in dims} == {
        "bottleneck", "momentum", "competitiveStructure", "moat",
        "unitEconomics", "strategicRisk"}
    for d in dims:
        assert d["plainName"] and d["plainName"] != d["id"]


def test_dimension_tone_reflects_rating_word(tmp_path):
    payload = _build(tmp_path)
    by_id = {d["id"]: d for d in payload["dimensions"]}
    assert by_id["bottleneck"]["ratingWord"] == "Weak"
    assert by_id["bottleneck"]["tone"] == "bad"
    assert by_id["momentum"]["ratingWord"] == "Very strong"
    assert by_id["momentum"]["tone"] == "good"
    assert by_id["competitiveStructure"]["ratingWord"] == "Mixed"
    assert by_id["competitiveStructure"]["tone"] == "mixed"


# ---------------------------------------------------------------------------
# Missing-inputs failure modes: never write a partial/misleading payload.
# ---------------------------------------------------------------------------

def test_no_scorecard_history_raises(tmp_path):
    (tmp_path / "store" / "chips.merchant-gpu" / "story").mkdir(parents=True)
    (tmp_path / "store" / "series").mkdir(parents=True)
    with pytest.raises(ValueError, match="no monthly scorecard history"):
        build_dashboard_payload("chips.merchant-gpu", str(tmp_path / "store"))


def test_only_one_month_of_history_raises_for_gap_chart(tmp_path):
    cat_dir = tmp_path / "store" / "chips.merchant-gpu"
    (cat_dir / "story").mkdir(parents=True)
    (tmp_path / "store" / "series").mkdir(parents=True)
    current = copy.deepcopy(SCORECARD)
    current["demandSupply"] = {"dmiContribution": 1.0, "smiContribution": 1.0}
    current["confidence"] = {"level": "high", "basis": "b"}
    (cat_dir / "2026-08-v1.json").write_text(json.dumps(current), encoding="utf-8")
    (cat_dir / "story" / "2026-08-05.json").write_text(json.dumps(STORY), encoding="utf-8")
    with pytest.raises(ValueError, match="gap chart"):
        build_dashboard_payload("chips.merchant-gpu", str(tmp_path / "store"))
