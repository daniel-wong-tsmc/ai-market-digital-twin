"""F123: a re-worded binding constraint must RENAME the standing issue, not mint
a twin.

The real bug, from git history of store/chips.merchant-gpu/issues/register.json:
one physical constraint got three ids across three cycles because the id is
slugged from the exact constraintLabel. Each stranded id then stopped matching
the live scorecard, so trigger_still_firing read False, every "unchanged"
assessment counted as improvement, and after RESOLVE_STREAK quiet cycles the
register would tell the reader "Resolved" about a constraint still biting.
"""
from gpu_agent.issues import (
    Issue,
    IssueRegister,
    IssueTrigger,
    _label_overlap,
    _label_tokens,
    _labels_match,
    append_history,
    apply_assessments,
    open_issues,
    read_history_tail,
)

CATEGORY_ID = "chips.merchant-gpu"

# The three real constraintLabel values, verbatim from
# store/chips.merchant-gpu/2026-08-v{8,9,10}.json.
V8 = "HBM stacked memory supply"
V9 = "stacked memory and server DRAM"
V10 = "Stacked high-bandwidth memory supply"


# --- token overlap helpers ----------------------------------------------------

def test_label_tokens_drops_stop_words_and_lowercases():
    assert _label_tokens(V9) == {"stacked", "memory", "server", "dram"}


def test_label_tokens_empty_for_blank():
    assert _label_tokens("   ") == set()


def test_real_relabel_pairs_all_match():
    assert _labels_match(V8, V9)
    assert _labels_match(V9, V10)
    assert _labels_match(V8, V10)


def test_unrelated_constraints_do_not_match():
    assert not _labels_match(V8, "CoWoS advanced packaging capacity")
    assert not _labels_match(V8, "power and grid capacity")


def test_generic_tokens_alone_do_not_match():
    # Both end in "supply capacity" and share nothing specific: matching on
    # generic supply words alone would fuse two genuinely different constraints.
    assert not _labels_match("wafer supply capacity", "power supply capacity")


def test_overlap_reports_shared_specific_and_ratio():
    shared, specific, ratio = _label_overlap(V8, V10)
    assert shared == 3               # stacked, memory, supply
    assert specific == 2             # "supply" is generic
    assert ratio == 0.75


# --- open_issues: rename instead of minting a twin -----------------------------

def _scorecard(label):
    """Minimal scorecard: one binding constraint, no weak+worsening dims."""
    return {
        "categoryStatus": {
            "rating": "Strong",
            "direction": "steady",
            "bottleneck": "bottleneck",
            "reason": "...",
            "constraintLabel": label,
        },
        "dimensionRatings": {},
    }


def _empty_register():
    return IssueRegister(schemaVersion=1, categoryId=CATEGORY_ID, asOf="", issues=[])


def test_v8_to_v9_relabel_renames_instead_of_minting_a_twin():
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    assert [i.id for i in reg.issues] == ["constraint-hbm-stacked-memory-supply"]

    reg, opened = open_issues(reg, _scorecard(V9), "2026-08-21")

    assert len(reg.issues) == 1, "a relabel must not open a twin"
    issue = reg.issues[0]
    assert issue.id == "constraint-hbm-stacked-memory-supply"
    assert issue.title == V9
    assert issue.trigger.label == V9
    assert issue.openedAsOf == "2026-08-19"
    assert issue.reopenedAsOf == []
    assert opened == ["constraint-hbm-stacked-memory-supply"]


def test_three_cycle_relabel_chain_stays_one_issue():
    reg = _empty_register()
    for label, day in ((V8, "2026-08-19"), (V9, "2026-08-21"), (V10, "2026-08-22")):
        reg, _ = open_issues(reg, _scorecard(label), day)
    assert len(reg.issues) == 1
    assert reg.issues[0].id == "constraint-hbm-stacked-memory-supply"
    assert reg.issues[0].title == V10


def test_unrelated_new_constraint_still_mints_a_new_issue():
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    reg, opened = open_issues(reg, _scorecard("CoWoS advanced packaging capacity"),
                              "2026-08-21")
    assert len(reg.issues) == 2
    assert opened == ["constraint-cowos-advanced-packaging-capacity"]


def test_rerunning_open_after_a_rename_is_a_no_op():
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    reg, _ = open_issues(reg, _scorecard(V9), "2026-08-21")
    before = reg.model_dump()
    reg2, opened = open_issues(reg, _scorecard(V9), "2026-08-21")
    assert opened == []
    assert reg2.model_dump() == before


def test_resolved_issue_is_not_a_rename_target():
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    reg = reg.model_copy(update={
        "issues": [reg.issues[0].model_copy(update={"state": "resolved",
                                                    "resolvedAsOf": "2026-08-20"})]
    })
    reg, opened = open_issues(reg, _scorecard(V9), "2026-08-21")
    assert len(reg.issues) == 2
    assert opened == ["constraint-stacked-memory-and-server-dram"]


