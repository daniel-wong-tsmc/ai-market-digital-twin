"""F115 Task 5: the deterministic citation audit extended to narrator issue
assessments.

Mirrors tests/test_citation_audit_bullets.py's fixture style exactly --
issue assessments are audited via the same Claim/audit_claim machinery as
scenes, bullets and implication lines, just keyed `issue:<issueId>` (the
one deliberate difference from bullets: issues DO carry their own id, so
the claim key uses it instead of list order).
"""
import json

import pytest

from gpu_agent.citation_audit import (AuditStore, Claim, FindingsReader,
                                      audit_claim, claims_from_bullets,
                                      claims_from_issues, claims_from_story,
                                      run_audit)
from gpu_agent.narrator.schema import (IssueAssessment, NarratorMeta,
                                       StoryArtifact, StoryBullet, StoryScene)
from gpu_agent.narrator.store import StoryStore

CAT = "chips.merchant-gpu"
DATE = "2026-07-27"


def _finding(fid, statement="a thing happened", why="because", number=None,
             unit="USD_B", evidence=()):
    d = {
        "id": fid,
        "statement": statement,
        "kind": "observed",
        "trend": "flat",
        "why": why,
        "impact": {"targets": ["tsmc"], "direction": "mixed", "mechanism": "m"},
        "evidence": [{"source": "src", "url": "https://example.com/a", "date": dt,
                      "excerpt": ex, "tier": "secondary"} for dt, ex in evidence],
        "confidence": {"level": "medium", "basis": "b"},
        "asOf": "2026-07",
        "indicatorId": "gpuSpotPrice",
        "side": "price",
        "polarityDemand": 0,
        "polaritySupply": 0,
        "magnitude": 2,
        "entity": "nvidia",
        "observedAt": "2026-07-23",
        "capturedAt": "2026-07-23T00:00:00Z",
    }
    if number is not None:
        d["value"] = {"number": number, "unit": unit}
    return d


def _write_findings(root, *findings):
    d = root / "findings"
    d.mkdir(parents=True, exist_ok=True)
    for f in findings:
        (d / f"{f['id']}.json").write_text(json.dumps(f, indent=2), encoding="utf-8")
    return FindingsReader(d)


def _scene(n, paragraphs, finding_ids, title="A scene"):
    return StoryScene(n=n, title=title, paragraphs=paragraphs, visual=None,
                      claimFindingIds=list(finding_ids),
                      sourceLine="Sources: example.com", relatedDocs=[])


def _bullet(text, finding_ids):
    return StoryBullet(text=text, claimFindingIds=list(finding_ids))


def _issue(issue_id, reasoning, finding_ids, status="unchanged"):
    return IssueAssessment(issueId=issue_id, status=status, reasoning=reasoning,
                           claimFindingIds=list(finding_ids))


def _story(scenes, bullets=None, issues=None, schema_version=2, category_id=CAT,
          story_date=DATE):
    return StoryArtifact(
        schemaVersion=schema_version, categoryId=category_id, storyDate=story_date,
        headline="A headline", deck="A deck", scenes=scenes, kpiPicks=[],
        calloutMonths=[], bullets=bullets, issues=issues,
        narratorMeta=NarratorMeta(model="m", promptHash="h", retries=0,
                                  fellBack=False, wroteAt="2026-07-27T00:00:00Z"))


# --- claims_from_issues -------------------------------------------------

def test_claims_from_issues_keys_are_issue_id():
    art = _story(
        [_scene(1, ["one"], ["f-a"])],
        issues=[_issue("constraint-hbm4-stacked-memory-supply",
                       "Issue one reasoning.", ["f-a"]),
               _issue("policy-export-controls", "Issue two reasoning.", ["f-b"])])
    claims = claims_from_issues(art)
    assert [c.claimKey for c in claims] == [
        "issue:constraint-hbm4-stacked-memory-supply",
        "issue:policy-export-controls",
    ]
    assert claims[0].text == "Issue one reasoning."
    assert claims[0].findingIds == ("f-a",)


def test_claims_from_issues_on_artifact_with_no_issues_is_empty():
    # issues=None is the pre-F115 (v1/v2) shape -- must contribute zero claims.
    art = _story([_scene(1, ["one"], ["f-a"])], issues=None, schema_version=2)
    assert claims_from_issues(art) == []


# --- issue reasoning numbers audited like bullet/scene numbers -----------

def test_issue_number_matching_its_cited_finding_is_clean(tmp_path):
    reader = _write_findings(tmp_path, _finding(
        "f-a", statement="supply improved", number=4.83,
        evidence=[("2026-07-23", "climbed to $4.83 billion")]))
    claim = Claim("issue:constraint-hbm4-stacked-memory-supply",
                  "Supply climbed to $4.83 billion this week.", ("f-a",))
    r = audit_claim(claim, reader)
    assert r.verdict == "clean"
    assert r.flaggedTokens == []


