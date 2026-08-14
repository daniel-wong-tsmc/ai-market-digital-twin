"""F115 Task 7: the exporter's `issues` dashboard section.

Deterministic, no-clock: this section is built entirely from the on-disk
`gpu_agent.issues` register + history.jsonl (gpu_agent/issues.py, already
committed) -- never a fresh assessment, never a wall-clock read. Missing
register -> honest empty `{"open": [], "resolved": []}`, never an error
(the exporter's honest-empty and validate-before-write contracts both hold).
"""
import copy
import json
from pathlib import Path

import jsonschema

from gpu_agent import issues as issues_mod
from gpu_agent.dashboard.export_json import build_dashboard_payload

STORY = json.loads(Path("fixtures/dashboard/story-trimmed.json").read_text(encoding="utf-8"))
SCORECARD = json.loads(Path("fixtures/dashboard/scorecard-trimmed.json").read_text(encoding="utf-8"))
SCHEMA = json.loads(Path("web/schema/dashboard.schema.json").read_text(encoding="utf-8"))

# A finding genuinely present in the trimmed scorecard fixture, with real
# evidence -- so `sources` on the open+assessed issue resolves to a real ref,
# the exact same shape `refs_for_finding_ids` gives the bullets.
_REAL_FINDING_ID = "finance-yahoo-com-171fe64e-2026-08-1"


def _make_store(tmp_path: Path) -> Path:
    """A small, self-contained store tree -- same shape test_export_json.py's
    own `_make_store` builds, so build_dashboard_payload succeeds on the
    non-issues sections without dragging in that module's helpers."""
    cat_dir = tmp_path / "store" / "chips.merchant-gpu"
    cat_dir.mkdir(parents=True)
    (cat_dir / "story").mkdir()
    (tmp_path / "store" / "series").mkdir(parents=True)

    prev = {
        "categoryId": "chips.merchant-gpu", "asOf": "2026-07",
        "findings": [], "dimensionRatings": {},
        "demandSupply": {"dmiContribution": 2.0, "smiContribution": -1.0,
                          "anchors": {}, "sdgi": 3.0, "sdgiDirection": "demand-led"},
        "narrative": "Nothing to report.",
        "confidence": {"level": "medium", "basis": "prior month"},
        "categoryStatus": {"rating": "Strong", "direction": "improving",
                            "bottleneck": "bottleneck", "reason": "r"},
    }
    (cat_dir / "2026-07-v1.json").write_text(json.dumps(prev), encoding="utf-8")

    current = copy.deepcopy(SCORECARD)
    current["demandSupply"] = {"dmiContribution": 2.0, "smiContribution": -0.6,
                                "anchors": {}, "sdgi": 2.6, "sdgiDirection": "demand-led"}
    current["confidence"] = {"level": "high", "basis": "self-consistency over 3 samples"}
    (cat_dir / "2026-08-v1.json").write_text(json.dumps(current), encoding="utf-8")

    (cat_dir / "story" / "2026-08-05.json").write_text(json.dumps(STORY), encoding="utf-8")
    return tmp_path / "store"


def _write_register(store_dir: Path) -> None:
    """Writes a register with exactly the three issues the brief specifies:
    one open+assessed (worsened, real sources + capped/ordered history), one
    open+not-assessed (empty reasoning, no sources), one resolved."""
    cat_dir = store_dir / "chips.merchant-gpu"

    open_assessed = issues_mod.Issue(
        id="constraint-hbm4-stacked-memory-supply",
        title="HBM4 stacked-memory supply",
        state="open",
        openedAsOf="2026-07-01",
        trigger=issues_mod.IssueTrigger(kind="binding-constraint", label="HBM4 stacked-memory supply"),
        latest=issues_mod.IssueLatest(
            status="worsened",
            reasoning="Supply remains tight; packaging queues are still the limiter.",
            claimFindingIds=[_REAL_FINDING_ID],
            assessedAsOf="2026-08-10",
        ),
        improvedStreak=0,
        worsenedCount=3,
        checkCount=5,
    )
    open_not_assessed = issues_mod.Issue(
        id="dim-competitiveStructure",
        title="Competitive structure",
        state="open",
        openedAsOf="2026-08-01",
        trigger=issues_mod.IssueTrigger(kind="dimension-weak", label="competitiveStructure"),
        latest=issues_mod.IssueLatest(
            status="not-assessed",
            reasoning="",
            claimFindingIds=[],
            assessedAsOf="2026-08-10",
        ),
        improvedStreak=0,
        worsenedCount=0,
        checkCount=0,
    )
    resolved = issues_mod.Issue(
        id="dim-moat",
        title="Moat",
        state="resolved",
        openedAsOf="2026-06-01",
        resolvedAsOf="2026-08-01",
        trigger=issues_mod.IssueTrigger(kind="dimension-weak", label="moat"),
        latest=issues_mod.IssueLatest(
            status="improved",
            reasoning="Networking bundle held up for five straight checks.",
            claimFindingIds=[],
            assessedAsOf="2026-08-01",
        ),
        improvedStreak=5,
        worsenedCount=0,
        checkCount=5,
    )

    register = issues_mod.IssueRegister(
        schemaVersion=1, categoryId="chips.merchant-gpu", asOf="2026-08-10",
        issues=[open_assessed, open_not_assessed, resolved],
    )
    issues_mod.write_register(cat_dir, register)

    # 20 history lines for the open+assessed issue -- more than the 15-cap,
    # so the exporter's cap-and-order behaviour is genuinely exercised (not
    # vacuously true because there happen to be <= 15 on disk).
    lines = []
    for i in range(20):
        day = f"2026-07-{i + 1:02d}"
        lines.append({
            "asOf": day, "issueId": "constraint-hbm4-stacked-memory-supply",
            "status": "unchanged", "reasoning": "", "claimFindingIds": [],
            "triggerStillFiring": True, "streakAfter": 0,
        })
    issues_mod.append_history(cat_dir, lines)