def test_exact_id_hit_on_open_issue_refreshes_a_stale_label():
    # v8 -> v9 renames in place (the id still derives from the v8 wording). A
    # revert to the v8 wording finds the standing issue by id; its stored label
    # must follow back, or trigger_still_firing reads False against the live
    # scorecard -- the same F123 bug from the other direction.
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    reg, _ = open_issues(reg, _scorecard(V9), "2026-08-21")
    reg, opened = open_issues(reg, _scorecard(V8), "2026-08-22")
    assert len(reg.issues) == 1
    assert reg.issues[0].trigger.label == V8
    assert reg.issues[0].title == V8


def test_rename_target_is_deterministic_when_two_open_issues_match():
    # The committed register really does hold two open constraint issues, so a
    # tie is reachable and must not depend on iteration order.
    reg = IssueRegister(
        schemaVersion=1, categoryId=CATEGORY_ID, asOf="2026-08-21",
        issues=[
            Issue(id="constraint-stacked-memory-and-server-dram",
                  title=V9, state="open", openedAsOf="2026-08-21",
                  trigger=IssueTrigger(kind="binding-constraint", label=V9)),
            Issue(id="constraint-hbm-stacked-memory-supply",
                  title=V8, state="open", openedAsOf="2026-08-19",
                  trigger=IssueTrigger(kind="binding-constraint", label=V8)),
        ],
    )
    reg2, opened = open_issues(reg, _scorecard(V10), "2026-08-22")
    # V10 overlaps V8 at 0.75 and V9 at 0.5 -> the higher ratio wins.
    assert opened == ["constraint-hbm-stacked-memory-supply"]
    assert len(reg2.issues) == 2


# --- the append-only guarantee and the counters --------------------------------

def test_history_and_counters_survive_a_rename(tmp_path):
    cat_dir = tmp_path / CATEGORY_ID
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    iid = reg.issues[0].id

    reg, lines = apply_assessments(
        reg,
        [{"issueId": iid, "status": "worsened", "reasoning": "worse",
          "claimFindingIds": ["f-1"]}],
        _scorecard(V8), "2026-08-19",
    )
    append_history(cat_dir, lines)
    history_path = cat_dir / "issues" / "history.jsonl"
    before_bytes = history_path.read_bytes()

    reg, _ = open_issues(reg, _scorecard(V9), "2026-08-21")

    issue = reg.issues[0]
    assert issue.id == iid, "the id is the thread history hangs on"
    assert issue.worsenedCount == 1
    assert issue.checkCount == 1
    assert issue.latest.reasoning == "worse"
    assert issue.openedAsOf == "2026-08-19"

    # Append-only: the rename touched no history line.
    assert history_path.read_bytes() == before_bytes
    tail = read_history_tail(cat_dir, iid, 5)
    assert [t["status"] for t in tail] == ["worsened"]


def test_renamed_issue_keeps_counting_under_the_new_label():
    """The point of the whole fix: after a relabel, an "unchanged" assessment
    while the constraint still fires must NOT count as improvement."""
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    reg, _ = open_issues(reg, _scorecard(V9), "2026-08-21")
    iid = reg.issues[0].id
    reg, _ = apply_assessments(
        reg,
        [{"issueId": iid, "status": "unchanged", "reasoning": "", "claimFindingIds": []}],
        _scorecard(V9), "2026-08-21",
    )
    assert reg.issues[0].improvedStreak == 0
    assert reg.issues[0].state == "open"


def test_without_the_fix_shape_a_stranded_twin_would_drift_to_resolved():
    """Guards the failure mode itself: five quiet cycles under a re-worded label
    must leave the issue open, because the rename keeps the trigger matching."""
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    reg, _ = open_issues(reg, _scorecard(V9), "2026-08-21")
    iid = reg.issues[0].id
    for day in ("2026-08-22", "2026-08-23", "2026-08-24", "2026-08-25", "2026-08-26"):
        reg, _ = apply_assessments(
            reg,
            [{"issueId": iid, "status": "unchanged", "reasoning": "",
              "claimFindingIds": []}],
            _scorecard(V9), day,
        )
    assert reg.issues[0].state == "open"
    assert reg.issues[0].resolvedAsOf is None


def test_positive_control_a_stranded_issue_really_does_drift_to_resolved():
    """Proves the guard above is not vacuous. Same five quiet cycles, but the
    issue is left stranded under the OLD label while the scorecard shows the new
    one -- exactly the pre-fix state. trigger_still_firing reads False, every
    "unchanged" counts as improvement, and the register tells the reader
    "Resolved" about a constraint that is still biting."""
    reg, _ = open_issues(_empty_register(), _scorecard(V8), "2026-08-19")
    iid = reg.issues[0].id
    for day in ("2026-08-22", "2026-08-23", "2026-08-24", "2026-08-25", "2026-08-26"):
        reg, _ = apply_assessments(
            reg,
            [{"issueId": iid, "status": "unchanged", "reasoning": "",
              "claimFindingIds": []}],
            _scorecard(V9), day,   # live scorecard names the NEW label
        )
    assert reg.issues[0].state == "resolved"
    assert reg.issues[0].resolvedAsOf == "2026-08-26"
