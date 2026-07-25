"""F96 regression: the v15 RunPod five-sighting failure, re-enacted and closed.

v15 saw RunPod's pricing page re-gathered five times in one month with a
changing price each time. The OLD doc-id derivation hashed the URL alone, so
every re-fetch inside the same vintage month minted the SAME document id.
When the price changed, the extractor's downstream finding id ({docId}-{n})
also stayed the same but the finding CONTENT differed -> FindingStore.append
raised "finding id collision with differing content" and the whole cycle
aborted.

F96 (Task 1) fixed this by folding the document's content into the id
(`_doc_id(normalized_url, as_of, content_digest)`), so a same-month re-fetch
with a genuinely different price mints a new id instead of colliding. This
file proves that end to end, proves the untouched collision path still fires
when it is supposed to (the store tripwire), and proves an unchanged re-fetch
is still a clean no-op.

Fixture pattern lifted from tests/test_dedup_classify.py (_store/_seed/_ev
helpers, classify_findings usage) and tests/test_ingest_ids.py (normalize_documents
+ _doc_id vintage-scoping expectations).
"""
import pytest

from gpu_agent.store import FindingStore
from gpu_agent.wiki.store import WikiStore, PageNotFound
from gpu_agent.gathering.ingest import normalize_documents
from gpu_agent.gathering.dedup import classify_findings, DEFAULT_DEDUP_CONFIG
from gpu_agent.schema.finding import Finding, Kind, Impact, Confidence, Value, Evidence

URL = "https://www.runpod.io/pricing"
AS_OF = "2026-07"


def _blob(content, *, url=URL, date="2026-07-05"):
    return {"source": "RunPod", "url": url, "date": date, "entity": "runpod", "content": content}


def _store(tmp_path):
    return WikiStore(tmp_path / "wiki", FindingStore(tmp_path / "findings"))


def _ev(url=URL, date="2026-07-05"):
    return Evidence(source="RunPod", url=url, date=date, excerpt="H100 SXM pricing", tier="secondary")


def _finding(fid, number, capturedAt, *, url=URL):
    # Mirrors tests/test_dedup_classify.py's price-series fixtures: side="price" so
    # classify_findings keys by (entity, indicatorId, publisher, unit) — publisher is
    # derived from the evidence url, so re-using URL keeps cycle A/B in the same series.
    return Finding(
        id=fid, statement=f"RunPod H100 SXM spot price ${number}/hr", kind=Kind.observed,
        trend="flat", why="w",
        impact=Impact(targets=["chips.merchant-gpu"], direction="negative", mechanism="m"),
        value=Value(number=number, unit="USD_per_gpu_hr"),
        evidence=[_ev(url=url, date=capturedAt)],
        confidence=Confidence(level="medium", basis="b"), asOf=AS_OF,
        indicatorId="D6", side="price", polarityDemand=1, polaritySupply=0,
        magnitude=2, entity="NVDA", observedAt=AS_OF, capturedAt=capturedAt)


def _seed(store, f, as_of):
    pid = f"entity:{f.entity.lower()}"
    try:
        store.get_page(pid)
    except PageNotFound:
        store.create_page(pid, "entity", f.entity, as_of=as_of)
    store.findings.append(f)
    store.append_observation(pid, f.id, as_of=as_of)


def test_same_month_price_refetch_becomes_update_not_collision(tmp_path):
    store = _store(tmp_path)

    # --- cycle A (2026-07): ingest RunPod pricing at $3.29/hr -> finding written ---
    out_a = normalize_documents([_blob("H100 SXM $3.29/hr", date="2026-07-05")],
                                primary_sources=[], as_of=AS_OF)
    assert out_a.dropped == [] and out_a.duplicates == 0   # ingest excluded nothing
    doc_a = out_a.documents[0]
    finding_a = _finding(f"{doc_a.id}-1", 3.29, "2026-07-05")
    _seed(store, finding_a, AS_OF)

    # --- cycle B (same month): SAME url re-gathered, content now $2.99/hr ---
    out_b = normalize_documents([_blob("H100 SXM $2.99/hr", date="2026-07-20")],
                                primary_sources=[], as_of=AS_OF)
    assert out_b.dropped == [] and out_b.duplicates == 0   # ingest excluded nothing
    doc_b = out_b.documents[0]

    # F96: same URL + same vintage month but DIFFERENT folded content -> different doc id.
    # (Pre-Task-1, doc_a.id == doc_b.id here, and the append below would raise
    # "finding id collision with differing content".)
    assert doc_a.id != doc_b.id

    finding_b = _finding(f"{doc_b.id}-1", 2.99, "2026-07-20")
    assert finding_b.id != finding_a.id

    # both findings append cleanly - no ValueError from the store's collision tripwire
    store.findings.append(finding_b)
    assert store.findings.get(finding_a.id).value.number == 3.29
    assert store.findings.get(finding_b.id).value.number == 2.99

    # dedup classifies the second as an UPDATE of the first via entity+indicator (price-series)
    # prior_vintage, NOT via any id comparison
    res = classify_findings([finding_b], store, config=DEFAULT_DEDUP_CONFIG)
    assert [fc.findingId for fc in res.update] == [finding_b.id]
    assert res.update[0].priorFindingId == finding_a.id
    assert res.new == [] and res.duplicate == []


def test_unchanged_refetch_is_still_idempotent(tmp_path):
    store = _store(tmp_path)

    # same month, same content, re-fetched (e.g. a retry) -> same doc id both times
    make_doc = lambda: normalize_documents(
        [_blob("H100 SXM $3.29/hr", date="2026-07-05")],
        primary_sources=[], as_of=AS_OF).documents[0]
    doc_a = make_doc()
    doc_b = make_doc()
    assert doc_a.id == doc_b.id

    finding_a = _finding(f"{doc_a.id}-1", 3.29, "2026-07-05")
    finding_b = _finding(f"{doc_b.id}-1", 3.29, "2026-07-05")
    assert finding_a.id == finding_b.id

    path1 = store.findings.append(finding_a)
    path2 = store.findings.append(finding_b)   # identical id + identical content -> no-op
    assert path1 == path2
    assert store.findings.get(finding_a.id) == finding_a


def test_store_tripwire_still_fires_on_same_id_differing_content(tmp_path):
    # Direct proof the store's collision check (store.py:57, untouched by F96) still
    # works: two findings sharing an id but disagreeing on content must still raise.
    store = FindingStore(tmp_path / "findings")
    f1 = _finding("dup-id", 3.29, "2026-07-05")
    f2 = _finding("dup-id", 2.99, "2026-07-20")
    store.append(f1)
    with pytest.raises(ValueError, match="finding id collision with differing content"):
        store.append(f2)
