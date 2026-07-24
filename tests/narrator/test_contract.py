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
                                 sourceLine="Source: trust me")]),
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


def test_empty_claim_scene_has_empty_evidence_and_exact_wording(tmp_path):
    # Both named requirements together: a scene with no claimFindingIds must
    # (a) render an honest empty evidence list, never borrowed from another
    # scene/claim, and (b) carry the exact required sourceLine wording, even
    # if the mapper had to substitute it itself. The fixture's scene 2 is
    # given a deliberately WRONG sourceLine ("Source: trust me") precisely so
    # this test can only pass if the mapper's read-time backstop actually
    # substitutes the constant -- trusting the artifact's own sourceLine here
    # would fail the assertion below.
    st = _narrated(tmp_path)
    model = build_story_model(CAT, st, TODAY)
    scene2 = next(s for s in model["scenes"] if s["n"] == 2)
    assert scene2["source_line"] == "No new sourced evidence today."
    assert model["evidence"]["scene:2"]["findings"] == []


def test_fellback_artifact_falls_back_to_assembler(tmp_path):
    # The requirement is INDISTINGUISHABILITY, not merely "some other
    # headline ran": a fellBack artifact must produce the exact same model
    # as an identical store with no artifact at all.
    st = _narrated(tmp_path, fellBack=True)
    model = build_story_model(CAT, st, TODAY)
    assembled = build_story_model(CAT, _store(tmp_path / "assembled"), TODAY)
    assert model == assembled


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
    # Nested shapes, not just the top-level/kpis key sets: a missing key on a
    # hand-built scene dict or evidence entry must not slip through.
    assert set(narrated["scenes"][0]) == set(assembled["scenes"][0])
    assert (set(narrated["evidence"]["scene:1"])
           == set(assembled["evidence"]["scene:1"]))
    assert (set(narrated["kpis"]["anchored"])
           == set(assembled["kpis"]["anchored"]))


def test_anchored_indicator_cannot_be_a_kpi_pick(tmp_path):
    # An artifact that (illegally) picks the anchored indicator must be
    # rejected by the gate...
    from gpu_agent.narrator.gate import gate_narrator
    from gpu_agent.narrator.inputs import build_narrator_inputs
    from gpu_agent.narrator.schema import NarratorAnswer

    st = _store(tmp_path)
    answer = _answer(headline="A narrated headline.",
                     scenes=[_scene(claimFindingIds=["f-1"], relatedDocs=[]),
                             _scene(n=2, title="What would close the gap",
                                    claimFindingIds=[], relatedDocs=[],
                                    sourceLine="No new sourced evidence today.")],
                     kpiPicks=[{"indicatorId": "gpuRentalOnDemand",
                                "whyCaption": "the headline number",
                                "scene": 1}])
    violations = gate_narrator(
        NarratorAnswer.model_validate(answer),
        build_narrator_inputs(CAT, st, TODAY, None))
    assert any("gpuRentalOnDemand" in v for v in violations)

    # ...AND, if that gate is bypassed (a hand-edited or legacy artifact
    # written directly to the store), the mapper must still refuse to render
    # the anchored chip twice: it should be skipped from kpis.picks entirely,
    # so the label appears on the page exactly once (as the anchored chip).
    StoryStore(st).write(StoryArtifact.model_validate({
        "schemaVersion": 1, "categoryId": CAT, "storyDate": "2026-07-23",
        **answer,
        "narratorMeta": {"model": "opus", "promptHash": "x", "retries": 0,
                          "fellBack": False, "wroteAt": "2026-07-23T09:00:00"}}))
    model = build_story_model(CAT, st, TODAY)
    pick_ids = [p["claim"] for p in model["kpis"]["picks"]]
    assert "kpi:gpuRentalOnDemand" not in pick_ids
    html = render_story_page(model)
    # Count actual rendered KPI-band chips (visible <button class="st-chip...
    # elements), not incidental mentions of the label elsewhere on the page
    # (e.g. the hidden evidence-panel JSON, which legitimately still carries
    # a "kpi:gpuRentalOnDemand" entry for the always-present anchored chip).
    assert html.count('data-ev="kpi:gpuRentalOnDemand"') == 1
