import copy
import json
from pathlib import Path
from unittest import mock

import jsonschema
import pytest

from gpu_agent.dashboard.export_json import (
    _ANSWER_OPENING, _CHIP_LABEL, _GAP_WORD_CAPTION,
    build_dashboard_payload, write_dashboard_json,
)

STORY = json.loads(Path("fixtures/dashboard/story-trimmed.json").read_text(encoding="utf-8"))
SCORECARD = json.loads(Path("fixtures/dashboard/scorecard-trimmed.json").read_text(encoding="utf-8"))
SCHEMA = json.loads(Path("web/schema/dashboard.schema.json").read_text(encoding="utf-8"))
GOLDEN_PATH = Path("fixtures/dashboard/golden-dashboard.json")

# The distinctive word each caption direction is keyed by -- used to prove
# the chip and the caption never disagree.
_CAPTION_WORD = {"widening": "widened", "narrowing": "narrowed", "flat": "held roughly steady"}


def _make_store(tmp_path: Path, *, prev_dmi=2.0, prev_smi=-1.0,
                 cur_dmi=2.0, cur_smi=-0.6) -> Path:
    """A small, fully self-contained store tree -- NOT the real, ever-growing
    store/chips.merchant-gpu -- so this test's expected numbers never drift
    as the live daily cycle appends new data. Two monthly scorecards (real
    per-reading demand/supply values -- gap_chart.build_reading_series
    reads these AS REPORTED, never cumulative-summed), the real trimmed
    story, and an EMPTY series directory (every bullet is honestly
    chart-less and deterministic -- Task 5 already covers the chart-
    matching paths)."""
    cat_dir = tmp_path / "store" / "chips.merchant-gpu"
    cat_dir.mkdir(parents=True)
    (cat_dir / "story").mkdir()
    (tmp_path / "store" / "series").mkdir(parents=True)

    prev = {
        "categoryId": "chips.merchant-gpu", "asOf": "2026-07",
        "findings": [], "dimensionRatings": {},
        "demandSupply": {"dmiContribution": prev_dmi, "smiContribution": prev_smi,
                          "anchors": {}, "sdgi": prev_dmi - prev_smi, "sdgiDirection": "demand-led"},
        "narrative": "Nothing to report.",
        "confidence": {"level": "medium", "basis": "prior month"},
        "categoryStatus": {"rating": "Strong", "direction": "improving",
                            "bottleneck": "bottleneck", "reason": "r"},
    }
    (cat_dir / "2026-07-v1.json").write_text(json.dumps(prev), encoding="utf-8")

    current = copy.deepcopy(SCORECARD)
    current["demandSupply"] = {"dmiContribution": cur_dmi, "smiContribution": cur_smi,
                                "anchors": {}, "sdgi": cur_dmi - cur_smi, "sdgiDirection": "demand-led"}
    current["confidence"] = {"level": "high", "basis": "self-consistency over 3 samples"}
    (cat_dir / "2026-08-v1.json").write_text(json.dumps(current), encoding="utf-8")

    (cat_dir / "story" / "2026-08-05.json").write_text(json.dumps(STORY), encoding="utf-8")
    return tmp_path / "store"


def _build(tmp_path, **kw):
    store_dir = _make_store(tmp_path, **kw)
    return build_dashboard_payload("chips.merchant-gpu", str(store_dir))


# ---------------------------------------------------------------------------
# CRITICAL 1: the chip and the chart caption must agree -- always, because
# they are now the SAME computation over the SAME plotted series.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prev_dmi,prev_smi,cur_dmi,cur_smi,expected_direction", [
    (2.0, -1.0, 2.0, -0.6, "narrowing"),  # gap 3.0 -> 2.6, a 13% shrink
    (1.0, 0.0, 3.0, -1.0, "widening"),    # gap 1.0 -> 4.0, more than doubles
    (1.0, 0.0, 1.02, 0.0, "flat"),        # gap 1.0 -> 1.02, inside the 5% band
])
def test_chip_and_caption_direction_always_agree(tmp_path, prev_dmi, prev_smi,
                                                  cur_dmi, cur_smi, expected_direction):
    # MINOR (review round 1): the golden fixture alone only ever exercised
    # the "widened" branch -- this covers all three, directly.
    payload = _build(tmp_path, prev_dmi=prev_dmi, prev_smi=prev_smi,
                      cur_dmi=cur_dmi, cur_smi=cur_smi)
    chip_direction = payload["verdict"]["chip"]["direction"]
    caption = payload["gapChart"]["caption"]
    assert chip_direction == expected_direction
    assert payload["verdict"]["chip"]["label"] == _CHIP_LABEL[expected_direction]
    assert _CAPTION_WORD[expected_direction] in caption
    for other, word in _CAPTION_WORD.items():
        if other != expected_direction:
            assert word not in caption


