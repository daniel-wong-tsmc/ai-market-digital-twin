"""tests/narrator/test_inputs_issues.py — F115 Task 4: the `openIssues` key.

build_narrator_inputs must hand the narrator every OPEN issue from the
category's register, in register order, each with a short tail of its recent
assessment history. Resolved issues are not shown. A category with no register
yet gets an empty list -- deterministic and clock-free, so the prompt pin stays
stable.
"""
import datetime as dt

from gpu_agent.issues import (Issue, IssueRegister, IssueTrigger,
                              append_history, write_register)
from gpu_agent.narrator.inputs import build_narrator_inputs
from tests.dashboard.test_story_model import _store, CAT


def _issue(iid, title, state, kind, label):
    return Issue(id=iid, title=title, state=state, openedAsOf="2026-06",
                 trigger=IssueTrigger(kind=kind, label=label))


def _register_with_one_open_one_resolved(cat_dir):
    register = IssueRegister(
        schemaVersion=1, categoryId=CAT, asOf="2026-07",
        issues=[
            _issue("constraint-advanced-packaging", "advanced packaging",
                   "open", "binding-constraint", "advanced packaging"),
            _issue("dim-bottleneck", "Bottleneck", "resolved",
                   "dimension-weak", "bottleneck"),
        ])
    write_register(cat_dir, register)
    append_history(cat_dir, [
        {"asOf": "2026-05", "issueId": "constraint-advanced-packaging",
         "status": "worsened", "reasoning": "r", "claimFindingIds": ["f-1"],
         "triggerStillFiring": True, "streakAfter": 0},
        {"asOf": "2026-06", "issueId": "dim-bottleneck",
         "status": "improved", "reasoning": "r", "claimFindingIds": [],
         "triggerStillFiring": False, "streakAfter": 5},
        {"asOf": "2026-06", "issueId": "constraint-advanced-packaging",
         "status": "unchanged", "reasoning": "r", "claimFindingIds": [],
         "triggerStillFiring": True, "streakAfter": 0},
    ])


def test_open_issues_lists_only_open_with_history_tail(tmp_path):
    store = _store(tmp_path)
    _register_with_one_open_one_resolved(store / CAT)
    inp = build_narrator_inputs(CAT, store, dt.date(2026, 7, 23), None)
    assert inp["openIssues"] == [
        {"id": "constraint-advanced-packaging",
         "title": "advanced packaging",
         "trigger": {"kind": "binding-constraint", "label": "advanced packaging"},
         "recent": [{"asOf": "2026-05", "status": "worsened"},
                     {"asOf": "2026-06", "status": "unchanged"}]},
    ]


def test_open_issues_empty_when_no_register(tmp_path):
    inp = build_narrator_inputs(CAT, _store(tmp_path), dt.date(2026, 7, 23), None)
    assert inp["openIssues"] == []


def test_open_issues_preserves_register_order(tmp_path):
    store = _store(tmp_path)
    write_register(store / CAT, IssueRegister(
        schemaVersion=1, categoryId=CAT, asOf="2026-07",
        issues=[_issue("dim-zeta", "Zeta", "open", "dimension-weak", "zeta"),
                _issue("dim-alpha", "Alpha", "open", "dimension-weak", "alpha")]))
    inp = build_narrator_inputs(CAT, store, dt.date(2026, 7, 23), None)
    assert [i["id"] for i in inp["openIssues"]] == ["dim-zeta", "dim-alpha"]
    assert all(i["recent"] == [] for i in inp["openIssues"])


def test_open_issues_is_clock_free(tmp_path):
    """Same store, two different 'today' dates -> identical openIssues."""
    store = _store(tmp_path)
    _register_with_one_open_one_resolved(store / CAT)
    a = build_narrator_inputs(CAT, store, dt.date(2026, 7, 23), None)["openIssues"]
    b = build_narrator_inputs(CAT, store, dt.date(2027, 1, 1), None)["openIssues"]
    assert a == b
