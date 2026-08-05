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

def test_cap_actually_truncates():
    # The trimmed fixture's findings resolve to more distinct URLs than
    # max_refs, so the cap must discard some of them. If refs[:max_refs]
    # were removed, this test would fail (len(refs) would exceed 3 and
    # some available URL would be missing from a truncated-only check).
    idx = findings_index(SC)
    all_ids = list(idx)
    uncapped = refs_for_finding_ids(all_ids, idx, max_refs=1000)
    assert len(uncapped) > 3, "fixture must contain more than max_refs distinct URLs for this test to be meaningful"
    capped = refs_for_finding_ids(all_ids, idx, max_refs=3)
    assert len(capped) == 3
    assert len(capped) < len(uncapped)

def test_primary_tier_sorts_before_secondary():
    idx = findings_index(SC)
    all_ids = list(idx)
    refs = refs_for_finding_ids(all_ids, idx, max_refs=1000)
    tiers_present = {r["tier"] for r in refs}
    assert {"primary", "secondary"} <= tiers_present, "fixture must contain both tiers for this test to be meaningful"
    tier_sequence = [r["tier"] for r in refs]
    first_secondary = tier_sequence.index("secondary")
    assert "primary" not in tier_sequence[first_secondary:], (
        "a primary-tier ref appeared after the first secondary-tier ref: ordering is broken"
    )

def test_missing_url_refs_not_collapsed():
    # Two distinct sources that both lack a url must not dedupe against
    # each other via a shared "url is None" key.
    findings_by_id = {
        "f1": {"id": "f1", "evidence": [
            {"source": "Outlet One", "url": None, "date": None, "tier": None},
        ]},
        "f2": {"id": "f2", "evidence": [
            {"source": "Outlet Two", "url": None, "date": None, "tier": None},
        ]},
    }
    refs = refs_for_finding_ids(["f1", "f2"], findings_by_id, max_refs=10)
    assert len(refs) == 2
    assert {r["title"] for r in refs} == {"Outlet One", "Outlet Two"}

def test_assessment_ref_shape():
    r = assessment_ref([{"title": "t", "outlet": "o", "url": "u", "date": None, "tier": None}])
    assert r["assessment"] is True and len(r["basedOn"]) == 1