def test_chip_and_caption_agree_on_the_real_committed_store():
    # Driven from the real, live store/chips.merchant-gpu -- the exact case
    # review round 1 found contradicting itself ("Gap narrowing" chip over
    # a "gap widened" caption, against real points visibly widening).
    payload = build_dashboard_payload("chips.merchant-gpu", "store")
    direction = payload["verdict"]["chip"]["direction"]
    caption = payload["gapChart"]["caption"]
    assert _CAPTION_WORD[direction] in caption
    for other, word in _CAPTION_WORD.items():
        if other != direction:
            assert word not in caption


def test_gap_chart_points_are_raw_readings_not_cumulative_index(tmp_path):
    # IMPORTANT 5 (review round 1, controller ruling): points are the real
    # per-reading demandSupply values AS REPORTED -- never a cumulative sum
    # indexed to 100 (the OLD, unrelated gap_chart.build_gap_data shape).
    # If someone reverted to that shape, these would read 100+, not the raw
    # small numbers below.
    payload = _build(tmp_path, prev_dmi=2.0, prev_smi=-1.0, cur_dmi=2.0, cur_smi=-0.6)
    points = payload["gapChart"]["points"]
    assert points == [
        {"date": "2026-07", "demand": 2.0, "supply": -1.0},
        {"date": "2026-08", "demand": 2.0, "supply": -0.6},
    ]


# ---------------------------------------------------------------------------
# CRITICAL 2: validate-before-write, proven against an INPUT corruption
# (never a mocked-out validator), and proven to bite via ordering reversal.
# ---------------------------------------------------------------------------

def _corrupt_url_in_place(store_dir: Path) -> None:
    """Corrupts one evidence url (a real finding cited by the headline
    scene, so it is guaranteed to reach verdict.sources) to a non-string,
    non-null value -- something the schema forbids but nothing upstream of
    jsonschema.validate rejects on its own."""
    current_path = Path(store_dir) / "chips.merchant-gpu" / "2026-08-v1.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    for f in current["findings"]:
        if f["id"] == "finance-yahoo-com-171fe64e-2026-08-1":
            f["evidence"][0]["url"] = 12345
            break
    else:
        raise AssertionError("expected finding not present in the fixture")
    current_path.write_text(json.dumps(current), encoding="utf-8")


def test_corrupt_input_leaves_no_file_on_disk(tmp_path):
    store_dir = _make_store(tmp_path)
    _corrupt_url_in_place(store_dir)
    site_dir = tmp_path / "site"
    with pytest.raises(jsonschema.ValidationError):
        write_dashboard_json("chips.merchant-gpu", str(store_dir), str(site_dir))
    assert not (site_dir / "chips.merchant-gpu" / "data" / "dashboard.json").exists()


def test_build_dashboard_payload_calls_jsonschema_validate(tmp_path):
    store_dir = _make_store(tmp_path)
    with mock.patch("gpu_agent.dashboard.export_json.jsonschema.validate") as spy:
        build_dashboard_payload("chips.merchant-gpu", str(store_dir))
    spy.assert_called_once()
    args, _ = spy.call_args
    assert args[0]["categoryId"] == "chips.merchant-gpu"


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
    assert list(json.loads(text).keys()) == sorted(reparsed.keys())


def test_write_dashboard_json_twice_is_byte_identical_on_disk(tmp_path):
    store_dir = _make_store(tmp_path)
    site_dir = str(tmp_path / "site")
    out1 = write_dashboard_json("chips.merchant-gpu", str(store_dir), site_dir)
    bytes1 = out1.read_bytes()
    out2 = write_dashboard_json("chips.merchant-gpu", str(store_dir), site_dir)
    bytes2 = out2.read_bytes()
    assert bytes1 == bytes2


