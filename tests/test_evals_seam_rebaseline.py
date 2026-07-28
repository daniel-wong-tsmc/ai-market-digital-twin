"""F108 seam-scoped rebaseline: rebuild only the named seams, carry every other seam's
baseline entry forward unchanged, narrow the dispersion guard to the seams being rebuilt.
Spec: docs/superpowers/specs/2026-07-28-f108-seam-scoped-rebaseline-design.md."""
from __future__ import annotations
import copy
import json
import pytest
from gpu_agent.evals.cases import EvalCase
from gpu_agent.evals.harness import (
    build_baseline_v2, case_seam, load_baseline, merge_baseline_seam_scoped, rebaseline_v2)

SEAMS = ("extract", "judge", "thesis")
OLD_HASHES = {"extract": "a" * 64, "judge": "b" * 64, "thesis": "c" * 64}
NEW_HASHES = dict(OLD_HASHES, extract="d" * 64)
DOC = {"id": "d1", "source": "s", "url": "http://x", "date": "2026-07-01",
       "tier": "primary", "entity": "NVDA", "content": "Blackwell shipments doubled."}


def _case(case_id, seam, kind="positive"):
    return EvalCase.model_validate({
        "caseId": case_id, "seam": seam, "kind": kind, "source": "t",
        "input": {"doc": DOC, "asOf": "2026-07-03"},
        "recordedAnswer": json.dumps({"drafts": []}),
        "checks": {"gateOutcome": "pass"}, "notes": "n"})


CASES = [_case("extract-e1", "extract"), _case("extract-e2", "extract"),
         _case("extract-n1", "extract", kind="negative"),
         _case("judge-j1", "judge"), _case("judge-j2", "judge"),
         _case("judge-n1", "judge", kind="negative"),
         _case("thesis-t1", "thesis"), _case("thesis-t2", "thesis"),
         _case("thesis-n1", "thesis", kind="negative")]


def _report(extract, judge, thesis, scores, hashes=OLD_HASHES, as_of="2026-07-18",
            calibrated=True):
    negatives = ["extract-n1", "judge-n1", "thesis-n1"]
    all_scores = dict(scores, **{n: 0 for n in negatives})
    return {"seamMeans": {"extract": extract, "judge": judge, "thesis": thesis},
            "scores": {cid: {"total": t, "grades": {"k": t}} for cid, t in all_scores.items()},
            "calibration": {n: {"score": 0 if calibrated else 9, "max": 4, "ok": calibrated}
                            for n in negatives},
            "promptHashes": hashes, "asOf": as_of}


def _old_reports():
    """The incumbent's three runs: every seam tight."""
    return [_report(6.5, 8.0, 6.0, {"extract-e1": 6, "extract-e2": 7,
                                    "judge-j1": 8, "judge-j2": 8,
                                    "thesis-t1": 6, "thesis-t2": 6}),
            _report(6.5, 8.0, 6.0, {"extract-e1": 6, "extract-e2": 7,
                                    "judge-j1": 8, "judge-j2": 8,
                                    "thesis-t1": 6, "thesis-t2": 6}),
            _report(6.0, 8.0, 6.0, {"extract-e1": 6, "extract-e2": 6,
                                    "judge-j1": 8, "judge-j2": 8,
                                    "thesis-t1": 6, "thesis-t2": 6})]


def _new_reports(hashes=NEW_HASHES):
    """The F105 shape: extract tight and moved, thesis wildly dispersed but unmoved."""
    return [_report(7.0, 7.5, 5.0, {"extract-e1": 7, "extract-e2": 7,
                                    "judge-j1": 7, "judge-j2": 8,
                                    "thesis-t1": 5, "thesis-t2": 5},
                    hashes=hashes, as_of="2026-07-28"),
            _report(7.0, 7.5, 7.5, {"extract-e1": 7, "extract-e2": 7,
                                    "judge-j1": 7, "judge-j2": 8,
                                    "thesis-t1": 7, "thesis-t2": 8},
                    hashes=hashes, as_of="2026-07-28"),
            _report(6.5, 7.5, 5.5, {"extract-e1": 6, "extract-e2": 7,
                                    "judge-j1": 7, "judge-j2": 8,
                                    "thesis-t1": 5, "thesis-t2": 6},
                    hashes=hashes, as_of="2026-07-28")]


