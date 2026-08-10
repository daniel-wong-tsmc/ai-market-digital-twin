import json

import pytest

from gpu_agent.issues import (
    RESOLVE_STREAK,
    Issue,
    IssueLatest,
    IssueRegister,
    IssueTrigger,
    _title_from_dim_key,
    append_history,
    apply_assessments,
    issue_id,
    open_issues,
    read_history_tail,
    read_register,
    trigger_still_firing,
    write_register,
)

CATEGORY_ID = "chips.merchant-gpu"
AS_OF = "2026-08-10"

# Trimmed shape copied verbatim (structurally) from store/chips.merchant-gpu/2026-08-v5.json:
# categoryStatus.constraintLabel is truthy (binding-constraint trigger); bottleneck and moat
# are both Weak+worsening (dimension-weak triggers); competitiveStructure is Mixed+worsening
# (must NOT trigger); momentum is Very strong+improving (must NOT trigger).
SCORECARD = {
    "categoryStatus": {
        "rating": "Strong",
        "direction": "steady",
        "bottleneck": "bottleneck",
        "reason": "Orders and vendor margins stay very strong...",
        "constraintLabel": "HBM4 stacked-memory supply",
    },
    "dimensionRatings": {
        "bottleneck": {
            "rating": "Weak",
            "direction": "worsening",
            "voteSpread": "3/3 Weak",
        },
        "competitiveStructure": {
            "rating": "Mixed",
            "direction": "worsening",
            "voteSpread": "3/3 Mixed",
        },
        "moat": {
            "rating": "Weak",
            "direction": "worsening",
            "voteSpread": "3/3 Weak",
        },
        "momentum": {
            "rating": "Very strong",
            "direction": "improving",
            "voteSpread": "3/3 Very strong",
        },
        "strategicRisk": {
            "rating": "Mixed",
            "direction": "worsening",
            "voteSpread": "3/3 Mixed",
        },
    },
}

# Same shape as SCORECARD but with competitiveStructure flipped from Mixed+worsening to
# Weak+worsening, so a real multi-word dimension key (2 of the 5 real dimensions —
# competitiveStructure, strategicRisk — are multi-word) actually opens an issue and exercises
# the camelCase title-splitting logic end to end, not just the single-word dims
# (bottleneck, moat) that SCORECARD triggers.
MULTIWORD_DIM_SCORECARD = {
    "categoryStatus": SCORECARD["categoryStatus"],
    "dimensionRatings": {
        **SCORECARD["dimensionRatings"],
        "competitiveStructure": {
            "rating": "Weak",
            "direction": "worsening",
            "voteSpread": "3/3 Weak",
        },
    },
}

NO_CONSTRAINT_SCORECARD = {
    "categoryStatus": {
        "rating": "Strong",
        "direction": "steady",
        "bottleneck": "bottleneck",
        "reason": "no binding constraint right now",
        "constraintLabel": "",
    },
    "dimensionRatings": {
        "bottleneck": {"rating": "Strong", "direction": "improving"},
        "competitiveStructure": {"rating": "Mixed", "direction": "worsening"},
        "moat": {"rating": "Strong", "direction": "improving"},
        "momentum": {"rating": "Very strong", "direction": "improving"},
        "strategicRisk": {"rating": "Mixed", "direction": "worsening"},
    },
}


def _empty_register():
    return IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf="", issues=[])


# --- issue_id slugging -----------------------------------------------------

def test_issue_id_constraint_slug():
    trig = IssueTrigger(kind="binding-constraint", label="HBM4 stacked-memory supply")
    assert issue_id(trig) == "constraint-hbm4-stacked-memory-supply"


def test_issue_id_dimension_key():
    trig = IssueTrigger(kind="dimension-weak", label="bottleneck")
    assert issue_id(trig) == "dim-bottleneck"


def test_issue_id_stable_for_same_trigger():
    trig1 = IssueTrigger(kind="binding-constraint", label="HBM4 stacked-memory supply")
    trig2 = IssueTrigger(kind="binding-constraint", label="HBM4 stacked-memory supply")
    assert issue_id(trig1) == issue_id(trig2)


