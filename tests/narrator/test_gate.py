import datetime as dt
from gpu_agent.narrator.gate import gate_narrator
from gpu_agent.narrator.schema import NarratorAnswer
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
    assert gate_narrator(a, _inp(tmp_path))
    a.scenes[0].sourceLine = "No new sourced evidence today."
    assert gate_narrator(a, _inp(tmp_path)) == []


def test_related_doc_outside_pool_rejected(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].relatedDocs = [{"url": "https://elsewhere.example/x",
                                 "title": "t", "outlet": "o", "date": "d"}]
    assert any("elsewhere" in v for v in gate_narrator(a, _inp(tmp_path)))


def test_banned_word_rejected(tmp_path):
    a = _ok(tmp_path)
    a.deck = "Demand momentum is strengthening."
    assert len(gate_narrator(a, _inp(tmp_path))) >= 1


def test_scene_bounds_and_forward_close(tmp_path):
    a = _ok(tmp_path)
    a.scenes = a.scenes[:1]                       # only 1 scene
    assert gate_narrator(a, _inp(tmp_path))
    b = _ok(tmp_path)
    b.scenes[-1].title = "Another grim chapter"   # not forward-looking
    assert gate_narrator(b, _inp(tmp_path))


def test_kpi_and_callout_membership(tmp_path):
    a = _ok(tmp_path)
    a.kpiPicks[0].indicatorId = "notASeries"
    assert gate_narrator(a, _inp(tmp_path))
    b = _ok(tmp_path)
    b.calloutMonths[0].monthKey = "1999-01"
    assert gate_narrator(b, _inp(tmp_path))


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
