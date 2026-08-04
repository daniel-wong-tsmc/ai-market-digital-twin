"""F109 — coverage gaps recorded durably.

Until F109, `compute_coverage_gaps()` had no production caller: it ran only from a
copy-paste snippet in the gather skill, and its output was hand-appended to a file in
the gitignored `work/` tree. These tests pin the durable path: a `CoverageRecord`
built by a pure function, and a `coverage-record` CLI verb that writes it to the
tracked sidecar `store/<categoryId>/coverage-<asOf>.json` — mirroring the existing
`dedup-<asOf>.json` precedent.

The record is SELF-AUDITING (F109 design answer Q2/(iii)): it carries the fetched-URL
set and the manifest reference the verdict was computed over, so the gap list stays
checkable after the work dir is swept.
"""
import json

import pytest

from gpu_agent.cli import main
from gpu_agent.manifest import (
    CoverageManifest,
    CoverageOverride,
    CoverageRecord,
    build_coverage_record,
    load_manifest,
)


# ── fixtures ─────────────────────────────────────────────────────────────────

MANIFEST = {
    "version": "1.0",
    "categoryId": "chips.merchant-gpu",
    "asOf": "2026-08",
    "expectedIndicators": [
        {"indicatorId": "D2", "dimension": "demand", "priority": "required",
         "sourceIds": ["ir-nvda"]},
        {"indicatorId": "S9", "dimension": "supply", "priority": "preferred",
         "sourceIds": ["ir-amd"]},
    ],
    "expectedSources": [
        {"id": "ir-nvda", "label": "NVIDIA IR", "urlPatterns": ["investor.nvidia.com"],
         "accessMethod": "free-web", "tier": "primary", "refresh": "quarterly"},
        {"id": "ir-amd", "label": "AMD IR", "urlPatterns": ["ir.amd.com"],
         "accessMethod": "free-web", "tier": "primary", "refresh": "quarterly"},
    ],
}


def _write_manifest(tmp_path, payload=None):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(payload or MANIFEST), "utf-8")
    return p


def _finding(fid, indicator_id, urls):
    return {
        "id": fid, "statement": "s", "kind": "observed", "trend": "flat", "why": "w",
        "impact": {"targets": ["x"], "direction": "negative", "mechanism": "m"},
        "evidence": [{"source": "s", "url": u, "date": "2026-08", "excerpt": "e",
                      "tier": "primary"} for u in urls],
        "confidence": {"level": "medium", "basis": "b"},
        "asOf": "2026-08", "indicatorId": indicator_id, "side": "demand",
        "polarityDemand": 1, "polaritySupply": 0, "magnitude": 2, "entity": "nvda",
        "observedAt": "2026-08", "capturedAt": "2026-08-04",
    }


# ── build_coverage_record: the pure builder ──────────────────────────────────

def test_record_carries_the_gaps_the_pure_function_computes(tmp_path):
    manifest = load_manifest(_write_manifest(tmp_path))
    rec = build_coverage_record(
        manifest=manifest,
        category_id="chips.merchant-gpu",
        as_of="2026-08",
        manifest_ref="manifests/chips.merchant-gpu.json",
        fetched_urls=["https://investor.nvidia.com/q2"],
        found_indicator_ids={"D2"},
        captured_at="2026-08-04T00:00:00Z",
    )
    assert isinstance(rec, CoverageRecord)
    # ir-amd not fetched -> source gap; S9 never found -> indicator gap.
    assert {(g.type, g.id) for g in rec.gaps} == {("source", "ir-amd"), ("indicator", "S9")}


def test_record_is_self_auditing_it_carries_its_own_inputs(tmp_path):
    """The F109 durability failure: the URL set lived only in the gitignored work dir,
    so a recorded gap verdict could never be re-checked. The record carries it."""
    manifest = load_manifest(_write_manifest(tmp_path))
    rec = build_coverage_record(
        manifest=manifest, category_id="chips.merchant-gpu", as_of="2026-08",
        manifest_ref="manifests/chips.merchant-gpu.json",
        fetched_urls=["https://b.example/2", "https://a.example/1", "https://b.example/2"],
        found_indicator_ids={"D2", "S9"},
        captured_at="2026-08-04T00:00:00Z",
    )
    # deduped and sorted -> two runs over the same inputs give byte-identical records
    assert rec.judgedUrls == ["https://a.example/1", "https://b.example/2"]
    assert rec.judgedIndicatorIds == ["D2", "S9"]
    assert rec.manifestRef == "manifests/chips.merchant-gpu.json"
    assert rec.categoryId == "chips.merchant-gpu"
    assert rec.asOf == "2026-08"
    assert rec.capturedAt == "2026-08-04T00:00:00Z"


