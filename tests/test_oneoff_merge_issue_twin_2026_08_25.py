"""One-time data cleanup (user-approved 2026-08-25): the register held two open
constraint issues for one real problem (stacked-memory / HBM supply).

F123 stops NEW twins from being minted; the pair that already existed had to be
merged by hand. `scripts/oneoff_merge_issue_twin_2026_08_25.py` does exactly that
merge, and this test pins its behaviour against an in-memory copy of the register
as it stood on 2026-08-25, before the script was run.

The fixture below is a verbatim copy of the two issues in question plus the
third, deliberately-untouched HBM4-allocation issue, so the "everything else is
byte-identical" assertion has something real to protect.
"""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from gpu_agent.issues import IssueRegister

_SCRIPT = (Path(__file__).resolve().parents[1]
           / "scripts" / "oneoff_merge_issue_twin_2026_08_25.py")


def _load_script():
    spec = importlib.util.spec_from_file_location("oneoff_merge_twin", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


oneoff = _load_script()

SURVIVOR_ID = "constraint-stacked-memory-and-server-dram"
TWIN_ID = "constraint-stacked-high-bandwidth-memory-supply"
UNRELATED_ID = "constraint-hbm4-memory-allocation-per-accelerator"

SURVIVOR_FINDING = "www-investing-com-87498f82-2026-08-1"
TWIN_FINDING = "en-sedaily-com-b1c000ac-2026-08-1"


def _register_before() -> dict:
    """The register as committed on 2026-08-25, trimmed to the constraint issues.

    Trimming is safe: the merge only ever looks issues up by id, and the two
    dimension issues in the real file are structurally identical to the
    unrelated constraint issue kept here as the untouched control."""
    return {
        "schemaVersion": 1,
        "categoryId": "chips.merchant-gpu",
        "asOf": "2026-08-25",
        "issues": [
            {
                "id": SURVIVOR_ID,
                "title": "HBM4 and server DRAM supply",
                "state": "open",
                "openedAsOf": "2026-08",
                "resolvedAsOf": None,
                "reopenedAsOf": [],
                "trigger": {
                    "kind": "binding-constraint",
                    "label": "HBM4 and server DRAM supply",
                },
                "latest": {
                    "status": "unchanged",
                    "reasoning": "No new memory-price or supply evidence arrived today.",
                    "claimFindingIds": [SURVIVOR_FINDING],
                    "assessedAsOf": "2026-08-25",
                },
                "improvedStreak": 0,
                "worsenedCount": 1,
                "checkCount": 5,
            },
            {
                "id": TWIN_ID,
                "title": "Stacked memory supply per accelerator",
                "state": "open",
                "openedAsOf": "2026-08",
                "resolvedAsOf": None,
                "reopenedAsOf": [],
                "trigger": {
                    "kind": "binding-constraint",
                    "label": "Stacked memory supply per accelerator",
                },
                "latest": {
                    "status": "unchanged",
                    "reasoning": "No new evidence arrived today.",
                    "claimFindingIds": [TWIN_FINDING],
                    "assessedAsOf": "2026-08-25",
                },
                "improvedStreak": 1,
                "worsenedCount": 0,
                "checkCount": 4,
            },
            {
                "id": UNRELATED_ID,
                "title": "HBM4 memory allocation per accelerator",
                "state": "open",
                "openedAsOf": "2026-08",
                "resolvedAsOf": None,
                "reopenedAsOf": [],
                "trigger": {
                    "kind": "binding-constraint",
                    "label": "HBM4 memory allocation per accelerator",
                },
                "latest": {
                    "status": "unchanged",
                    "reasoning": "No new allocation evidence arrived today.",
                    "claimFindingIds": ["some-other-finding-2026-08-1"],
                    "assessedAsOf": "2026-08-25",
                },
                "improvedStreak": 0,
                "worsenedCount": 0,
                "checkCount": 3,
            },
        ],
    }


def _merged_once() -> IssueRegister:
    reg = IssueRegister.model_validate(_register_before())
    merged, _ = oneoff.merge_twin(reg)
    return merged


def _by_id(register: IssueRegister, iid: str):
    return next((i for i in register.issues if i.id == iid), None)


def test_twin_is_removed_from_the_register():
    merged = _merged_once()
    assert _by_id(merged, TWIN_ID) is None
    assert [i.id for i in merged.issues] == [SURVIVOR_ID, UNRELATED_ID]


def test_survivor_claim_finding_ids_are_the_union_survivor_first():
    survivor = _by_id(_merged_once(), SURVIVOR_ID)
    assert survivor.latest.claimFindingIds == [SURVIVOR_FINDING, TWIN_FINDING]


def test_survivor_title_and_counters_are_unchanged():
    """Counters are NOT summed: both issues were checked on the same days."""
    survivor = _by_id(_merged_once(), SURVIVOR_ID)
    before = _register_before()["issues"][0]
    assert survivor.title == before["title"]
    assert survivor.checkCount == before["checkCount"] == 5
    assert survivor.worsenedCount == before["worsenedCount"] == 1
    assert survivor.improvedStreak == before["improvedStreak"] == 0
    assert survivor.trigger.label == before["trigger"]["label"]
    assert survivor.openedAsOf == before["openedAsOf"]
    assert survivor.latest.status == before["latest"]["status"]
    assert survivor.latest.reasoning == before["latest"]["reasoning"]


def test_every_other_issue_is_byte_identical():
    merged = _merged_once()
    before = _register_before()
    for iid in (UNRELATED_ID,):
        was = next(i for i in before["issues"] if i["id"] == iid)
        now = _by_id(merged, iid).model_dump()
        assert json.dumps(now, sort_keys=True) == json.dumps(was, sort_keys=True)


def test_register_envelope_is_unchanged():
    merged = _merged_once()
    before = _register_before()
    assert merged.schemaVersion == before["schemaVersion"]
    assert merged.categoryId == before["categoryId"]
    assert merged.asOf == before["asOf"]


def test_second_run_is_a_no_op():
    once = _merged_once()
    twice, note = oneoff.merge_twin(copy.deepcopy(once))
    assert json.dumps(twice.model_dump(), sort_keys=True) == json.dumps(
        once.model_dump(), sort_keys=True)
    assert oneoff.ALREADY_MERGED in note


def test_missing_survivor_is_refused_with_a_clear_message():
    data = _register_before()
    data["issues"] = [i for i in data["issues"] if i["id"] != SURVIVOR_ID]
    with pytest.raises(oneoff.MergeRefused) as exc:
        oneoff.merge_twin(IssueRegister.model_validate(data))
    assert SURVIVOR_ID in str(exc.value)


def test_twin_alone_without_survivor_is_refused():
    """Guards against running the script against some other category's register."""
    data = _register_before()
    data["issues"] = [i for i in data["issues"] if i["id"] == TWIN_ID]
    with pytest.raises(oneoff.MergeRefused):
        oneoff.merge_twin(IssueRegister.model_validate(data))


def test_duplicate_finding_ids_are_not_repeated():
    data = _register_before()
    data["issues"][1]["latest"]["claimFindingIds"] = [SURVIVOR_FINDING, TWIN_FINDING]
    merged, _ = oneoff.merge_twin(IssueRegister.model_validate(data))
    survivor = _by_id(merged, SURVIVOR_ID)
    assert survivor.latest.claimFindingIds == [SURVIVOR_FINDING, TWIN_FINDING]
