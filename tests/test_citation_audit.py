"""F66 Task 2: the deterministic citation audit over story scenes + implication lines.

Every fixture here is built in tmp_path -- the suite must never depend on mutable
live `store/` state. (The frozen live-artifact replay lives in
tests/test_f66_live_replay.py and uses committed copies under tests/fixtures/f66/.)
"""
import json

import pytest

from gpu_agent.citation_audit import (AuditArtifact, AuditStore, Claim,
                                      FindingsReader, audit_claim,
                                      claims_from_implication,
                                      claims_from_story, run_audit)
from gpu_agent.implication import ImplicationArtifact, ImplicationLine, ImplicationStore
from gpu_agent.narrator.schema import (NarratorMeta, StoryArtifact, StoryScene)
from gpu_agent.narrator.store import StoryStore

CAT = "chips.merchant-gpu"
DATE = "2026-07-27"


# --- fixture builders ---------------------------------------------------------

def _finding(fid, statement="a thing happened", why="because", number=None,
             unit="USD_B", evidence=()):
    d = {
        "id": fid,
        "statement": statement,
        "kind": "observed",
        "trend": "flat",
        "why": why,
        "impact": {"targets": ["tsmc"], "direction": "mixed", "mechanism": "m"},
        "evidence": [{"source": "src", "url": "https://example.com/a", "date": dt,
                      "excerpt": ex, "tier": "secondary"} for dt, ex in evidence],
        "confidence": {"level": "medium", "basis": "b"},
        "asOf": "2026-07",
        "indicatorId": "gpuSpotPrice",
        "side": "price",
        "polarityDemand": 0,
        "polaritySupply": 0,
        "magnitude": 2,
        "entity": "nvidia",
        "observedAt": "2026-07-23",
        "capturedAt": "2026-07-23T00:00:00Z",
    }
    if number is not None:
        d["value"] = {"number": number, "unit": unit}
    return d


def _write_findings(root, *findings):
    d = root / "findings"
    d.mkdir(parents=True, exist_ok=True)
    for f in findings:
        (d / f"{f['id']}.json").write_text(json.dumps(f, indent=2), encoding="utf-8")
    return FindingsReader(d)


def _scene(n, paragraphs, finding_ids, title="A scene"):
    return StoryScene(n=n, title=title, paragraphs=paragraphs, visual=None,
                      claimFindingIds=list(finding_ids),
                      sourceLine="Sources: example.com", relatedDocs=[])


def _story(scenes, category_id=CAT, story_date=DATE):
    return StoryArtifact(
        schemaVersion=1, categoryId=category_id, storyDate=story_date,
        headline="A headline", deck="A deck", scenes=scenes, kpiPicks=[],
        calloutMonths=[],
        narratorMeta=NarratorMeta(model="m", promptHash="h", retries=0,
                                  fellBack=False, wroteAt="2026-07-27T00:00:00Z"))


# --- claim builders -----------------------------------------------------------

def test_claims_from_story_keys_and_text():
    art = _story([_scene(1, ["one", "two"], ["f-a"]), _scene(2, ["three"], [])])
    claims = claims_from_story(art)
    assert [c.claimKey for c in claims] == ["scene:1", "scene:2"]
    assert claims[0].text == "one two"
    assert claims[0].findingIds == ("f-a",)
    assert claims[1].findingIds == ()


def test_claims_from_implication_keys_are_dispatch_order():
    art = ImplicationArtifact(categoryId=CAT, asOf="2026-07", lines=[
        ImplicationLine(watchItem="watch A", findingIds=["f-a"]),
        ImplicationLine(watchItem="watch B", findingIds=[]),
    ])
    claims = claims_from_implication(art)
    assert [c.claimKey for c in claims] == ["impl:0", "impl:1"]
    assert claims[0].text == "watch A"


# --- the verdict rules --------------------------------------------------------

def test_clean_claim_passes(tmp_path):
    reader = _write_findings(tmp_path, _finding(
        "f-a", statement="the deal closed", number=4.83,
        evidence=[("2026-07-23", "worth $4.83 billion")]))
    claim = Claim("scene:1", "The deal was $4.83 billion in 2026.", ("f-a",))
    r = audit_claim(claim, reader)
    assert r.verdict == "clean"
    assert r.flaggedTokens == []
    assert r.citedFindingIds == ["f-a"]


def test_rounded_number_passes(tmp_path):
    reader = _write_findings(tmp_path, _finding(
        "f-a", statement="SK Hynix's board approved 7.0931 trillion won"))
    claim = Claim("scene:2", "The board approved 7.09 trillion won.", ("f-a",))
    r = audit_claim(claim, reader)
    assert r.verdict == "clean"
    assert r.flaggedTokens == []


def test_fabricated_number_is_flagged(tmp_path):
    reader = _write_findings(tmp_path, _finding("f-a", statement="rates held flat"))
    claim = Claim("scene:1", "Rates ran to $9.99 an hour.", ("f-a",))
    r = audit_claim(claim, reader)
    assert r.verdict == "flagged"
    assert r.flaggedTokens == ["9.99"]
    assert r.unresolvedIds == []