def test_gap_counts_are_precomputed_so_a_reader_need_not_re_derive_them(tmp_path):
    manifest = load_manifest(_write_manifest(tmp_path))
    rec = build_coverage_record(
        manifest=manifest, category_id="chips.merchant-gpu", as_of="2026-08",
        manifest_ref="m.json", fetched_urls=[], found_indicator_ids=set(),
        captured_at="2026-08-04T00:00:00Z",
    )
    # both sources unfetched, both indicators unfound
    assert rec.gapCounts["total"] == 4
    assert rec.gapCounts["source"] == 2
    assert rec.gapCounts["indicator"] == 2
    assert rec.gapCounts["required"] == 3      # 2 sources (always required) + D2
    assert rec.gapCounts["preferred"] == 1     # S9
    assert rec.gapCounts["optional"] == 0
    assert rec.gapCounts["waived"] == 0


def test_full_coverage_records_an_empty_gap_list_not_a_missing_file(tmp_path):
    """An honest zero must be written, not inferred from absence — absence is exactly
    what F109 could not distinguish from 'nobody ran the check'."""
    manifest = load_manifest(_write_manifest(tmp_path))
    rec = build_coverage_record(
        manifest=manifest, category_id="chips.merchant-gpu", as_of="2026-08",
        manifest_ref="m.json",
        fetched_urls=["https://investor.nvidia.com/q2", "https://ir.amd.com/q2"],
        found_indicator_ids={"D2", "S9"}, captured_at="2026-08-04T00:00:00Z",
    )
    assert rec.gaps == []
    assert rec.gapCounts["total"] == 0


def test_waived_gaps_stay_visible_and_are_counted_separately(tmp_path):
    manifest = load_manifest(_write_manifest(tmp_path))
    rec = build_coverage_record(
        manifest=manifest, category_id="chips.merchant-gpu", as_of="2026-08",
        manifest_ref="m.json", fetched_urls=[], found_indicator_ids={"D2", "S9"},
        overrides=[CoverageOverride(type="source", id="ir-amd", reason="paywall lapsed",
                                    waivedBy="operator 2026-08-04")],
        captured_at="2026-08-04T00:00:00Z",
    )
    waived = [g for g in rec.gaps if g.acquisitionStatus == "waived"]
    assert [g.id for g in waived] == ["ir-amd"]
    assert rec.gapCounts["waived"] == 1
    # still counted in total: waiving records a reason, it does not erase the gap
    assert rec.gapCounts["total"] == 2


# ── the CLI verb: the thing that makes it durable ────────────────────────────

def _run_verb(tmp_path, store, extra=None):
    blobs = tmp_path / "blobs.json"
    blobs.write_text(json.dumps({
        "rounds": 1, "skipped": [],
        "blobs": [{"url": "https://investor.nvidia.com/q2", "content": "c"}],
    }), "utf-8")
    findings = tmp_path / "findings.json"
    findings.write_text(json.dumps([
        _finding("f1", "D2", ["https://investor.nvidia.com/q2"]),
    ]), "utf-8")
    argv = ["coverage-record", "--manifest", str(_write_manifest(tmp_path)),
            "--blobs", str(blobs), "--findings", str(findings),
            "--store", str(store), "--category", "chips.merchant-gpu",
            "--as-of", "2026-08"]
    return main(argv + (extra or []))


def test_verb_writes_the_tracked_sidecar_next_to_the_scorecard(tmp_path, capsys):
    store = tmp_path / "store"
    assert _run_verb(tmp_path, store) == 0
    out = store / "chips.merchant-gpu" / "coverage-2026-08.json"
    assert out.exists(), "the whole point of F109: the record lands in tracked store data"
    rec = json.loads(out.read_text("utf-8"))
    assert {(g["type"], g["id"]) for g in rec["gaps"]} == {("source", "ir-amd"),
                                                           ("indicator", "S9")}
    assert rec["judgedUrls"] == ["https://investor.nvidia.com/q2"]
    assert rec["judgedIndicatorIds"] == ["D2"]
    assert "coverage-2026-08.json" in capsys.readouterr().out


def test_verb_takes_covered_indicators_from_the_gated_findings(tmp_path):
    """A source can be fetched and still leave the indicator uncovered — the gap check
    keys on findings actually produced, not on URLs alone (compute_coverage_gaps'
    documented semantics). The verb must honour that."""
    store = tmp_path / "store"
    blobs = tmp_path / "blobs.json"
    blobs.write_text(json.dumps([{"url": "https://ir.amd.com/q2", "content": "c"},
                                 {"url": "https://investor.nvidia.com/q2", "content": "c"}]),
                     "utf-8")
    findings = tmp_path / "findings.json"
    findings.write_text(json.dumps([]), "utf-8")   # fetched everything, extracted nothing
    rc = main(["coverage-record", "--manifest", str(_write_manifest(tmp_path)),
               "--blobs", str(blobs), "--findings", str(findings), "--store", str(store),
               "--category", "chips.merchant-gpu", "--as-of", "2026-08"])
    assert rc == 0
    rec = json.loads((store / "chips.merchant-gpu" / "coverage-2026-08.json").read_text("utf-8"))
    # no source gaps (both fetched), but both indicators are gaps
    assert {(g["type"], g["id"]) for g in rec["gaps"]} == {("indicator", "D2"),
                                                           ("indicator", "S9")}


