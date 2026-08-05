import json
from pathlib import Path
from gpu_agent.dashboard.source_refs import refs_for_finding_ids, findings_index, assessment_ref

SC = json.loads(Path("fixtures/dashboard/scorecard-trimmed.json").read_text(encoding="utf-8"))

def test_resolves_url_and_tier():
    idx = findings_index(SC)
    fid = next(iter(idx))
    refs = refs_for_finding_ids([fid], idx)
    assert refs and refs[0]["url"].startswith("http")
    assert refs[0]["tier"] in ("primary", "secondary", None)

def test_unknown_id_skipped_not_raised():
    assert refs_for_finding_ids(["nope-1"], findings_index(SC)) == []

def test_dedupes_by_url_and_caps():
    idx = findings_index(SC)
    all_ids = list(idx) * 2
    refs = refs_for_finding_ids(all_ids, idx, max_refs=3)
    assert len(refs) <= 3
    assert len({r["url"] for r in refs}) == len(refs)

def test_assessment_ref_shape():
    r = assessment_ref([{"title": "t", "outlet": "o", "url": "u", "date": None, "tier": None}])
    assert r["assessment"] is True and len(r["basedOn"]) == 1