# --- open_issues -------------------------------------------------------------

def test_open_issues_opens_constraint_and_both_weak_worsening_dims():
    register = _empty_register()
    new_register, opened = open_issues(register, SCORECARD, AS_OF)
    ids = {i.id for i in new_register.issues}
    assert ids == {
        "constraint-hbm4-stacked-memory-supply",
        "dim-bottleneck",
        "dim-moat",
    }
    assert set(opened) == ids


def test_open_issues_mixed_worsening_does_not_open():
    register = _empty_register()
    new_register, _ = open_issues(register, SCORECARD, AS_OF)
    ids = {i.id for i in new_register.issues}
    assert "dim-competitiveStructure" not in ids
    assert "dim-momentum" not in ids
    assert "dim-strategicRisk" not in ids


def test_open_issues_constraint_title_is_verbatim():
    register = _empty_register()
    new_register, _ = open_issues(register, SCORECARD, AS_OF)
    constraint_issue = next(
        i for i in new_register.issues if i.id == "constraint-hbm4-stacked-memory-supply"
    )
    assert constraint_issue.title == "HBM4 stacked-memory supply"


def test_open_issues_dimension_title_is_camelcase_split_capitalized():
    register = _empty_register()
    new_register, _ = open_issues(register, SCORECARD, AS_OF)
    bottleneck_issue = next(i for i in new_register.issues if i.id == "dim-bottleneck")
    assert bottleneck_issue.title == "Bottleneck"


def test_open_issues_new_entries_are_open_with_zeroed_counters():
    register = _empty_register()
    new_register, _ = open_issues(register, SCORECARD, AS_OF)
    for issue in new_register.issues:
        assert issue.state == "open"
        assert issue.openedAsOf == AS_OF
        assert issue.improvedStreak == 0
        assert issue.worsenedCount == 0
        assert issue.checkCount == 0
        assert issue.reopenedAsOf == []
        assert issue.resolvedAsOf is None


def test_title_from_dim_key_splits_multiword_camelcase_key():
    # Direct assertion on the one piece of derived (non-pass-through) string logic in the
    # module: real multi-word dimension keys, not the single-word ones (bottleneck, moat)
    # that happen to be the only dims the fixture scorecard opens.
    assert _title_from_dim_key("competitiveStructure") == "Competitive structure"
    assert _title_from_dim_key("strategicRisk") == "Strategic risk"


def test_open_issues_opens_multiword_dimension_with_correctly_derived_title():
    # End-to-end path through open_issues: competitiveStructure (a real key from
    # store/chips.merchant-gpu/2026-08-v5.json) Weak+worsening must open dim-competitiveStructure
    # with the camelCase-split, capitalized title -- not just single-word dims.
    register = _empty_register()
    new_register, opened = open_issues(register, MULTIWORD_DIM_SCORECARD, AS_OF)
    assert "dim-competitiveStructure" in opened
    issue = next(i for i in new_register.issues if i.id == "dim-competitiveStructure")
    assert issue.title == "Competitive structure"
    assert issue.trigger == IssueTrigger(kind="dimension-weak", label="competitiveStructure")


def test_open_issues_second_call_is_idempotent():
    register = _empty_register()
    first_register, _ = open_issues(register, SCORECARD, AS_OF)
    second_register, opened_again = open_issues(first_register, SCORECARD, "2026-08-17")
    assert opened_again == []
    assert len(second_register.issues) == len(first_register.issues)
    assert {i.id for i in second_register.issues} == {i.id for i in first_register.issues}


def test_open_issues_no_constraint_does_not_open_constraint_issue():
    register = _empty_register()
    new_register, opened = open_issues(register, NO_CONSTRAINT_SCORECARD, AS_OF)
    ids = {i.id for i in new_register.issues}
    assert not any(i.startswith("constraint-") for i in ids)


# --- reopen ------------------------------------------------------------------