def test_schema_path_resolves_regardless_of_working_directory(tmp_path, monkeypatch):
    # MINOR (review round 1): SCHEMA_PATH used to be a relative string,
    # which only resolved from the repo root -- this WILL bite the
    # run-cycle and integration tasks. Prove the resolved path is absolute
    # (survives any CWD) and still points at the real schema file, from a
    # CWD that has nothing else the repo needs.
    from gpu_agent.dashboard.export_json import SCHEMA_PATH
    assert SCHEMA_PATH.is_absolute()
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == SCHEMA


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
# CRITICAL 3: the verdict answer leads with a short, direct, chip-consistent
# answer, then exactly one supporting sentence -- never a 51-word paragraph,
# never a soWhat duplicate.
# ---------------------------------------------------------------------------

def test_verdict_question_is_the_fixed_string(tmp_path):
    payload = _build(tmp_path)
    assert payload["verdict"]["question"] == "Is supply catching up to demand?"


def test_verdict_answer_leads_with_a_direct_phrase_then_one_sentence(tmp_path):
    payload = _build(tmp_path)
    assert payload["verdict"]["answer"] == (
        "Getting closer. The challenger had a good quarter."
    )


@pytest.mark.parametrize("prev_dmi,prev_smi,cur_dmi,cur_smi,expected_opening", [
    (2.0, -1.0, 2.0, -0.6, "Getting closer."),
    (1.0, 0.0, 3.0, -1.0, "Not yet."),
    (1.0, 0.0, 1.02, 0.0, "Not yet."),
])
def test_verdict_answer_opening_is_consistent_with_the_chip(tmp_path, prev_dmi, prev_smi,
                                                             cur_dmi, cur_smi, expected_opening):
    payload = _build(tmp_path, prev_dmi=prev_dmi, prev_smi=prev_smi,
                      cur_dmi=cur_dmi, cur_smi=cur_smi)
    direction = payload["verdict"]["chip"]["direction"]
    assert payload["verdict"]["answer"].startswith(_ANSWER_OPENING[direction])
    assert payload["verdict"]["answer"].startswith(expected_opening)


def test_verdict_answer_is_short(tmp_path):
    # Review round 1: the prior 51-word answer opened with AMD's quarter
    # instead of answering, and its last sentence was repeated verbatim in
    # soWhat. Bound it well clear of that failure mode.
    payload = _build(tmp_path)
    word_count = len(payload["verdict"]["answer"].split())
    assert word_count <= 25, payload["verdict"]["answer"]


def test_so_what_never_repeats_a_sentence_from_answer(tmp_path):
    payload = _build(tmp_path)
    answer, so_what = payload["verdict"]["answer"], payload["verdict"]["soWhat"]
    assert so_what not in answer
    assert answer not in so_what


def test_so_what_falls_back_when_deck_would_duplicate_the_support_sentence(tmp_path):
    # Direct exercise of the dedup guard itself: with NO headline, the
    # answer's support sentence falls back to the deck's own first sentence
    # -- so a soWhat that just returns the deck unconditionally (the
    # pre-fix behaviour) would duplicate it exactly. soWhat must instead
    # fall back to the scorecard narrative's first sentence.
    store_dir = _make_store(tmp_path)
    story_path = Path(store_dir) / "chips.merchant-gpu" / "story" / "2026-08-05.json"
    story = json.loads(story_path.read_text(encoding="utf-8"))
    story["headline"] = ""
    story["deck"] = "Only one sentence here that would otherwise duplicate."
    story_path.write_text(json.dumps(story), encoding="utf-8")
    payload = build_dashboard_payload("chips.merchant-gpu", str(store_dir))
    answer, so_what = payload["verdict"]["answer"], payload["verdict"]["soWhat"]
    assert "Only one sentence here that would otherwise duplicate." in answer
    assert so_what != "Only one sentence here that would otherwise duplicate."
    assert so_what not in answer
    # Sentence-level check: no individual sentence of soWhat is a verbatim
    # substring of answer (the specific bug review round 1 found -- the
    # deck's whole single sentence WAS the answer's final sentence).
    for sentence in so_what.split(". "):
        sentence = sentence.strip()
        if sentence:
            assert sentence not in answer, sentence


def test_verdict_confidence_reflects_scorecard_confidence_level(tmp_path):
    payload = _build(tmp_path)
    assert payload["verdict"]["confidence"] == "We are confident in this read"
    assert not payload["verdict"]["confidence"].endswith(".")