def _incumbent():
    return build_baseline_v2(_old_reports(), ["old-r1", "old-r2", "old-r3"], CASES,
                             None, "incumbent whole-baseline rebuild")


def _fresh(hashes=NEW_HASHES):
    return build_baseline_v2(_new_reports(hashes), ["new-r1", "new-r2", "new-r3"], CASES,
                             None, "F105 extract change")


def _write_runs(tmp_path, reports, name="r"):
    dirs = []
    for i, rep in enumerate(reports):
        d = tmp_path / f"{name}{i + 1}"
        d.mkdir(parents=True)
        (d / "report.json").write_text(json.dumps(rep), "utf-8")
        dirs.append(d)
    return dirs


def _verdict(hashes=NEW_HASHES, decision="pass", gated=True, ok=True):
    return {"decision": decision, "promptHashes": hashes,
            "seams": {"extract": {"value": 6.833, "bar": 5.6, "gated": gated, "ok": ok},
                      "judge": {"value": 7.5, "bar": 7.75, "gated": False, "ok": False},
                      "thesis": {"value": 6.0, "bar": 5.5, "gated": False, "ok": True}}}


# --- Task 1: shared case-to-seam matching --------------------------------------

def test_case_seam_exact_and_prefix():
    seams = {"extract", "judge", "thesis"}
    assert case_seam("extract-2026-07-01", seams) == "extract"
    assert case_seam("judge", seams) == "judge"


def test_case_seam_longest_prefix_wins():
    seams = {"judge", "judge-hard"}
    assert case_seam("judge-hard-01", seams) == "judge-hard"


def test_case_seam_unmappable_is_none():
    assert case_seam("mystery-01", {"extract", "judge"}) is None


# --- Task 2: the merge ---------------------------------------------------------

def test_merge_carries_unnamed_seam_scalars_unchanged():
    inc, fresh = _incumbent(), _fresh()
    out = merge_baseline_seam_scoped(inc, fresh, ["extract"], ["new-r1", "new-r2", "new-r3"],
                                     None, "F105")
    for field in ("seamMeans", "epsilon", "quanta", "seamHistory", "promptHashes"):
        for seam in ("judge", "thesis"):
            assert out[field][seam] == inc[field][seam], f"{field}/{seam} was not carried"


def test_merge_takes_named_seam_scalars_from_fresh():
    inc, fresh = _incumbent(), _fresh()
    out = merge_baseline_seam_scoped(inc, fresh, ["extract"], ["new-r1", "new-r2", "new-r3"],
                                     None, "F105")
    for field in ("seamMeans", "epsilon", "quanta", "seamHistory", "promptHashes"):
        assert out[field]["extract"] == fresh[field]["extract"], f"{field} not rebuilt"


def test_merge_named_seam_history_is_replaced_not_appended():
    inc, fresh = _incumbent(), _fresh()
    out = merge_baseline_seam_scoped(inc, fresh, ["extract"], ["new-r1", "new-r2", "new-r3"],
                                     None, "F105")
    assert len(out["seamHistory"]["extract"]) == 3
    assert out["seamHistory"]["extract"] == [r["seamMeans"]["extract"] for r in _new_reports()]


def test_merge_case_medians_split_by_seam():
    inc, fresh = _incumbent(), _fresh()
    out = merge_baseline_seam_scoped(inc, fresh, ["extract"], ["new-r1", "new-r2", "new-r3"],
                                     None, "F105")
    assert out["caseMedians"]["extract-e1"] == fresh["caseMedians"]["extract-e1"]
    assert out["caseMedians"]["thesis-t1"] == inc["caseMedians"]["thesis-t1"]
    assert out["caseMedians"]["judge-j1"] == inc["caseMedians"]["judge-j1"]


def test_merge_replicates_keep_three_entries_and_all_seams():
    inc, fresh = _incumbent(), _fresh()
    out = merge_baseline_seam_scoped(inc, fresh, ["extract"], ["new-r1", "new-r2", "new-r3"],
                                     None, "F105")
    assert len(out["replicates"]) == 3
    for i, rep in enumerate(out["replicates"]):
        assert set(rep["seamMeans"]) == set(SEAMS)
        assert rep["runDir"] == inc["replicates"][i]["runDir"]
        assert rep["asOf"] == inc["replicates"][i]["asOf"]