def test_reopen_resolved_issue_when_trigger_fires_again():
    trig = IssueTrigger(kind="dimension-weak", label="bottleneck")
    resolved_issue = Issue(
        id="dim-bottleneck",
        title="Bottleneck",
        state="resolved",
        openedAsOf="2026-06-01",
        resolvedAsOf="2026-07-01",
        reopenedAsOf=[],
        trigger=trig,
        improvedStreak=5,
        worsenedCount=1,
        checkCount=7,
    )
    register = IssueRegister(
        schemaVersion=1, categoryId=CATEGORY_ID, asOf="2026-07-01", issues=[resolved_issue]
    )
    new_register, opened = open_issues(register, SCORECARD, AS_OF)
    assert opened == ["dim-bottleneck"] or "dim-bottleneck" in opened
    reopened = next(i for i in new_register.issues if i.id == "dim-bottleneck")
    assert reopened.state == "open"
    assert reopened.reopenedAsOf == [AS_OF]
    assert reopened.improvedStreak == 0
    assert reopened.worsenedCount == 0
    # history preserved
    assert reopened.openedAsOf == "2026-06-01"
    assert reopened.resolvedAsOf == "2026-07-01"
    # no duplicate entry for same id
    assert sum(1 for i in new_register.issues if i.id == "dim-bottleneck") == 1


def test_reopen_grows_reopened_as_of_across_cycles():
    trig = IssueTrigger(kind="dimension-weak", label="bottleneck")
    resolved_issue = Issue(
        id="dim-bottleneck",
        title="Bottleneck",
        state="resolved",
        openedAsOf="2026-06-01",
        resolvedAsOf="2026-07-01",
        reopenedAsOf=["2026-07-15"],
        trigger=trig,
    )
    register = IssueRegister(
        schemaVersion=1, categoryId=CATEGORY_ID, asOf="2026-07-15", issues=[resolved_issue]
    )
    new_register, _ = open_issues(register, SCORECARD, AS_OF)
    reopened = next(i for i in new_register.issues if i.id == "dim-bottleneck")
    assert reopened.reopenedAsOf == ["2026-07-15", AS_OF]


# --- trigger_still_firing -----------------------------------------------------

def test_trigger_still_firing_true_for_matching_dimension():
    trig = IssueTrigger(kind="dimension-weak", label="bottleneck")
    issue = Issue(id="dim-bottleneck", title="Bottleneck", state="open",
                  openedAsOf=AS_OF, trigger=trig)
    assert trigger_still_firing(issue, SCORECARD) is True


def test_trigger_still_firing_false_when_dimension_recovers():
    trig = IssueTrigger(kind="dimension-weak", label="bottleneck")
    issue = Issue(id="dim-bottleneck", title="Bottleneck", state="open",
                  openedAsOf=AS_OF, trigger=trig)
    assert trigger_still_firing(issue, NO_CONSTRAINT_SCORECARD) is False


def test_trigger_still_firing_true_for_matching_constraint():
    trig = IssueTrigger(kind="binding-constraint", label="HBM4 stacked-memory supply")
    issue = Issue(id="constraint-hbm4-stacked-memory-supply", title="HBM4 stacked-memory supply",
                  state="open", openedAsOf=AS_OF, trigger=trig)
    assert trigger_still_firing(issue, SCORECARD) is True


def test_trigger_still_firing_false_when_constraint_cleared():
    trig = IssueTrigger(kind="binding-constraint", label="HBM4 stacked-memory supply")
    issue = Issue(id="constraint-hbm4-stacked-memory-supply", title="HBM4 stacked-memory supply",
                  state="open", openedAsOf=AS_OF, trigger=trig)
    assert trigger_still_firing(issue, NO_CONSTRAINT_SCORECARD) is False


# --- streak rules (apply_assessments) ----------------------------------------

def _open_issue(iid="dim-bottleneck"):
    trig = IssueTrigger(kind="dimension-weak", label="bottleneck")
    return Issue(id=iid, title="Bottleneck", state="open", openedAsOf=AS_OF, trigger=trig)


