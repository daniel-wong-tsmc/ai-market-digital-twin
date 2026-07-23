"""F101b Task 4: the `narrator` CLI verb (emit / accept / fallback).

Pattern: tests/test_cli_implication.py -- invoke gpu_agent.cli.main([...]) and assert
return codes + store side effects. Fixture inputs come from tests/narrator/test_gate.py's
_ok() (a NarratorAnswer that passes gate_narrator against tests/dashboard/test_story_model's
_store fixture) so the "clean answer" path exercises the real gate, not a stub.
"""
from __future__ import annotations
import hashlib
import json

from gpu_agent.cli import main
from tests.narrator.test_gate import _ok
from tests.narrator.test_inputs import CAT
from tests.dashboard.test_story_model import _store
from gpu_agent.narrator.store import StoryStore

DATE = "2026-07-23"


def test_emit_prints_bundle(tmp_path, capsys):
    store = _store(tmp_path)
    rc = main(["narrator", "--emit-prompt", "--store", str(store),
               "--category", CAT, "--date", DATE])
    assert rc == 0
    bundle = json.loads(capsys.readouterr().out)
    assert set(bundle) == {"system", "schema", "user"}
    assert "scenes" in bundle["schema"]["properties"]


def test_recorded_clean_writes_artifact(tmp_path, capsys):
    store = _store(tmp_path)
    answer = _ok(tmp_path)
    ap = tmp_path / "answer.json"
    ap.write_text(answer.model_dump_json(), encoding="utf-8")
    rc = main(["narrator", "--recorded", str(ap), "--store", str(store),
               "--category", CAT, "--date", DATE, "--model", "opus",
               "--retries", "1"])
    assert rc == 0
    capsys.readouterr()   # discard the "wrote <path>" line before the --emit-prompt call below
    art = StoryStore(store).read(CAT, DATE)
    assert art is not None
    assert art.headline == answer.headline
    assert art.categoryId == CAT and art.storyDate == DATE
    assert art.narratorMeta.model == "opus"
    assert art.narratorMeta.retries == 1
    assert art.narratorMeta.fellBack is False
    assert art.narratorMeta.wroteAt

    # promptHash must equal sha256 of the exact bundle --emit-prompt would print for the
    # same store/category/date (the canonicalization Task 6's pin recipe uses), not just
    # be a non-empty string.
    rc_emit = main(["narrator", "--emit-prompt", "--store", str(store),
                     "--category", CAT, "--date", DATE])
    assert rc_emit == 0
    bundle = json.loads(capsys.readouterr().out)
    expected_hash = hashlib.sha256(
        json.dumps(bundle, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    assert art.narratorMeta.promptHash == expected_hash


def test_recorded_gate_fail_writes_nothing(tmp_path, capsys):
    store = _store(tmp_path)
    answer = _ok(tmp_path)
    answer.deck = "Demand momentum is strengthening."   # banned word -> gate fail
    ap = tmp_path / "answer.json"
    ap.write_text(answer.model_dump_json(), encoding="utf-8")
    rc = main(["narrator", "--recorded", str(ap), "--store", str(store),
               "--category", CAT, "--date", DATE])
    assert rc == 1
    out = capsys.readouterr().out
    assert "NARRATOR GATE FAILED" in out
    # Minor A: the exact bare marker line (no trailing colon) is what Task 7's
    # orchestrator matches on -- assert it precisely, not just substring-present.
    assert "NARRATOR GATE FAILED" in out.splitlines()
    assert not (store / CAT / "story" / f"{DATE}.json").exists()


def test_recorded_invalid_json_writes_nothing(tmp_path, capsys):
    # Missing required fields -> pydantic ValidationError, same failure marker/path as a
    # gate rejection (the interface spec's "pydantic errors -> print NARRATOR GATE FAILED").
    store = _store(tmp_path)
    ap = tmp_path / "bad.json"
    ap.write_text(json.dumps({"headline": "x"}), encoding="utf-8")
    rc = main(["narrator", "--recorded", str(ap), "--store", str(store),
               "--category", CAT, "--date", DATE])
    assert rc == 1
    assert "NARRATOR GATE FAILED" in capsys.readouterr().out
    assert not (store / CAT / "story" / f"{DATE}.json").exists()


def test_recorded_gate_fail_leaves_existing_artifact_byte_unchanged(tmp_path):
    # Controller note: a failure path must leave the store byte-unchanged, not merely
    # "the file doesn't exist" -- seed a real artifact first, then prove a later failing
    # --recorded call for the same category/date doesn't touch it at all.
    store = _store(tmp_path)
    good = _ok(tmp_path)
    ap0 = tmp_path / "good.json"
    ap0.write_text(good.model_dump_json(), encoding="utf-8")
    rc0 = main(["narrator", "--recorded", str(ap0), "--store", str(store),
                "--category", CAT, "--date", DATE])
    assert rc0 == 0
    p = store / CAT / "story" / f"{DATE}.json"
    before = p.read_bytes()

    bad = _ok(tmp_path)
    bad.deck = "Demand momentum is strengthening."
    ap1 = tmp_path / "bad.json"
    ap1.write_text(bad.model_dump_json(), encoding="utf-8")
    rc1 = main(["narrator", "--recorded", str(ap1), "--store", str(store),
                "--category", CAT, "--date", DATE])
    assert rc1 == 1
    assert p.read_bytes() == before
    assert not p.with_suffix(".json.tmp").exists()   # atomic write leaves no stray .tmp


def test_record_fallback_writes_fellback(tmp_path):
    store = _store(tmp_path)
    reasons = tmp_path / "reasons.json"
    reasons.write_text(json.dumps(["banned word: momentum", "unknown finding id: f-x"]),
                        encoding="utf-8")
    rc = main(["narrator", "--record-fallback", "--reasons", str(reasons),
               "--store", str(store), "--category", CAT, "--date", DATE])
    assert rc == 0
    art = StoryStore(store).read(CAT, DATE)
    assert art is not None
    assert art.headline == "" and art.deck == ""
    assert art.scenes == [] and art.kpiPicks == [] and art.calloutMonths == []
    assert art.narratorMeta.fellBack is True
    assert art.narratorMeta.promptHash        # still filled: computed from real inputs
    fallback_log = store / CAT / "story" / f"{DATE}.fallback.json"
    assert fallback_log.exists()
    assert "momentum" in fallback_log.read_text(encoding="utf-8")


def test_neither_flag_exits_2(tmp_path):
    store = _store(tmp_path)
    rc = main(["narrator", "--store", str(store), "--category", CAT, "--date", DATE])
    assert rc == 2


def test_record_fallback_without_reasons_exits_2(tmp_path):
    store = _store(tmp_path)
    rc = main(["narrator", "--record-fallback", "--store", str(store),
               "--category", CAT, "--date", DATE])
    assert rc == 2


def test_recorded_missing_file_exits_1_cleanly(tmp_path, capsys):
    # Important 1: a missing --recorded file must exit 1 with a clean message, never
    # crash main() with a raw traceback (this is the orchestrator's daily-cycle path).
    store = _store(tmp_path)
    rc = main(["narrator", "--recorded", str(tmp_path / "nope.json"), "--store", str(store),
               "--category", CAT, "--date", DATE])
    assert rc == 1
    err = capsys.readouterr().err
    assert "gpu-agent narrator: error:" in err
    assert not (store / CAT / "story" / f"{DATE}.json").exists()


def test_record_fallback_missing_reasons_file_exits_1_cleanly(tmp_path, capsys):
    # Important 1: --record-fallback is the safety valve used when things have already
    # gone wrong -- a bad --reasons path must not crash the fallback itself.
    store = _store(tmp_path)
    rc = main(["narrator", "--record-fallback", "--reasons", str(tmp_path / "nope.json"),
               "--store", str(store), "--category", CAT, "--date", DATE])
    assert rc == 1
    err = capsys.readouterr().err
    assert "gpu-agent narrator: error:" in err
    assert not (store / CAT / "story" / f"{DATE}.json").exists()


def test_record_fallback_malformed_reasons_json_exits_1_cleanly(tmp_path, capsys):
    store = _store(tmp_path)
    reasons = tmp_path / "reasons.json"
    reasons.write_text("{not valid json", encoding="utf-8")
    rc = main(["narrator", "--record-fallback", "--reasons", str(reasons),
               "--store", str(store), "--category", CAT, "--date", DATE])
    assert rc == 1
    err = capsys.readouterr().err
    assert "gpu-agent narrator: error:" in err
    assert not (store / CAT / "story" / f"{DATE}.json").exists()