def test_merge_replicates_splice_per_seam():
    inc, fresh = _incumbent(), _fresh()
    out = merge_baseline_seam_scoped(inc, fresh, ["extract"], ["new-r1", "new-r2", "new-r3"],
                                     None, "F105")
    for i, rep in enumerate(out["replicates"]):
        assert rep["seamMeans"]["extract"] == fresh["replicates"][i]["seamMeans"]["extract"]
        assert rep["seamMeans"]["thesis"] == inc["replicates"][i]["seamMeans"]["thesis"]
        assert rep["cases"]["extract-e1"] == fresh["replicates"][i]["cases"]["extract-e1"]
        assert rep["cases"]["thesis-t1"] == inc["replicates"][i]["cases"]["thesis-t1"]
        # negatives travel with their seam
        assert rep["cases"]["extract-n1"] == fresh["replicates"][i]["cases"]["extract-n1"]
        assert rep["cases"]["judge-n1"] == inc["replicates"][i]["cases"]["judge-n1"]


def test_merge_replicates_record_seam_run_dirs():
    inc, fresh = _incumbent(), _fresh()
    out = merge_baseline_seam_scoped(inc, fresh, ["extract"], ["new-r1", "new-r2", "new-r3"],
                                     None, "F105")
    for i, rep in enumerate(out["replicates"]):
        assert rep["seamRunDirs"]["extract"] == f"new-r{i + 1}"
        assert rep["seamRunDirs"]["judge"] == inc["replicates"][i]["runDir"]
        assert rep["seamRunDirs"]["thesis"] == inc["replicates"][i]["runDir"]


def test_merge_does_not_mutate_its_inputs():
    inc, fresh = _incumbent(), _fresh()
    inc_before, fresh_before = copy.deepcopy(inc), copy.deepcopy(fresh)
    merge_baseline_seam_scoped(inc, fresh, ["extract"], ["new-r1", "new-r2", "new-r3"],
                               None, "F105")
    assert inc == inc_before and fresh == fresh_before


def test_merge_top_level_provenance_untouched():
    inc, fresh = _incumbent(), _fresh()
    out = merge_baseline_seam_scoped(inc, fresh, ["extract"], ["new-r1", "new-r2", "new-r3"],
                                     "forced for a reason", "F105")
    for field in ("asOf", "graderModel", "forceReason", "humanReview"):
        assert out["provenance"][field] == inc["provenance"][field]


def test_merge_records_scoped_provenance():
    inc, fresh = _incumbent(), _fresh()
    out = merge_baseline_seam_scoped(inc, fresh, ["extract"], ["new-r1", "new-r2", "new-r3"],
                                     None, "F105 extract-strict")
    entry = out["provenance"]["seamRebaselines"]["extract"]
    assert entry["asOf"] == "2026-07-28"
    assert entry["runDirs"] == ["new-r1", "new-r2", "new-r3"]
    assert entry["humanReview"] == "F105 extract-strict"
    assert entry["forceReason"] is None
    assert set(out["provenance"]["seamRebaselines"]) == {"extract"}


def test_merge_scoped_provenance_accumulates_across_seams():
    inc, fresh = _incumbent(), _fresh()
    once = merge_baseline_seam_scoped(inc, fresh, ["extract"],
                                      ["new-r1", "new-r2", "new-r3"], None, "first")
    twice = merge_baseline_seam_scoped(once, fresh, ["thesis"],
                                       ["t-r1", "t-r2", "t-r3"], "recalibrating", "second")
    assert set(twice["provenance"]["seamRebaselines"]) == {"extract", "thesis"}
    assert twice["provenance"]["seamRebaselines"]["extract"]["humanReview"] == "first"
    assert twice["provenance"]["seamRebaselines"]["thesis"]["forceReason"] == "recalibrating"


def test_merge_keeps_an_earlier_scoped_seams_run_dirs_when_it_is_carried():
    """extract rebuilt first, then thesis: extract must keep pointing at ITS runs, not
    fall back to the entry's original runDir."""
    inc, fresh = _incumbent(), _fresh()
    once = merge_baseline_seam_scoped(inc, fresh, ["extract"],
                                      ["new-r1", "new-r2", "new-r3"], None, "first")
    twice = merge_baseline_seam_scoped(once, fresh, ["thesis"],
                                       ["t-r1", "t-r2", "t-r3"], "recalibrating", "second")
    for i, rep in enumerate(twice["replicates"]):
        assert rep["seamRunDirs"]["extract"] == f"new-r{i + 1}"
        assert rep["seamRunDirs"]["thesis"] == f"t-r{i + 1}"
        assert rep["seamRunDirs"]["judge"] == inc["replicates"][i]["runDir"]
        assert rep["seamMeans"]["extract"] == fresh["replicates"][i]["seamMeans"]["extract"]