def _assessment(iid, status, reasoning="ok", finding_ids=None):
    return {
        "issueId": iid,
        "status": status,
        "reasoning": reasoning,
        "claimFindingIds": finding_ids or [],
    }


def test_improved_five_times_resolves_at_exactly_five():
    register = IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf=AS_OF,
                              issues=[_open_issue()])
    for n in range(RESOLVE_STREAK):
        register, _ = apply_assessments(
            register, [_assessment("dim-bottleneck", "improved")], SCORECARD, f"2026-08-{10+n}"
        )
    issue = register.issues[0]
    assert issue.improvedStreak == RESOLVE_STREAK
    assert issue.state == "resolved"
    assert issue.resolvedAsOf == "2026-08-14"


def test_improved_four_times_then_worsened_resets_and_stays_open():
    register = IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf=AS_OF,
                              issues=[_open_issue()])
    for n in range(RESOLVE_STREAK - 1):
        register, _ = apply_assessments(
            register, [_assessment("dim-bottleneck", "improved")], SCORECARD, f"2026-08-{10+n}"
        )
    register, _ = apply_assessments(
        register, [_assessment("dim-bottleneck", "worsened")], SCORECARD, "2026-08-20"
    )
    issue = register.issues[0]
    assert issue.improvedStreak == 0
    assert issue.state == "open"
    assert issue.worsenedCount == 1


def test_unchanged_with_trigger_gone_counts_toward_streak():
    register = IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf=AS_OF,
                              issues=[_open_issue()])
    register, lines = apply_assessments(
        register, [_assessment("dim-bottleneck", "unchanged")], NO_CONSTRAINT_SCORECARD, "2026-08-11"
    )
    issue = register.issues[0]
    assert issue.improvedStreak == 1
    assert lines[0]["triggerStillFiring"] is False


def test_unchanged_still_firing_resets_streak():
    register = IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf=AS_OF,
                              issues=[_open_issue()])
    register, _ = apply_assessments(
        register, [_assessment("dim-bottleneck", "improved")], SCORECARD, "2026-08-11"
    )
    assert register.issues[0].improvedStreak == 1
    register, lines = apply_assessments(
        register, [_assessment("dim-bottleneck", "unchanged")], SCORECARD, "2026-08-12"
    )
    issue = register.issues[0]
    assert issue.improvedStreak == 0
    assert lines[0]["triggerStillFiring"] is True


def test_not_assessed_after_three_improved_freezes_streak_and_check_count():
    register = IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf=AS_OF,
                              issues=[_open_issue()])
    for n in range(3):
        register, _ = apply_assessments(
            register, [_assessment("dim-bottleneck", "improved")], SCORECARD, f"2026-08-{10+n}"
        )
    assert register.issues[0].improvedStreak == 3
    assert register.issues[0].checkCount == 3
    register, lines = apply_assessments(
        register, [_assessment("dim-bottleneck", "not-assessed", reasoning="")], SCORECARD, "2026-08-20"
    )
    issue = register.issues[0]
    assert issue.improvedStreak == 3
    assert issue.checkCount == 3
    assert issue.latest.status == "not-assessed"
    assert lines[0]["status"] == "not-assessed"


def test_empty_assessments_marks_every_open_issue_not_assessed():
    register = IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf=AS_OF,
                              issues=[_open_issue("dim-bottleneck"), _open_issue("dim-moat")])
    register, lines = apply_assessments(register, [], SCORECARD, "2026-08-11")
    assert {i.latest.status for i in register.issues} == {"not-assessed"}
    assert {l["status"] for l in lines} == {"not-assessed"}
    assert len(lines) == 2


def test_assessment_for_unknown_id_is_ignored_without_crash():
    register = IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf=AS_OF,
                              issues=[_open_issue()])
    register, lines = apply_assessments(
        register, [_assessment("dim-does-not-exist", "improved")], SCORECARD, "2026-08-11"
    )
    assert lines == []
    assert register.issues[0].latest is None


