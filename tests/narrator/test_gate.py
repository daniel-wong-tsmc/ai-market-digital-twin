import datetime as dt

import pytest

from gpu_agent.narrator.gate import gate_narrator
from gpu_agent.narrator.schema import NarratorAnswer, RelatedDoc
from gpu_agent.narrator.inputs import build_narrator_inputs
from tests.narrator.test_schema import _answer, _scene
from tests.narrator.test_inputs import CAT
from tests.dashboard.test_story_model import _store


_inp_cache: dict = {}


def _inp(tmp_path):
    # Several tests below call _inp(tmp_path) more than once with the same
    # tmp_path (to check two answers against the same fixture inputs), but
    # tests/dashboard/test_story_model._store() creates its directory tree
    # with mkdir(parents=True) and no exist_ok=True, so a second call on the
    # same tmp_path raises FileExistsError. Cache by tmp_path so the store is
    # only built once per test; pytest's tmp_path is unique per test function,
    # so this cannot leak fixture state between tests.
    key = str(tmp_path)
    if key not in _inp_cache:
        _inp_cache[key] = build_narrator_inputs(
            CAT, _store(tmp_path), dt.date(2026, 7, 23), None)
    return _inp_cache[key]


def _ok(tmp_path):
    # an answer aligned with the fixture store: finding f-1, series pool ids, month keys
    return NarratorAnswer.model_validate(_answer(
        scenes=[_scene(claimFindingIds=["f-1"], relatedDocs=[]),
                _scene(n=2, title="What would close the gap",
                       claimFindingIds=["f-2"], relatedDocs=[])],
        kpiPicks=[{"indicatorId": "hbmSupplyCapex", "whyCaption": "relief lever",
                    "scene": 1}],
        calloutMonths=[{"monthKey": "2026-07", "text": "Jul: memory cut",
                         "scene": 1}]))


def test_clean_answer_passes(tmp_path):
    assert gate_narrator(_ok(tmp_path), _inp(tmp_path)) == []


def test_unknown_finding_id_rejected(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].claimFindingIds = ["f-ghost"]
    assert any("f-ghost" in v for v in gate_narrator(a, _inp(tmp_path)))


def test_sourceless_scene_needs_exact_wording(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].claimFindingIds = []
    a.scenes[0].sourceLine = "Source: trust me"
    assert any("Source: trust me" in v for v in gate_narrator(a, _inp(tmp_path)))
    a.scenes[0].sourceLine = "No new sourced evidence today."
    assert gate_narrator(a, _inp(tmp_path)) == []


def test_related_doc_outside_pool_rejected(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].relatedDocs = [RelatedDoc(url="https://elsewhere.example/x",
                                          title="t", outlet="o", date="d")]
    assert any("elsewhere" in v for v in gate_narrator(a, _inp(tmp_path)))


def test_banned_word_rejected(tmp_path):
    a = _ok(tmp_path)
    a.deck = "Demand momentum is strengthening."
    assert len(gate_narrator(a, _inp(tmp_path))) >= 1


def test_scene_bounds_and_forward_close(tmp_path):
    a = _ok(tmp_path)
    a.scenes = a.scenes[:1]                       # only 1 scene
    a.scenes[0].title = "What to watch"           # forward-looking, so only
                                                   # the count check can fire
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("between 2 and 5" in v and "1" in v for v in violations)
    assert not any("forward-looking" in v for v in violations)

    b = _ok(tmp_path)
    b.scenes[-1].title = "Another grim chapter"   # not forward-looking
    violations_b = gate_narrator(b, _inp(tmp_path))
    assert any("forward-looking" in v and "Another grim chapter" in v
               for v in violations_b)


def test_scene_bounds_upper_limit(tmp_path):
    scenes = [
        _scene(n=1, title="What tightened", claimFindingIds=[],
               sourceLine="No new sourced evidence today.", relatedDocs=[]),
        _scene(n=2, title="What else moved", claimFindingIds=[],
               sourceLine="No new sourced evidence today.", relatedDocs=[]),
        _scene(n=3, title="What else moved", claimFindingIds=[],
               sourceLine="No new sourced evidence today.", relatedDocs=[]),
        _scene(n=4, title="What else moved", claimFindingIds=[],
               sourceLine="No new sourced evidence today.", relatedDocs=[]),
        _scene(n=5, title="What else moved", claimFindingIds=[],
               sourceLine="No new sourced evidence today.", relatedDocs=[]),
        _scene(n=6, title="What to watch", claimFindingIds=[],
               sourceLine="No new sourced evidence today.", relatedDocs=[]),
    ]
    a = NarratorAnswer.model_validate(_answer(
        scenes=scenes, kpiPicks=[], calloutMonths=[]))
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("between 2 and 5" in v and "6" in v for v in violations)


