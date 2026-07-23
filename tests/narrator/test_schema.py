import pytest
from pydantic import ValidationError
from gpu_agent.narrator.schema import (NarratorAnswer, StoryArtifact,
                                       StoryScene, NarratorMeta)


def _scene(n=1, **kw):
    d = dict(n=n, title="What tightened", paragraphs=["Memory makers cut back."],
             visual={"kind": "spark", "seriesId": "hbmSupplyCapex",
                     "label": "Memory factory spending"},
             claimFindingIds=["f-1"], sourceLine="Source: Micron call",
             relatedDocs=[{"url": "https://x.example/a", "title": "t",
                            "outlet": "Reuters", "date": "2026-07-22"}])
    d.update(kw)
    return d


def _answer(**kw):
    d = dict(headline="The GPU shortage got worse.", deck="Why.",
             scenes=[_scene(), _scene(n=2, title="What would close the gap")],
             kpiPicks=[{"indicatorId": "hbmSupplyCapex",
                        "whyCaption": "the relief lever", "scene": 1}],
             calloutMonths=[{"monthKey": "2026-07", "text": "Jul: memory cut",
                              "scene": 1}])
    d.update(kw)
    return d


def test_answer_validates():
    a = NarratorAnswer.model_validate(_answer())
    assert a.scenes[0].visual.seriesId == "hbmSupplyCapex"


def test_extra_keys_forbidden():
    with pytest.raises(ValidationError):
        NarratorAnswer.model_validate({**_answer(), "mood": "spicy"})


def test_artifact_wraps_answer():
    art = StoryArtifact.model_validate({
        "schemaVersion": 1, "categoryId": "chips.merchant-gpu",
        "storyDate": "2026-07-23", **_answer(),
        "narratorMeta": {"model": "opus", "promptHash": "abc", "retries": 0,
                          "fellBack": False, "wroteAt": "2026-07-23T09:00:00"}})
    assert art.narratorMeta.fellBack is False


def test_answer_schema_exported():
    js = NarratorAnswer.model_json_schema()
    assert "scenes" in js["properties"] and "narratorMeta" not in js["properties"]
