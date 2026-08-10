"""tests/test_narrator_issues_gate.py — F115 Task 3: gate check 9, issue assessments.

`gate_narrator` gains a mechanical check over `answer.issues`: when
`inputs["openIssues"]` is non-empty, every open issue must get exactly one
assessment (missing/unknown/duplicate ids are each their own violation);
when `openIssues` is empty or missing, `answer.issues` must be None or
empty (a narrator that writes issues nobody asked about has invented
them). Each assessment's `reasoning` is checked for non-empty, at most 60
words, and the same banned-word lint check 4 already runs; each
`claimFindingIds` is checked for non-empty and membership in
`inputs.findings`, reusing the same `finding_ids` set the scene checks use.

`openIssues` is a brand-new inputs key (F115 Task 2/4, already landed in
cf304de). Many pre-F115 tests build inputs dicts by hand without it, so a
MISSING `openIssues` key must be treated as an empty list -- never a gate
crash, never a required-key violation.
"""
from gpu_agent.narrator.gate import gate_narrator
from gpu_agent.narrator.schema import IssueAssessment, NarratorAnswer

FINDINGS = [{"id": "f-1"}, {"id": "f-2"}]
SERIES_POOL = [{"indicatorId": "hbmSupplyCapex"}]
GAP_MONTHS = ["2026-07"]
OPEN_ISSUES = [
    {"id": "iss-1", "title": "Memory squeeze", "trigger": {"kind": "x", "label": "y"},
     "recent": []},
    {"id": "iss-2", "title": "Capex surge", "trigger": {"kind": "x", "label": "y"},
     "recent": []},
]


def _scene(n=1, title="What tightened", claimFindingIds=None):
    return dict(
        n=n, title=title, paragraphs=["Memory makers cut back."], visual=None,
        claimFindingIds=claimFindingIds if claimFindingIds is not None else ["f-1"],
        sourceLine="Source: Micron call", relatedDocs=[])


def _answer(issues=None):
    return NarratorAnswer.model_validate(dict(
        headline="The GPU shortage got worse.", deck="Why.",
        scenes=[_scene(), _scene(n=2, title="What would close the gap")],
        kpiPicks=[{"indicatorId": "hbmSupplyCapex", "whyCaption": "relief lever",
                   "scene": 1}],
        calloutMonths=[{"monthKey": "2026-07", "text": "Jul: memory cut", "scene": 1}],
        bullets=None,
        issues=issues,
    ))


def _inputs(open_issues=OPEN_ISSUES, findings=FINDINGS, drop_open_issues_key=False):
    inp = {
        "findings": findings,
        "docPool": [],
        "seriesPool": SERIES_POOL,
        "gapMonths": GAP_MONTHS,
        "openIssues": open_issues,
    }
    if drop_open_issues_key:
        del inp["openIssues"]
    return inp


def _issue(issue_id="iss-1", status="unchanged",
           reasoning="No new evidence arrived on this issue.",
           claim_finding_ids=None):
    return {
        "issueId": issue_id,
        "status": status,
        "reasoning": reasoning,
        "claimFindingIds": claim_finding_ids if claim_finding_ids is not None else ["f-1"],
    }


def _clean_issues():
    return [
        _issue("iss-1", reasoning="Memory supply share moved from 60% to 70% this week."),
        _issue("iss-2", reasoning="Oracle's capex filing showed a 162% year-over-year jump."),
    ]


def test_all_clean_issue_assessments_pass():
    a = _answer(_clean_issues())
    violations = gate_narrator(a, _inputs())
    assert not any("issue" in v.lower() for v in violations)


def test_missing_assessment_for_open_issue_rejected():
    a = _answer([_clean_issues()[0]])  # only iss-1, iss-2 missing
    violations = gate_narrator(a, _inputs())
    assert any("iss-2" in v and "missing" in v.lower() for v in violations)


def test_unknown_issue_id_rejected():
    issues = _clean_issues() + [_issue("iss-ghost")]
    a = _answer(issues)
    violations = gate_narrator(a, _inputs())
    assert any("iss-ghost" in v and "unknown" in v.lower() for v in violations)


def test_duplicate_issue_id_rejected():
    issues = _clean_issues() + [_issue("iss-1")]
    a = _answer(issues)
    violations = gate_narrator(a, _inputs())
    assert any("iss-1" in v and "duplicate" in v.lower() for v in violations)


def test_empty_reasoning_rejected():
    issues = _clean_issues()
    issues[0] = _issue("iss-1", reasoning="")
    a = _answer(issues)
    violations = gate_narrator(a, _inputs())
    assert any("iss-1" in v and "reasoning" in v.lower() and "empty" in v.lower()
               for v in violations)


def test_reasoning_over_60_words_rejected():
    long_reasoning = "word " * 61
    issues = _clean_issues()
    issues[0] = _issue("iss-1", reasoning=long_reasoning.strip())
    a = _answer(issues)
    violations = gate_narrator(a, _inputs())
    assert any("iss-1" in v and "60 words" in v for v in violations)


def test_reasoning_banned_word_rejected():
    issues = _clean_issues()
    issues[0] = _issue(
        "iss-1", reasoning="Supply momentum shifted this week per the filing.")
    a = _answer(issues)
    violations = gate_narrator(a, _inputs())
    assert any("momentum" in v for v in violations)


def test_unknown_finding_id_in_issue_rejected():
    issues = _clean_issues()
    issues[0] = _issue("iss-1", claim_finding_ids=["f-ghost"])
    a = _answer(issues)
    violations = gate_narrator(a, _inputs())
    assert any("iss-1" in v and "f-ghost" in v for v in violations)


def test_empty_claim_finding_ids_rejected():
    issues = _clean_issues()
    issues[0] = _issue("iss-1", claim_finding_ids=[])
    a = _answer(issues)
    violations = gate_narrator(a, _inputs())
    assert any("iss-1" in v and "claimFindingIds" in v and "empty" in v.lower()
               for v in violations)


def test_issues_present_when_open_issues_empty_rejected():
    a = _answer(_clean_issues())
    violations = gate_narrator(a, _inputs(open_issues=[]))
    assert any("narrator invented issue assessments" in v for v in violations)


def test_issues_none_when_open_issues_empty_passes():
    a = _answer(None)
    violations = gate_narrator(a, _inputs(open_issues=[]))
    assert not any("issue" in v.lower() for v in violations)


def test_missing_open_issues_key_with_no_issues_is_pre_f115_compatible():
    # Pre-F115 callers build inputs dicts by hand with no `openIssues` key at
    # all -- this must be treated as an empty list, not a required-key
    # violation and not a crash.
    a = _answer(None)
    inp = _inputs(drop_open_issues_key=True)
    assert "openIssues" not in inp
    violations = gate_narrator(a, inp)
    assert not any("issue" in v.lower() for v in violations)
    assert not any("openIssues" in v for v in violations)