def test_issue_number_unsupported_by_its_citation_is_flagged(tmp_path):
    reader = _write_findings(tmp_path, _finding("f-a", statement="supply held flat"))
    claim = Claim("issue:constraint-hbm4-stacked-memory-supply",
                  "Supply climbed to $99.99 billion this week.", ("f-a",))
    r = audit_claim(claim, reader)
    assert r.verdict == "flagged"
    assert r.flaggedTokens == ["99.99"]
    assert r.claimKey == "issue:constraint-hbm4-stacked-memory-supply"


# --- run_audit wiring -------------------------------------------------------

def test_run_audit_includes_issue_claims(tmp_path):
    _write_findings(
        tmp_path,
        _finding("f-a", statement="rates held flat"),
        _finding("f-b", statement="supply rose", number=25,
                 evidence=[("2026-07-23", "up 25 percent")]))
    StoryStore(tmp_path).write(_story(
        [_scene(1, ["Nothing numeric."], ["f-a"])],
        issues=[
            _issue("constraint-hbm4-stacked-memory-supply",
                   "Supply rose 25 percent this week.", ["f-b"]),
            _issue("policy-export-controls",
                   "Rates ran to $9.99 an hour.", ["f-a"]),
        ]))
    art = run_audit(tmp_path, CAT, DATE)
    keys = [c.claimKey for c in art.claims]
    assert keys == [
        "scene:1",
        "issue:constraint-hbm4-stacked-memory-supply",
        "issue:policy-export-controls",
    ]
    by = {c.claimKey: c for c in art.claims}
    assert by["issue:constraint-hbm4-stacked-memory-supply"].verdict == "clean"
    assert by["issue:policy-export-controls"].verdict == "flagged"
    assert by["issue:policy-export-controls"].flaggedTokens == ["9.99"]


def test_run_audit_writes_and_reads_back_issue_claims(tmp_path):
    _write_findings(tmp_path, _finding("f-a", statement="rates held flat"))
    StoryStore(tmp_path).write(_story(
        [_scene(1, ["Nothing numeric."], ["f-a"])],
        issues=[_issue("constraint-hbm4-stacked-memory-supply",
                       "Nothing numeric here either.", ["f-a"])]))
    art = run_audit(tmp_path, CAT, DATE)
    store = AuditStore(tmp_path)
    store.write(art)
    back = store.read(CAT, DATE)
    assert [c.claimKey for c in back.claims] == [
        "scene:1", "issue:constraint-hbm4-stacked-memory-supply"]


# --- v1/v2 back-compat: golden count regression ------------------------------

def test_v2_artifact_with_no_issues_audits_exactly_as_before(tmp_path):
    """Pins the pre-F115 behaviour: a v2 story (schemaVersion=2, issues=None)
    must produce exactly the same claim count/keys/summary as it did before
    this task -- no issue: claims appear, nothing about scene/bullet auditing
    changes."""
    _write_findings(
        tmp_path,
        _finding("f-a", statement="rates held flat"))
    StoryStore(tmp_path).write(_story(
        [
            _scene(1, ["Rates ran to $9.99 an hour."], ["f-a"]),   # flagged
            _scene(2, ["Nothing numeric."], ["f-a"]),              # clean
            _scene(3, ["We saw 42 percent."], []),                 # skipped
        ],
        bullets=[_bullet("A bullet with no numbers.", ["f-a"])],
        issues=None, schema_version=2))
    art = run_audit(tmp_path, CAT, DATE)

    # Golden pin: exactly the pre-F115 claim set, in the pre-F115 order.
    assert [c.claimKey for c in art.claims] == [
        "scene:1", "scene:2", "scene:3", "bullet:0"]
    assert art.summary == {"claimsAudited": 4, "flagged": 1, "skipped": 1}
    assert art.schemaVersion == 1  # audit artifact's own schema is unaffected


def test_real_2026_08_08_story_artifact_golden_claim_count():
    """Regression pin over the real store artifact (F115 brief requirement):
    a v2 artifact with bullets and no issues must produce a claim list
    IDENTICAL to what it produced before this task. Before-count measured by
    running the pre-change code: run_audit('store', 'chips.merchant-gpu',
    '2026-08-08') gave claimsAudited=15, flagged=0, skipped=0, with keys
    scene:1..4 and bullet:0.. (exact list asserted below)."""
    art = run_audit("store", "chips.merchant-gpu", "2026-08-08")
    assert art.summary == {"claimsAudited": 15, "flagged": 0, "skipped": 0}
    assert len(art.claims) == 15
    assert all(not c.claimKey.startswith("issue:") for c in art.claims)
