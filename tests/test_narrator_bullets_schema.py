"""tests/test_narrator_bullets_schema.py — F114 Task 1: StoryBullet schema, artifact v2.

A v2 artifact carries the narrator's own three "what changed" bullets on
NarratorAnswer.bullets. A pre-F114 (v1) artifact has no bullets key at all and must
keep validating unchanged (back-compat is the point).
"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from gpu_agent.narrator.schema import NarratorAnswer, StoryArtifact, StoryBullet

REPO_ROOT = Path(__file__).resolve().parent.parent


def _scene(n=1, **kw):
    d = dict(n=n, title="What tightened", paragraphs=["Memory makers cut back."],
             visual={"kind": "spark", "seriesId": "hbmSupplyCapex",
                     "label": "Memory factory spending"},
             claimFindingIds=["f-1"], sourceLine="Source: Micron call",
             relatedDocs=[{"url": "https://x.example/a", "title": "t",
                            "outlet": "Reuters", "date": "2026-07-22"}])
    d.update(kw)
    return d


def _minimal_answer(**kw):
    d = dict(headline="The GPU shortage got worse.", deck="Why.",
             scenes=[_scene(), _scene(n=2, title="What would close the gap")],
             kpiPicks=[{"indicatorId": "hbmSupplyCapex",
                        "whyCaption": "the relief lever", "scene": 1}],
             calloutMonths=[{"monthKey": "2026-07", "text": "Jul: memory cut",
                              "scene": 1}])
    d.update(kw)
    return d


def test_v1_artifact_still_validates():
    art = json.loads(
        (REPO_ROOT / "store/chips.merchant-gpu/story/2026-08-05.json").read_text(encoding="utf-8")
    )
    assert "bullets" not in art
    assert art["schemaVersion"] == 1
    validated = StoryArtifact.model_validate(art)
    assert validated.bullets is None


def test_v2_bullets_roundtrip():
    b = {"text": "AMD's data-center sales hit $6.7 billion last quarter, nearly triple two years ago.",
         "claimFindingIds": ["abc-1"]}
    a = _minimal_answer()
    a["bullets"] = [b, b, b]
    answer = NarratorAnswer.model_validate(a)
    assert answer.bullets is not None
    assert len(answer.bullets) == 3
    assert answer.bullets[0].text.startswith("AMD")
    assert answer.bullets[0].claimFindingIds == ["abc-1"]


def test_bullets_extra_key_forbidden():
    b = {"text": "AMD's data-center sales hit $6.7 billion last quarter, nearly triple two years ago.",
         "claimFindingIds": ["abc-1"], "mood": "spicy"}
    with pytest.raises(ValidationError):
        StoryBullet.model_validate(b)


def test_artifact_schema_version_accepts_2():
    a = _minimal_answer()
    a["bullets"] = None
    art = StoryArtifact.model_validate({
        "schemaVersion": 2, "categoryId": "chips.merchant-gpu",
        "storyDate": "2026-08-06", **a,
        "narratorMeta": {"model": "opus", "promptHash": "abc", "retries": 0,
                          "fellBack": False, "wroteAt": "2026-08-06T09:00:00"}})
    assert art.schemaVersion == 2
