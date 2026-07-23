import datetime as dt
from gpu_agent.dashboard.story_model import build_story_model
from gpu_agent.dashboard.story_render import render_story_page, lint_story_copy
from gpu_agent.narrator.store import StoryStore
from gpu_agent.narrator.schema import StoryArtifact
from tests.narrator.test_schema import _answer, _scene
from tests.dashboard.test_story_model import _store, CAT

TODAY = dt.date(2026, 7, 23)


def _narrated(tmp_path, **meta):
    st = _store(tmp_path)
    m = {"model": "opus", "promptHash": "x", "retries": 0,
         "fellBack": False, "wroteAt": "2026-07-23T09:00:00"}
    m.update(meta)
    StoryStore(st).write(StoryArtifact.model_validate({
        "schemaVersion": 1, "categoryId": CAT, "storyDate": "2026-07-23",
        **_answer(headline="A narrated headline.",
                  scenes=[_scene(claimFindingIds=["f-1"], relatedDocs=[]),
                          _scene(n=2, title="What would close the gap",
                                 claimFindingIds=[], relatedDocs=[],
                                 sourceLine="No new sourced evidence today.")]),
        "narratorMeta": m}))
    return st


def test_artifact_drives_the_page(tmp_path):
    st = _narrated(tmp_path)
    model = build_story_model(CAT, st, TODAY)
    assert model["headline"] == "A narrated headline."
    assert model["kpis"]["picks"][0]["caption"] == "the relief lever"
    html = render_story_page(model)
    assert "A narrated headline." in html
    assert lint_story_copy(html) == []


def test_fellback_artifact_falls_back_to_assembler(tmp_path):
    st = _narrated(tmp_path, fellBack=True)
    model = build_story_model(CAT, st, TODAY)
    assert model["headline"] != "A narrated headline."   # assembler ran


def test_no_artifact_same_as_phase_a(tmp_path):
    st = _store(tmp_path)
    model = build_story_model(CAT, st, TODAY)
    assert model["headline"] == "The GPU shortage got worse this month."


def test_both_paths_same_shape(tmp_path):
    st = _narrated(tmp_path)
    narrated = build_story_model(CAT, st, TODAY)
    assembled = build_story_model(CAT, _store(tmp_path / "b"), TODAY)
    assert set(narrated) == set(assembled)
    assert set(narrated["kpis"]) == set(assembled["kpis"])