def test_merge_schema_version_not_bumped():
    inc, fresh = _incumbent(), _fresh()
    out = merge_baseline_seam_scoped(inc, fresh, ["extract"], ["new-r1", "new-r2", "new-r3"],
                                     None, "F105")
    assert out["schemaVersion"] == inc["schemaVersion"] == 2


def test_merge_result_json_round_trips(tmp_path):
    inc, fresh = _incumbent(), _fresh()
    out = merge_baseline_seam_scoped(inc, fresh, ["extract"], ["new-r1", "new-r2", "new-r3"],
                                     None, "F105")
    p = tmp_path / "b.json"
    p.write_text(json.dumps(out, indent=2, sort_keys=True), "utf-8")
    assert json.loads(p.read_text("utf-8")) == out


# --- Task 3: guards and wiring -------------------------------------------------

def _scoped(tmp_path, name="n", seams=("extract",), reports=None, hashes=NEW_HASHES,
            verdict=None, force_reason=None, baseline=None):
    out = baseline if baseline is not None else tmp_path / "baseline.json"
    dirs = _write_runs(tmp_path / name, reports if reports is not None else _new_reports(hashes))
    return rebaseline_v2(dirs, out, hashes, CASES, seams=list(seams),
                         verdict=verdict if verdict is not None else _verdict(hashes),
                         force_reason=force_reason, human_review="F105")


def _seeded(tmp_path):
    out = tmp_path / "baseline.json"
    out.write_text(json.dumps(_incumbent(), indent=2, sort_keys=True), "utf-8")
    return out


def test_scoped_rebaseline_happy_path_carries_unnamed_seams(tmp_path):
    out = _seeded(tmp_path)
    inc = load_baseline(out)
    _scoped(tmp_path, baseline=out)
    got = load_baseline(out)
    for seam in ("judge", "thesis"):
        for field in ("seamMeans", "epsilon", "quanta", "seamHistory", "promptHashes"):
            assert got[field][seam] == inc[field][seam]
    assert got["seamMeans"]["extract"] != inc["seamMeans"]["extract"]


def test_scoped_rebaseline_pins_the_current_tree_hashes(tmp_path):
    """The whole point for the F6 pin: after a scoped rebaseline the stored hashes must
    equal the working tree's, or the pin stays red."""
    out = _seeded(tmp_path)
    _scoped(tmp_path, baseline=out)
    assert load_baseline(out)["promptHashes"] == NEW_HASHES


def test_scoped_dispersion_guard_ignores_unnamed_seams(tmp_path):
    """thesis ranges 2.5 across the new runs; naming only extract must still succeed."""
    out = _seeded(tmp_path)
    _scoped(tmp_path, baseline=out)
    assert load_baseline(out)["provenance"]["seamRebaselines"]["extract"]


def test_scoped_dispersion_guard_applies_to_named_seams(tmp_path):
    out = _seeded(tmp_path)
    with pytest.raises(ValueError, match="dispersion"):
        _scoped(tmp_path, seams=("extract", "thesis"), baseline=out,
                force_reason=None, verdict=_verdict())


def test_scoped_refuses_without_an_incumbent(tmp_path):
    with pytest.raises(ValueError, match="incumbent|existing"):
        _scoped(tmp_path, baseline=tmp_path / "missing.json")


def test_scoped_refuses_on_v1_incumbent(tmp_path):
    out = tmp_path / "baseline.json"
    out.write_text(json.dumps({"promptHashes": OLD_HASHES, "seamMeans": {"extract": 6.5},
                               "provenance": {}}), "utf-8")
    with pytest.raises(ValueError, match="schema|v2"):
        _scoped(tmp_path, baseline=out)


def test_scoped_refuses_when_incumbent_lacks_three_replicates(tmp_path):
    inc = _incumbent()
    inc["replicates"] = inc["replicates"][:2]
    out = tmp_path / "baseline.json"
    out.write_text(json.dumps(inc), "utf-8")
    with pytest.raises(ValueError, match="3 replicate"):
        _scoped(tmp_path, baseline=out)


def test_scoped_refuses_unknown_seam_name(tmp_path):
    out = _seeded(tmp_path)
    with pytest.raises(ValueError, match="unknown seam"):
        _scoped(tmp_path, seams=("extrakt",), baseline=out)