def test_number_from_an_uncited_finding_is_flagged(tmp_path):
    # The number is real and IS in the store -- but in a finding this claim does not
    # cite. This is the mis-attribution case, and the reason the pool is per-claim.
    reader = _write_findings(
        tmp_path,
        _finding("f-cited", statement="rates held flat"),
        _finding("f-uncited", statement="the price reached 68.80 an hour"))
    claim = Claim("scene:1", "The price reached $68.80 an hour.", ("f-cited",))
    r = audit_claim(claim, reader)
    assert r.verdict == "flagged"
    assert r.flaggedTokens == ["68.80"]


def test_unresolved_finding_id_is_flagged(tmp_path):
    reader = _write_findings(tmp_path, _finding("f-a", statement="rates held flat"))
    claim = Claim("scene:1", "Nothing numeric here.", ("f-a", "f-missing"))
    r = audit_claim(claim, reader)
    assert r.verdict == "flagged"
    assert r.unresolvedIds == ["f-missing"]
    assert r.flaggedTokens == []


def test_zero_citation_scene_is_skipped_not_flagged(tmp_path):
    reader = _write_findings(tmp_path, _finding("f-a"))
    claim = Claim("scene:3", "We saw 42 percent and $18.77 today.", ())
    r = audit_claim(claim, reader)
    assert r.verdict == "skipped"
    assert r.flaggedTokens == []
    assert r.unresolvedIds == []


def test_evidence_date_tokens_are_allowed(tmp_path):
    # A statement-only pool would flag "23"; the wide pool reads evidence dates.
    reader = _write_findings(tmp_path, _finding(
        "f-a", statement="the supplier spoke", why="context",
        evidence=[("2026-07-23", "an excerpt with no digits")]))
    claim = Claim("scene:2", "The head of the supplier said on 23 July.", ("f-a",))
    r = audit_claim(claim, reader)
    assert r.verdict == "clean"


def test_extra_texts_supply_self_computed_values(tmp_path):
    # D5b, sourcing option (a): the CLI hands the series values in. Without them
    # the page is flagged for quoting arithmetic we computed ourselves.
    reader = _write_findings(tmp_path, _finding("f-a", statement="rates held flat"))
    claim = Claim("scene:1", "A median of $18.77 per chip-hour.", ("f-a",))
    assert audit_claim(claim, reader).verdict == "flagged"
    assert audit_claim(claim, reader, extra_texts=["18.77"]).verdict == "clean"


# --- run_audit + artifact -----------------------------------------------------

def test_implication_lines_are_audited(tmp_path):
    _write_findings(tmp_path, _finding("f-a", statement="memory rose 25 percent"))
    StoryStore(tmp_path).write(_story([_scene(1, ["Nothing numeric."], ["f-a"])]))
    ImplicationStore(tmp_path / "implications" / CAT).write(ImplicationArtifact(
        categoryId=CAT, asOf="2026-07", lines=[
            ImplicationLine(watchItem="Memory up 25 percent.", findingIds=["f-a"]),
            ImplicationLine(watchItem="Packaging up 99 percent.", findingIds=["f-a"]),
        ]))
    art = run_audit(tmp_path, CAT, DATE)
    keys = [c.claimKey for c in art.claims]
    assert keys == ["scene:1", "impl:0", "impl:1"]
    by = {c.claimKey: c for c in art.claims}
    assert by["impl:0"].verdict == "clean"
    assert by["impl:1"].verdict == "flagged"
    assert by["impl:1"].flaggedTokens == ["99"]


def test_missing_implication_artifact_is_not_an_error(tmp_path):
    _write_findings(tmp_path, _finding("f-a", statement="rates held flat"))
    StoryStore(tmp_path).write(_story([_scene(1, ["Nothing numeric."], ["f-a"])]))
    art = run_audit(tmp_path, CAT, DATE)
    assert [c.claimKey for c in art.claims] == ["scene:1"]
    assert art.summary["flagged"] == 0


def test_missing_story_artifact_is_an_empty_clean_audit(tmp_path):
    _write_findings(tmp_path, _finding("f-a"))
    art = run_audit(tmp_path, CAT, DATE)
    assert art.claims == []
    assert art.summary == {"claimsAudited": 0, "flagged": 0, "skipped": 0}


def test_artifact_roundtrips_and_summary_counts(tmp_path):
    _write_findings(tmp_path, _finding("f-a", statement="rates held flat"))
    StoryStore(tmp_path).write(_story([
        _scene(1, ["Rates ran to $9.99 an hour."], ["f-a"]),   # flagged
        _scene(2, ["Nothing numeric."], ["f-a"]),              # clean
        _scene(3, ["We saw 42 percent."], []),                 # skipped
    ]))
    art = run_audit(tmp_path, CAT, DATE)
    assert art.summary == {"claimsAudited": 3, "flagged": 1, "skipped": 1}

    store = AuditStore(tmp_path)
    p = store.write(art)
    assert p == tmp_path / CAT / "audit" / f"{DATE}.json"
    back = store.read(CAT, DATE)
    assert isinstance(back, AuditArtifact)
    assert back.model_dump() == art.model_dump()
    assert back.schemaVersion == 1
    assert not list((tmp_path / CAT / "audit").glob("*.tmp"))   # atomic write left no litter


def test_audit_store_read_missing_returns_none(tmp_path):
    assert AuditStore(tmp_path).read(CAT, DATE) is None