def test_assessment_for_resolved_id_is_ignored_without_crash():
    trig = IssueTrigger(kind="dimension-weak", label="bottleneck")
    resolved = Issue(id="dim-bottleneck", title="Bottleneck", state="resolved",
                      openedAsOf="2026-06-01", resolvedAsOf="2026-07-01", trigger=trig)
    register = IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf=AS_OF, issues=[resolved])
    register, lines = apply_assessments(
        register, [_assessment("dim-bottleneck", "improved")], SCORECARD, "2026-08-11"
    )
    assert lines == []
    assert register.issues[0].state == "resolved"


# --- history -------------------------------------------------------------------

def test_apply_assessments_history_lines_have_correct_streak_after(tmp_path):
    register = IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf=AS_OF,
                              issues=[_open_issue("dim-bottleneck"), _open_issue("dim-moat")])
    register, lines = apply_assessments(
        register,
        [_assessment("dim-bottleneck", "improved"), _assessment("dim-moat", "improved")],
        SCORECARD,
        "2026-08-11",
    )
    assert len(lines) == 2
    for line in lines:
        assert line["streakAfter"] == 1
        assert line["asOf"] == "2026-08-11"


def test_append_history_never_truncates(tmp_path):
    cat_dir = tmp_path / "chips.merchant-gpu"
    lines1 = [{"asOf": AS_OF, "issueId": "dim-bottleneck", "status": "improved",
               "reasoning": "r", "claimFindingIds": [], "triggerStillFiring": True,
               "streakAfter": 1}]
    append_history(cat_dir, lines1)
    append_history(cat_dir, lines1 + lines1)
    p = cat_dir / "issues" / "history.jsonl"
    written = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(written) == 3


def test_read_history_tail_returns_last_n_oldest_first(tmp_path):
    cat_dir = tmp_path / "chips.merchant-gpu"
    for n in range(7):
        line = {"asOf": f"2026-08-{10+n}", "issueId": "dim-bottleneck", "status": "improved",
                "reasoning": "r", "claimFindingIds": [], "triggerStillFiring": True,
                "streakAfter": n + 1}
        append_history(cat_dir, [line])
    tail = read_history_tail(cat_dir, "dim-bottleneck", 3)
    assert [l["streakAfter"] for l in tail] == [5, 6, 7]


# --- no-silent-deletion invariant ----------------------------------------------

@pytest.mark.parametrize("mutate_fn", ["open_issues", "apply_assessments"])
def test_no_silent_deletion(mutate_fn):
    register = IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf=AS_OF,
                              issues=[_open_issue("dim-bottleneck"), _open_issue("dim-moat")])
    old_ids = {i.id for i in register.issues}
    if mutate_fn == "open_issues":
        new_register, _ = open_issues(register, SCORECARD, "2026-08-11")
    else:
        new_register, _ = apply_assessments(
            register,
            [_assessment("dim-bottleneck", "improved"), _assessment("dim-moat", "worsened")],
            SCORECARD,
            "2026-08-11",
        )
    new_ids = {i.id for i in new_register.issues}
    assert old_ids <= new_ids


# --- IO --------------------------------------------------------------------

def test_read_register_missing_dir_returns_empty_register(tmp_path):
    cat_dir = tmp_path / "chips.merchant-gpu"
    register = read_register(cat_dir, CATEGORY_ID)
    assert register.schemaVersion == 1
    assert register.categoryId == CATEGORY_ID
    assert register.issues == []


def test_write_then_read_round_trips(tmp_path):
    cat_dir = tmp_path / "chips.merchant-gpu"
    register = IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf=AS_OF,
                              issues=[_open_issue()])
    write_register(cat_dir, register)
    reread = read_register(cat_dir, CATEGORY_ID)
    assert reread.model_dump() == register.model_dump()


def test_write_register_twice_is_byte_identical(tmp_path):
    cat_dir = tmp_path / "chips.merchant-gpu"
    register = IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf=AS_OF,
                              issues=[_open_issue()])
    p1 = write_register(cat_dir, register)
    bytes1 = p1.read_bytes()
    p2 = write_register(cat_dir, register)
    bytes2 = p2.read_bytes()
    assert bytes1 == bytes2