def _build(tmp_path, with_register: bool = True):
    store_dir = _make_store(tmp_path)
    if with_register:
        _write_register(store_dir)
    return build_dashboard_payload("chips.merchant-gpu", str(store_dir))


# ---------------------------------------------------------------------------
# Honest empty: no register directory -> {"open": [], "resolved": []}, and
# the payload still validates (never an error).
# ---------------------------------------------------------------------------

def test_no_register_produces_honest_empty_lists(tmp_path):
    payload = _build(tmp_path, with_register=False)
    assert payload["issues"] == {"open": [], "resolved": []}
    jsonschema.validate(payload, SCHEMA)


# ---------------------------------------------------------------------------
# The full section, built exactly per the brief's payload shape.
# ---------------------------------------------------------------------------

def test_issues_section_is_built_from_the_register(tmp_path):
    payload = _build(tmp_path)
    jsonschema.validate(payload, SCHEMA)
    issues_section = payload["issues"]
    assert len(issues_section["open"]) == 2
    assert len(issues_section["resolved"]) == 1

    by_id = {i["id"]: i for i in issues_section["open"]}
    assessed = by_id["constraint-hbm4-stacked-memory-supply"]
    assert assessed["title"] == "HBM4 stacked-memory supply"
    assert assessed["status"] == "worsened"
    assert assessed["assessedAsOf"] == "2026-08-10"
    assert assessed["trackedSince"] == "2026-07-01"
    assert assessed["worsenedCount"] == 3
    assert assessed["checkCount"] == 5
    assert assessed["reasoning"] == "Supply remains tight; packaging queues are still the limiter."
    assert assessed["sources"], "expected a real resolved source from claimFindingIds"
    for ref in assessed["sources"]:
        assert ref["url"] is None or ref["url"].startswith("http")

    not_assessed = by_id["dim-competitiveStructure"]
    assert not_assessed["title"] == "Competitive structure"
    assert not_assessed["status"] == "not-assessed"
    assert not_assessed["reasoning"] == ""
    assert not_assessed["sources"] == []

    resolved = issues_section["resolved"][0]
    assert resolved["id"] == "dim-moat"
    assert resolved["title"] == "Moat"
    assert resolved["resolvedAsOf"] == "2026-08-01"
    assert resolved["finalNote"] == "Networking bundle held up for five straight checks."


# ---------------------------------------------------------------------------
# History: capped at the last 15, oldest first.
# ---------------------------------------------------------------------------

def test_history_is_capped_at_15_oldest_first(tmp_path):
    payload = _build(tmp_path)
    by_id = {i["id"]: i for i in payload["issues"]["open"]}
    history = by_id["constraint-hbm4-stacked-memory-supply"]["history"]
    assert len(history) == 15
    dates = [h["asOf"] for h in history]
    assert dates == sorted(dates)
    # The last 15 of 20 written days (2026-07-06 .. 2026-07-20 inclusive).
    assert dates[0] == "2026-07-06"
    assert dates[-1] == "2026-07-20"
    for h in history:
        assert set(h) == {"asOf", "status"}


def test_not_assessed_issue_has_no_history_entries_beyond_what_was_recorded(tmp_path):
    payload = _build(tmp_path)
    by_id = {i["id"]: i for i in payload["issues"]["open"]}
    assert by_id["dim-competitiveStructure"]["history"] == []


# ---------------------------------------------------------------------------
# Determinism: no wall-clock read, byte-identical across two runs.
# ---------------------------------------------------------------------------

def test_issues_section_is_byte_stable_across_two_runs(tmp_path):
    store_dir = _make_store(tmp_path)
    _write_register(store_dir)
    p1 = build_dashboard_payload("chips.merchant-gpu", str(store_dir))
    p2 = build_dashboard_payload("chips.merchant-gpu", str(store_dir))
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)


def test_schema_version_bumped_to_1_2(tmp_path):
    payload = _build(tmp_path, with_register=False)
    assert payload["schemaVersion"] == "1.2"
