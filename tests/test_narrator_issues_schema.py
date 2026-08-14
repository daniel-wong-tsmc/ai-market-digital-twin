"""tests/test_narrator_issues_schema.py — F115 Task 2: IssueAssessment schema, artifact v3.

A v3 artifact carries the narrator's per-issue assessments on
NarratorAnswer.issues. A pre-F115 (v1/v2) artifact has no issues key at all
and must keep validating unchanged (back-compat is the point). The narrator's
status vocabulary is deliberately narrower than the register's: it may say
only improved/worsened/unchanged. It may never say "resolved" (that is
decided solely by the streak rule in gpu_agent/issues.py) or "not-assessed"
(that is a system-set default, not something the narrator writes).
"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from gpu_agent.narrator.schema import IssueAssessment, NarratorAnswer, StoryArtifact

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
        (REPO_ROOT / "store/chips.merchant-gpu/story/2026-07-25.json").read_text(encoding="utf-8")
    )
    assert "bullets" not in art
    assert "issues" not in art
    assert art["schemaVersion"] == 1
    validated = StoryArtifact.model_validate(art)
    assert validated.bullets is None
    assert validated.issues is None


def test_v2_artifact_still_validates():
    art = json.loads(
        (REPO_ROOT / "store/chips.merchant-gpu/story/2026-08-08.json").read_text(encoding="utf-8")
    )
    assert "issues" not in art
    assert art["schemaVersion"] == 2
    validated = StoryArtifact.model_validate(art)
    assert validated.bullets is not None
    assert validated.issues is None


def test_v3_issues_roundtrip():
    issue = {"issueId": "iss-1", "status": "improved",
              "reasoning": "Memory supply share moved from 60% to 70%.",
              "claimFindingIds": ["abc-1"]}
    a = _minimal_answer()
    a["issues"] = [issue, issue]
    answer = NarratorAnswer.model_validate(a)
    assert answer.issues is not None
    assert len(answer.issues) == 2
    assert answer.issues[0].issueId == "iss-1"
    assert answer.issues[0].status == "improved"
    assert answer.issues[0].claimFindingIds == ["abc-1"]


def test_issue_assessment_extra_key_forbidden():
    issue = {"issueId": "iss-1", "status": "improved",
              "reasoning": "Memory supply share moved from 60% to 70%.",
              "claimFindingIds": ["abc-1"], "mood": "spicy"}
    with pytest.raises(ValidationError):
        IssueAssessment.model_validate(issue)


@pytest.mark.parametrize("bad_status", ["resolved", "not-assessed", "closed", ""])
def test_issue_assessment_rejects_statuses_outside_narrator_vocabulary(bad_status):
    issue = {"issueId": "iss-1", "status": bad_status,
              "reasoning": "Some reasoning.", "claimFindingIds": ["abc-1"]}
    with pytest.raises(ValidationError):
        IssueAssessment.model_validate(issue)


def test_artifact_schema_version_accepts_3():
    a = _minimal_answer()
    a["bullets"] = None
    a["issues"] = [{"issueId": "iss-1", "status": "unchanged",
                     "reasoning": "No new information this cycle.",
                     "claimFindingIds": []}]
    art = StoryArtifact.model_validate({
        "schemaVersion": 3, "categoryId": "chips.merchant-gpu",
        "storyDate": "2026-08-10", **a,
        "narratorMeta": {"model": "opus", "promptHash": "abc", "retries": 0,
                          "fellBack": False, "wroteAt": "2026-08-10T09:00:00"}})
    assert art.schemaVersion == 3
    assert art.issues[0].status == "unchanged"


def test_artifact_schema_version_still_accepts_1_and_2():
    a = _minimal_answer()
    for version in (1, 2):
        art = StoryArtifact.model_validate({
            "schemaVersion": version, "categoryId": "chips.merchant-gpu",
            "storyDate": "2026-08-10", **a,
            "narratorMeta": {"model": "opus", "promptHash": "abc", "retries": 0,
                              "fellBack": False, "wroteAt": "2026-08-10T09:00:00"}})
        assert art.schemaVersion == version
        assert art.issues is None


def test_artifact_schema_version_rejects_4():
    a = _minimal_answer()
    with pytest.raises(ValidationError):
        StoryArtifact.model_validate({
            "schemaVersion": 4, "categoryId": "chips.merchant-gpu",
            "storyDate": "2026-08-10", **a,
            "narratorMeta": {"model": "opus", "promptHash": "abc", "retries": 0,
                              "fellBack": False, "wroteAt": "2026-08-10T09:00:00"}})
