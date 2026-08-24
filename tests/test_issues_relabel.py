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