def test_scoped_refuses_when_an_unnamed_seam_also_drifted(tmp_path):
    out = _seeded(tmp_path)
    drifted = dict(NEW_HASHES, judge="e" * 64)
    with pytest.raises(ValueError, match="judge"):
        _scoped(tmp_path, hashes=drifted, baseline=out, verdict=_verdict(drifted))


def test_scoped_refuses_naming_an_unchanged_seam_without_force(tmp_path):
    # nothing in the tree has drifted; judge is named purely to re-measure its bar
    out = _seeded(tmp_path)
    with pytest.raises(ValueError, match="force"):
        _scoped(tmp_path, seams=("judge",), hashes=OLD_HASHES, baseline=out)


def test_scoped_allows_naming_an_unchanged_seam_with_force(tmp_path):
    out = _seeded(tmp_path)
    _scoped(tmp_path, seams=("judge",), hashes=OLD_HASHES, baseline=out,
            force_reason="recalibrating after F107")
    got = load_baseline(out)
    assert got["provenance"]["seamRebaselines"]["judge"]["forceReason"] == \
        "recalibrating after F107"
    assert got["provenance"]["forceReason"] is None      # top level never written


def test_scoped_refuses_without_a_verdict(tmp_path):
    out = _seeded(tmp_path)
    with pytest.raises(ValueError, match="verdict"):
        _scoped(tmp_path, baseline=out, verdict={})


def test_scoped_refuses_on_a_non_pass_verdict(tmp_path):
    out = _seeded(tmp_path)
    with pytest.raises(ValueError, match="verdict"):
        _scoped(tmp_path, baseline=out, verdict=_verdict(decision="marginal-fail"))


def test_scoped_refuses_when_named_seam_only_informational(tmp_path):
    out = _seeded(tmp_path)
    with pytest.raises(ValueError, match="gated|informational"):
        _scoped(tmp_path, baseline=out, verdict=_verdict(gated=False))


def test_scoped_refuses_when_named_seam_missed_its_bar(tmp_path):
    out = _seeded(tmp_path)
    with pytest.raises(ValueError, match="bar|ok"):
        _scoped(tmp_path, baseline=out, verdict=_verdict(ok=False))


def test_scoped_force_overrides_verdict_governance(tmp_path):
    out = _seeded(tmp_path)
    _scoped(tmp_path, baseline=out, verdict={}, force_reason="operator override")
    assert load_baseline(out)["promptHashes"]["extract"] == NEW_HASHES["extract"]


def test_scoped_refuses_unmappable_case_id(tmp_path):
    out = _seeded(tmp_path)
    reports = _new_reports()
    for r in reports:
        r["scores"]["mystery-01"] = {"total": 5, "grades": {}}
    with pytest.raises(ValueError, match="mystery-01"):
        _scoped(tmp_path, reports=reports, baseline=out)


def test_scoped_still_refuses_stale_runs(tmp_path):
    """The pre-existing whole-baseline guards are not weakened by scoping."""
    out = _seeded(tmp_path)
    with pytest.raises(ValueError, match="current"):
        dirs = _write_runs(tmp_path / "stale", _new_reports(OLD_HASHES))
        rebaseline_v2(dirs, out, NEW_HASHES, CASES, seams=["extract"],
                      verdict=_verdict(), human_review="x")


def test_scoped_still_refuses_a_miscalibrated_grader(tmp_path):
    out = _seeded(tmp_path)
    reports = _new_reports()
    reports[1]["calibration"]["thesis-n1"] = {"score": 9, "max": 4, "ok": False}
    with pytest.raises(ValueError, match="calibrat"):
        _scoped(tmp_path, reports=reports, baseline=out)


# --- the default path must not move -------------------------------------------

def test_no_seams_path_is_byte_identical_to_todays_output(tmp_path):
    out = tmp_path / "baseline.json"
    dirs = _write_runs(tmp_path / "w", _old_reports())
    rebaseline_v2(dirs, out, OLD_HASHES, CASES, human_review="whole")
    expected = build_baseline_v2(_old_reports(), [str(d) for d in dirs], CASES, None, "whole")
    assert json.loads(out.read_text("utf-8")) == expected
    assert "seamRebaselines" not in expected["provenance"]
    assert all("seamRunDirs" not in r for r in expected["replicates"])