def test_kpi_and_callout_membership(tmp_path):
    a = _ok(tmp_path)
    a.kpiPicks[0].indicatorId = "notASeries"
    assert any("notASeries" in v for v in gate_narrator(a, _inp(tmp_path)))
    b = _ok(tmp_path)
    b.calloutMonths[0].monthKey = "1999-01"
    assert any("1999-01" in v for v in gate_narrator(b, _inp(tmp_path)))


# Supplementary coverage for the two sub-parts of check 6 that the brief's
# test_kpi_and_callout_membership doesn't exercise on its own: a kpiPick
# pointing at a scene number that doesn't exist, and two kpiPicks sharing a
# scene.
def test_kpi_pick_scene_must_exist(tmp_path):
    a = _ok(tmp_path)
    a.kpiPicks[0].scene = 99
    assert any("99" in v for v in gate_narrator(a, _inp(tmp_path)))


def test_kpi_pick_scenes_must_be_unique(tmp_path):
    a = _ok(tmp_path)
    a.kpiPicks.append(a.kpiPicks[0].model_copy())
    assert any("unique" in v for v in gate_narrator(a, _inp(tmp_path)))


def test_scene_n_values_must_be_contiguous(tmp_path):
    a = _ok(tmp_path)
    a.scenes[-1].n = 7                    # not 1..2 contiguous any more
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("[1, 7]" in v or ("1" in v and "7" in v and "contiguous" in v)
               for v in violations)

    b = _ok(tmp_path)
    b.scenes[0].n, b.scenes[1].n = 2, 1   # right set of values, wrong order
    violations_b = gate_narrator(b, _inp(tmp_path))
    assert any("[2, 1]" in v and "contiguous" in v for v in violations_b)


def test_scene_source_line_must_not_be_empty(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].claimFindingIds = ["f-1"]  # keep a claim so check 2's exact-
                                           # wording rule doesn't also fire
    a.scenes[0].sourceLine = "   "
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("sourceLine must not be empty" in v and "1" in v
               for v in violations)


_BANNED_WORD = "momentum"


@pytest.mark.parametrize("field", [
    "headline", "deck", "scene_title", "scene_paragraph", "scene_sourceLine",
    "kpi_whyCaption", "callout_text",
])
def test_prose_sweep_covers_every_location(tmp_path, field):
    a = _ok(tmp_path)
    if field == "headline":
        a.headline = f"The {_BANNED_WORD} shifted."
    elif field == "deck":
        a.deck = f"Demand {_BANNED_WORD} is building."
    elif field == "scene_title":
        a.scenes[0].title = f"The {_BANNED_WORD} shift"
    elif field == "scene_paragraph":
        a.scenes[0].paragraphs = [f"Buyers felt {_BANNED_WORD} building."]
    elif field == "scene_sourceLine":
        a.scenes[0].claimFindingIds = ["f-1"]
        a.scenes[0].sourceLine = f"Source: {_BANNED_WORD} tracker"
    elif field == "kpi_whyCaption":
        a.kpiPicks[0].whyCaption = f"the {_BANNED_WORD} lever"
    elif field == "callout_text":
        a.calloutMonths[0].text = f"Jul: {_BANNED_WORD} shift"
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("momentum" in v for v in violations)


def test_prose_sweep_catches_banned_word_hidden_by_angle_bracket_noise(tmp_path):
    # Unescaped prose containing a literal "<script>...</script>" span would
    # be stripped entirely by lint_story_copy's script-tag remover before the
    # banned-word scan runs, hiding the word inside. Escaping the model's
    # prose before wrapping it in "<p>...</p>" turns those angle brackets
    # into harmless entities so the word is still scanned and caught.
    a = _ok(tmp_path)
    a.deck = "Before. <script>the outlook shows momentum</script> After."
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("momentum" in v for v in violations)


def test_missing_inputs_keys_fail_closed_instead_of_raising(tmp_path):
    a = _ok(tmp_path)
    violations = gate_narrator(a, {})
    assert violations


def test_content_free_answer_with_empty_inputs_is_still_rejected():
    # A structurally legal but content-free answer -- no claim ids (using the
    # exact no-source sentence), no relatedDocs, no kpiPicks, no
    # calloutMonths -- references nothing in `inputs`, so checks 2/3/6 stay
    # silent no matter what `inputs` contains. Before the missing-keys check,
    # gate_narrator(a, {}) returned [] (a silent pass) instead of failing
    # closed on the fact that `inputs` itself is empty.
    a = NarratorAnswer.model_validate(_answer(
        scenes=[_scene(claimFindingIds=[],
                       sourceLine="No new sourced evidence today.",
                       relatedDocs=[]),
                _scene(n=2, title="What would close the gap",
                       claimFindingIds=[],
                       sourceLine="No new sourced evidence today.",
                       relatedDocs=[])],
        kpiPicks=[], calloutMonths=[]))
    violations = gate_narrator(a, {})
    assert violations
    for k in ("findings", "docPool", "seriesPool", "gapMonths"):
        assert any(k in v for v in violations)
