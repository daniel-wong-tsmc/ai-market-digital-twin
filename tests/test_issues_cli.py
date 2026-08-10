"""F115 Task 6: the `issues` CLI verb (open / update).

Pattern: tests/narrator/test_cli.py -- invoke gpu_agent.cli.main([...]) in-process
against a tmp store and assert return codes + on-disk side effects.

Fixture scorecard is imported verbatim from tests/test_issues_lifecycle.py's SCORECARD:
categoryStatus.constraintLabel is truthy (binding-constraint trigger); bottleneck and
moat are both Weak+worsening (dimension-weak triggers) -- three issues open from a
single scorecard, matching that module's own open_issues() coverage.
"""
from __future__ import annotations

import json

from gpu_agent.cli import main
from gpu_agent.issues import (
    Issue, IssueRegister, IssueTrigger, read_history_tail, read_register, write_register,
)
from gpu_agent.narrator.schema import IssueAssessment, NarratorMeta, StoryArtifact
from gpu_agent.narrator.store import StoryStore
from tests.dashboard.test_story_model import _store as _narrator_gate_store
from tests.narrator.test_gate import _ok as _ok_narrator_answer
from tests.narrator.test_inputs import CAT as NARRATOR_GATE_CAT
from tests.test_issues_lifecycle import SCORECARD

CAT = "chips.merchant-gpu"
OPENED_IDS = {"constraint-hbm4-stacked-memory-supply", "dim-bottleneck", "dim-moat"}


def _write_scorecard(store, month="2026-08", rev=5, scorecard=None):
    cat_dir = store / CAT
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / f"{month}-v{rev}.json").write_text(
        json.dumps(scorecard or SCORECARD), encoding="utf-8")
    return cat_dir


def _write_story(store, story_date, issues):
    meta = NarratorMeta(model="opus", promptHash="deadbeef", retries=0,
                        fellBack=False, wroteAt="2026-08-11T00:00:00+00:00")
    artifact = StoryArtifact(
        schemaVersion=3 if issues else 2, categoryId=CAT, storyDate=story_date,
        narratorMeta=meta, headline="h", deck="d", scenes=[], kpiPicks=[],
        calloutMonths=[], bullets=None, issues=issues)
    StoryStore(store).write(artifact)


def _open(store):
    return main(["issues", "open", "--category", CAT, "--store", str(store)])


# --- open ----------------------------------------------------------------------

def test_open_writes_register_with_constraint_and_two_dim_issues(tmp_path, capsys):
    _write_scorecard(tmp_path)
    rc = _open(tmp_path)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out["opened"]) == OPENED_IDS
    assert out["open"] == 3

    register = read_register(tmp_path / CAT, CAT)
    assert {i.id for i in register.issues} == OPENED_IDS
    assert all(i.state == "open" for i in register.issues)


def test_open_as_of_defaults_to_scorecard_own_as_of(tmp_path):
    _write_scorecard(tmp_path, month="2026-08", rev=5)
    _open(tmp_path)
    register = read_register(tmp_path / CAT, CAT)
    assert register.asOf == "2026-08"


def test_open_as_of_override(tmp_path):
    _write_scorecard(tmp_path, month="2026-08", rev=5)
    rc = main(["issues", "open", "--category", CAT, "--store", str(tmp_path),
               "--as-of", "2026-08-15"])
    assert rc == 0
    register = read_register(tmp_path / CAT, CAT)
    assert register.asOf == "2026-08-15"


def test_open_second_call_is_idempotent(tmp_path, capsys):
    _write_scorecard(tmp_path)
    _open(tmp_path)
    capsys.readouterr()
    rc = _open(tmp_path)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["opened"] == []
    assert out["open"] == 3


def test_open_missing_scorecard_exits_1_and_touches_nothing(tmp_path, capsys):
    rc = _open(tmp_path)
    assert rc == 1
    err = capsys.readouterr().err
    assert "gpu-agent issues: error:" in err
    assert not (tmp_path / CAT / "issues" / "register.json").exists()


# --- update ----------------------------------------------------------------------

def test_update_assessing_both_dim_issues_writes_register_and_history(tmp_path, capsys):
    _write_scorecard(tmp_path)
    _open(tmp_path)
    capsys.readouterr()
    story_date = "2026-08-11"
    _write_story(tmp_path, story_date, issues=[
        IssueAssessment(issueId="dim-bottleneck", status="improved",
                        reasoning="better", claimFindingIds=[]),
        IssueAssessment(issueId="dim-moat", status="improved",
                        reasoning="better", claimFindingIds=[]),
    ])
    rc = main(["issues", "update", "--category", CAT, "--store", str(tmp_path),
               "--story-date", story_date])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["assessed"] == 2
    assert out["notAssessed"] == 0
    assert out["resolved"] == []

    register = read_register(tmp_path / CAT, CAT)
    assert register.asOf == story_date
    bottleneck = next(i for i in register.issues if i.id == "dim-bottleneck")
    assert bottleneck.improvedStreak == 1
    assert bottleneck.latest.status == "improved"

    tail = read_history_tail(tmp_path / CAT, "dim-bottleneck", 10)
    assert len(tail) == 1
    assert tail[0]["asOf"] == story_date