def test_verdict_sources_is_an_assessment_over_headline_scene_top_3_refs(tmp_path):
    payload = _build(tmp_path)
    sources = payload["verdict"]["sources"]
    assert len(sources) == 1
    assert sources[0]["assessment"] is True
    assert len(sources[0]["basedOn"]) == 3
    urls = {r["url"] for r in sources[0]["basedOn"]}
    assert "https://ir.amd.com/news-events/press-releases/detail/1295/amd-reports-second-quarter-2026-financial-results" in urls


def test_verdict_sources_is_empty_list_when_nothing_resolves(tmp_path):
    # MINOR (review round 1): an unresolvable headline scene must yield an
    # honest empty sources list, never "our assessment, based on:" with
    # nothing behind it.
    store_dir = _make_store(tmp_path)
    story_path = Path(store_dir) / "chips.merchant-gpu" / "story" / "2026-08-05.json"
    story = json.loads(story_path.read_text(encoding="utf-8"))
    story["scenes"][0]["claimFindingIds"] = ["nonexistent-finding-id"]
    story_path.write_text(json.dumps(story), encoding="utf-8")
    payload = build_dashboard_payload("chips.merchant-gpu", str(store_dir))
    assert payload["verdict"]["sources"] == []


# ---------------------------------------------------------------------------
# IMPORTANT 4: gapChart.sources is a real assessment ref, not an empty list.
# ---------------------------------------------------------------------------

def test_gap_chart_sources_is_assessment_over_dimension_findings(tmp_path):
    payload = _build(tmp_path)
    sources = payload["gapChart"]["sources"]
    assert len(sources) == 1
    assert sources[0]["assessment"] is True
    assert len(sources[0]["basedOn"]) == 3
    for ref in sources[0]["basedOn"]:
        assert ref["url"] is None or ref["url"].startswith("http")


# ---------------------------------------------------------------------------
# IMPORTANT 6: footer has all five links, Companies included.
# ---------------------------------------------------------------------------

def test_footer_links_include_companies(tmp_path):
    payload = _build(tmp_path)
    assert payload["footerLinks"] == [
        {"label": "Evidence", "href": "findings/"},
        {"label": "Numbers we track", "href": "series/"},
        {"label": "Past readings", "href": "history.html"},
        {"label": "Story archive", "href": "story/"},
        {"label": "Companies", "href": "entities/"},
    ]


# ---------------------------------------------------------------------------
# Dimensions: exactly 6, plain names never blank, no jargon, capped summaries,
# panel reasoning that doesn't just restate the row, full-sentence confidence.
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


def test_unrecognized_rating_word_raises_instead_of_defaulting(tmp_path):
    # MINOR (review round 1): _TONE_FOR_RATING used to silently default an
    # unknown rating to "mixed". A dimension we cannot honestly color must
    # fail loudly.
    store_dir = _make_store(tmp_path)
    current_path = Path(store_dir) / "chips.merchant-gpu" / "2026-08-v1.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    current["dimensionRatings"]["bottleneck"]["rating"] = "Sideways"
    current_path.write_text(json.dumps(current), encoding="utf-8")
    with pytest.raises(ValueError, match="unrecognized rating word"):
        build_dashboard_payload("chips.merchant-gpu", str(store_dir))


def test_dimension_summary_is_length_capped_and_clause_bounded(tmp_path):
    payload = _build(tmp_path)
    for d in payload["dimensions"]:
        assert len(d["summary"].split()) <= 21, d["summary"]


def test_dimension_panel_reasoning_does_not_simply_restate_the_summary(tmp_path):
    # IMPORTANT 7 (review round 1): opening the why-panel must not repeat
    # the row's own summary word for word.
    payload = _build(tmp_path)
    for d in payload["dimensions"]:
        assert not d["reasoning"].startswith(d["summary"])
        assert d["reasoning"] != d["summary"]


def test_dimension_confidence_is_a_full_sentence(tmp_path):
    # MINOR (review round 1): ships a full plain sentence, not the raw
    # "medium"/"high" level string.
    payload = _build(tmp_path)
    for d in payload["dimensions"]:
        assert d["confidence"]
        assert d["confidence"] not in ("high", "medium", "low")
        assert len(d["confidence"].split()) >= 2


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