def test_verb_accepts_a_bare_blob_array_as_well_as_the_envelope(tmp_path):
    store = tmp_path / "store"
    blobs = tmp_path / "blobs.json"
    blobs.write_text(json.dumps([{"url": "https://investor.nvidia.com/q2"}]), "utf-8")
    findings = tmp_path / "findings.json"
    findings.write_text(json.dumps([_finding("f1", "D2", [])]), "utf-8")
    rc = main(["coverage-record", "--manifest", str(_write_manifest(tmp_path)),
               "--blobs", str(blobs), "--findings", str(findings), "--store", str(store),
               "--category", "chips.merchant-gpu", "--as-of", "2026-08"])
    assert rc == 0
    rec = json.loads((store / "chips.merchant-gpu" / "coverage-2026-08.json").read_text("utf-8"))
    assert rec["judgedUrls"] == ["https://investor.nvidia.com/q2"]


def test_verb_is_deterministic_rerunning_rewrites_identical_bytes(tmp_path):
    store = tmp_path / "store"
    out = store / "chips.merchant-gpu" / "coverage-2026-08.json"
    _run_verb(tmp_path, store, ["--captured-at", "2026-08-04T00:00:00Z"])
    first = out.read_text("utf-8")
    _run_verb(tmp_path, store, ["--captured-at", "2026-08-04T00:00:00Z"])
    assert out.read_text("utf-8") == first


def test_verb_writes_nothing_and_explains_itself_on_a_bad_manifest(tmp_path, capsys):
    store = tmp_path / "store"
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", "utf-8")
    findings = tmp_path / "findings.json"
    findings.write_text("[]", "utf-8")
    blobs = tmp_path / "blobs.json"
    blobs.write_text("[]", "utf-8")
    rc = main(["coverage-record", "--manifest", str(bad), "--blobs", str(blobs),
               "--findings", str(findings), "--store", str(store),
               "--category", "chips.merchant-gpu", "--as-of", "2026-08"])
    assert rc == 1
    assert not (store / "chips.merchant-gpu").exists(), "never half-write on a failure"
    assert "invalid JSON" in capsys.readouterr().err


def test_verb_honours_an_overrides_file(tmp_path):
    store = tmp_path / "store"
    ov = tmp_path / "overrides.json"
    ov.write_text(json.dumps([{"type": "source", "id": "ir-amd",
                               "reason": "licence lapsed", "waivedBy": "operator"}]), "utf-8")
    assert _run_verb(tmp_path, store, ["--overrides", str(ov)]) == 0
    rec = json.loads((store / "chips.merchant-gpu" / "coverage-2026-08.json").read_text("utf-8"))
    statuses = {g["id"]: g["acquisitionStatus"] for g in rec["gaps"]}
    assert statuses["ir-amd"] == "waived"
    assert rec["gapCounts"]["waived"] == 1


def test_verb_out_overrides_the_store_path(tmp_path):
    store = tmp_path / "store"
    out = tmp_path / "elsewhere.json"
    assert _run_verb(tmp_path, store, ["--out", str(out)]) == 0
    assert out.exists()


# ── the guard that keeps F109 from recurring ─────────────────────────────────

def test_gather_skill_no_longer_asks_anyone_to_hand_copy_the_gap_list():
    """F109's root cause was a manual transcription step: 'print the JSON, then append
    it to gather-log.json by hand'. It was skipped in the v19 cycle and the gaps were
    lost. The snippet must stay gone."""
    from pathlib import Path
    skill = Path(__file__).resolve().parents[1] / ".claude/skills/gather-category/SKILL.md"
    text = skill.read_text("utf-8")
    assert "compute_coverage_gaps" not in text, (
        "the inline compute_coverage_gaps snippet is back — F109 replaced it with the "
        "coverage-record verb precisely because the hand-copy step got skipped")
    assert "coverage-record" in text, "the skill must point at the verb that replaced it"


def test_the_record_model_round_trips_through_json(tmp_path):
    manifest = load_manifest(_write_manifest(tmp_path))
    rec = build_coverage_record(
        manifest=manifest, category_id="chips.merchant-gpu", as_of="2026-08",
        manifest_ref="m.json", fetched_urls=[], found_indicator_ids=set(),
        captured_at="2026-08-04T00:00:00Z")
    assert CoverageRecord.model_validate_json(rec.model_dump_json()) == rec