def test_update_second_run_same_date_appends_again(tmp_path, capsys):
    _write_scorecard(tmp_path)
    _open(tmp_path)
    capsys.readouterr()
    story_date = "2026-08-11"
    _write_story(tmp_path, story_date, issues=[
        IssueAssessment(issueId="dim-bottleneck", status="improved",
                        reasoning="better", claimFindingIds=[]),
    ])
    rc1 = main(["issues", "update", "--category", CAT, "--store", str(tmp_path),
                "--story-date", story_date])
    assert rc1 == 0
    rc2 = main(["issues", "update", "--category", CAT, "--store", str(tmp_path),
                "--story-date", story_date])
    assert rc2 == 0
    tail = read_history_tail(tmp_path / CAT, "dim-bottleneck", 10)
    assert len(tail) == 2   # append-only -- both runs are recorded, not deduped


def test_update_no_issues_block_marks_all_open_not_assessed_and_freezes_streaks(tmp_path, capsys):
    _write_scorecard(tmp_path)
    _open(tmp_path)
    capsys.readouterr()
    story_date = "2026-08-11"
    _write_story(tmp_path, story_date, issues=None)
    rc = main(["issues", "update", "--category", CAT, "--store", str(tmp_path),
               "--story-date", story_date])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["assessed"] == 0
    assert out["notAssessed"] == 3
    assert out["resolved"] == []

    register = read_register(tmp_path / CAT, CAT)
    for issue in register.issues:
        assert issue.latest.status == "not-assessed"
        assert issue.improvedStreak == 0   # frozen, not advanced


def test_update_reaching_streak_five_prints_resolved(tmp_path, capsys):
    _write_scorecard(tmp_path)
    _open(tmp_path)
    capsys.readouterr()
    dates = ["2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14", "2026-08-15"]
    for i, story_date in enumerate(dates):
        _write_story(tmp_path, story_date, issues=[
            IssueAssessment(issueId="dim-bottleneck", status="improved",
                            reasoning="better", claimFindingIds=[]),
        ])
        rc = main(["issues", "update", "--category", CAT, "--store", str(tmp_path),
                   "--story-date", story_date])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        if i < 4:
            assert out["resolved"] == []
        else:
            assert out["resolved"] == ["dim-bottleneck"]

    register = read_register(tmp_path / CAT, CAT)
    bottleneck = next(i for i in register.issues if i.id == "dim-bottleneck")
    assert bottleneck.state == "resolved"
    assert bottleneck.resolvedAsOf == dates[-1]


def test_update_missing_artifact_exits_1_and_register_untouched(tmp_path, capsys):
    _write_scorecard(tmp_path)
    _open(tmp_path)
    before = (tmp_path / CAT / "issues" / "register.json").read_bytes()
    capsys.readouterr()
    rc = main(["issues", "update", "--category", CAT, "--store", str(tmp_path),
               "--story-date", "2026-09-01"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "gpu-agent issues: error:" in err
    after = (tmp_path / CAT / "issues" / "register.json").read_bytes()
    assert after == before


# --- narrator writer schemaVersion conditional (F115 Task 6, user-decided 2026-08-10) ------
#
# gpu_agent/cli.py's `narrator --recorded` writer hard-coded schemaVersion=2 (F114 Task
# 5b). The plan wants F115 artifacts to be genuinely v3-shaped, but no task ever bumped
# the writer, so the user was asked and chose (interactively, 2026-08-10):
#   artifact = StoryArtifact(schemaVersion=3 if answer.issues else 2, ...)
# so the version number honestly means "this artifact carries issue assessments" --
# mirroring the F114 precedent (1->2 bumped when bullets became mandatory). The
# --record-fallback path (no issues block, untouched) already has its own coverage in
# tests/narrator/test_cli.py::test_record_fallback_writes_fellback asserting
# schemaVersion == 1 unchanged; not re-tested here.
#
# tests/narrator/test_cli.py::test_recorded_clean_writes_schema_version_2_with_bullets
# already covers the WITHOUT-issues side (answer.issues is None -> stays 2); this test
# covers the WITH-issues side.

def test_recorded_narrator_answer_with_issues_writes_schema_version_3(tmp_path, capsys):
    store = _narrator_gate_store(tmp_path)
    # Give the store one open issue so `answer.issues` clears gate check 9 (F115 Task 3):
    # every open issue must get exactly one assessment.
    register = IssueRegister(schemaVersion=1, categoryId=NARRATOR_GATE_CAT, asOf="2026-07-01",
                             issues=[
        Issue(id="dim-bottleneck", title="Bottleneck", state="open", openedAsOf="2026-07-01",
              trigger=IssueTrigger(kind="dimension-weak", label="bottleneck")),
    ])
    write_register(store / NARRATOR_GATE_CAT, register)

    answer = _ok_narrator_answer(tmp_path)
    answer.issues = [
        IssueAssessment(issueId="dim-bottleneck", status="unchanged",
                        reasoning="No new evidence changed the memory supply picture "
                                  "this week.",
                        claimFindingIds=["f-1"]),
    ]
    ap = tmp_path / "answer.json"
    ap.write_text(answer.model_dump_json(), encoding="utf-8")
    date = "2026-07-23"
    rc = main(["narrator", "--recorded", str(ap), "--store", str(store),
               "--category", NARRATOR_GATE_CAT, "--date", date, "--model", "opus",
               "--retries", "1"])
    assert rc == 0
    art = StoryStore(store).read(NARRATOR_GATE_CAT, date)
    assert art is not None
    assert art.schemaVersion == 3
    assert art.issues is not None
    assert art.issues[0].issueId == "dim-bottleneck"
