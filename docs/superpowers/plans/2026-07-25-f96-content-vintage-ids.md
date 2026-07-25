# F96 — Content-Vintage Document Ids Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A document's id digests URL + folded content, so a same-month re-fetch with changed content mints a new id instead of colliding in the append-only store — ending the five-sighting wiki-ingest abort.

**Architecture:** One derivation change at the single minting seam (`gathering/ingest.py:_doc_id`, sole call site `normalize_documents` @:71 where `blob["content"]` is in scope), reusing `gathering/dedup.py:content_hash` (@:53) as the one fold implementation. Everything else is verification: a headline regression re-enacting the v15 RunPod failure, and pin/suite proofs.

**Tech Stack:** Python 3 (`.venv/Scripts/python`; worktree `../../.venv/Scripts/python`), stdlib hashlib, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-25-f96-content-vintage-ids-design.md`. Frozen core, brains, prompts, `registry/`, `fixtures/evals/`, `fixtures/narrator/`: byte-untouched — `git diff --stat fixtures/ registry/ gpu_agent/evals gpu_agent/narrator` EMPTY at every commit. All four pins (F6, narrator, scoring v1 replay, F83) green at every commit — the replay pin especially: committed findings keep their ids, nothing rewrites them.
- `FindingStore` (`gpu_agent/store.py`) untouched — the collision check stays the backstop tripwire.
- No migration: the new derivation applies to newly ingested docs only; mixed id generations coexist.
- Worktree `.worktrees/f96-content-ids`, branch `f96-content-ids`. Question-stop rule verbatim. Never touch root `store/`; suite green every commit.

**Verified facts (2026-07-25):** `_doc_id(normalized_url, as_of)` @ingest.py:38-43 (`{slug}-{sha256(url)[:8]}-{as_of}`); ONLY call site @:71 inside `normalize_documents(blobs, *, primary_sources, as_of)` where `blob["content"]` is available (REQUIRED fields enforced @:55); `content_hash(content)` @dedup.py:53-56 (`sha256(" ".join(content.split()))`); `FindingStore.append` collision refusal @store.py:57; L2 dedup classifies via `prior_vintage` (entity+indicator) @dedup.py:131; finding ids downstream = `{docId}-{n}` (the F52 comment @ingest.py:43-45).

---

### Task 1: The derivation change (`_doc_id` + `normalize_documents`)

**Files:**
- Modify: `gpu_agent/gathering/ingest.py`
- Test: `tests/gathering/test_ingest_ids.py` (new; match the existing `tests/gathering/` layout — read the directory first; if ingest tests live elsewhere, put the new file beside them and say so in the task report)

**Interfaces:**
- `_doc_id(normalized_url: str, as_of: str, content_digest: str) -> str` — digest becomes `hashlib.sha256(f"{normalized_url}\n{content_digest}".encode("utf-8")).hexdigest()[:8]`; slug and `{slug}-{digest}-{as_of}` shape unchanged. The parameter is REQUIRED (no default) so no caller can silently mint URL-only ids again.
- `normalize_documents` passes `content_hash(blob["content"])` (import `content_hash` from `gpu_agent.gathering.dedup` — **Step 0 verifies import direction**: `grep -n "import" gpu_agent/gathering/dedup.py | grep ingest` must be empty, else a cycle exists → question-stop; if clean, the import is safe).
- Update the F52 comment block (@:43-45) to state the F96 invariant: "same URL + same folded content + same vintage month → same id; changed content → new id (F96)".

- [ ] **Step 0:** verify the import direction (above) and the test directory layout.
- [ ] **Step 1: Write the failing tests**

```python
# tests/gathering/test_ingest_ids.py
import re
from gpu_agent.gathering.ingest import _doc_id, normalize_documents
from gpu_agent.gathering.dedup import content_hash

URL = "https://www.runpod.io/pricing"
AS_OF = "2026-07"


def _blob(content, url=URL):
    return {"source": "RunPod", "url": url, "date": "2026-07-25",
            "entity": "runpod", "content": content}


def test_same_content_same_id():
    a = _doc_id(URL, AS_OF, content_hash("B200 $3.29/hr"))
    b = _doc_id(URL, AS_OF, content_hash("B200  $3.29/hr"))  # whitespace folded
    assert a == b


def test_changed_content_new_id():
    a = _doc_id(URL, AS_OF, content_hash("B200 $3.29/hr"))
    b = _doc_id(URL, AS_OF, content_hash("B200 $2.99/hr"))   # the v15 price move
    assert a != b
    assert a.rsplit("-", 2)[0] == b.rsplit("-", 2)[0]        # same slug
    assert a.endswith(AS_OF) and b.endswith(AS_OF)           # same vintage


def test_distinct_urls_never_merge():
    h = content_hash("identical body")
    assert _doc_id(URL, AS_OF, h) != _doc_id("https://lambda.ai/pricing", AS_OF, h)


def test_id_shape_unchanged():
    got = _doc_id(URL, AS_OF, content_hash("x"))
    assert re.fullmatch(r"www-runpod-io-[0-9a-f]{8}-2026-07", got)


def test_normalize_documents_threads_content(tmp_path):
    out1 = normalize_documents([_blob("B200 $3.29/hr")],
                                primary_sources=[], as_of=AS_OF)
    out2 = normalize_documents([_blob("B200 $2.99/hr")],
                                primary_sources=[], as_of=AS_OF)
    assert out1.documents[0].id != out2.documents[0].id
    out3 = normalize_documents([_blob("B200 $3.29/hr")],
                                primary_sources=[], as_of=AS_OF)
    assert out1.documents[0].id == out3.documents[0].id
```

(Adjust `IngestOutcome` attribute access to the real model — read it in Step 0; if `documents` is named differently, use the real name and note it.)

- [ ] **Step 2:** run `../../.venv/Scripts/python -m pytest tests/gathering/test_ingest_ids.py -v` → FAIL (`_doc_id() takes 2 positional arguments`).
- [ ] **Step 3:** implement per the Interfaces block.
- [ ] **Step 4:** run the new file → 5 PASS. Then the ingest/gathering test subset → reconcile ONLY tests that assert a specific URL-only digest value (enumerate each in the task report with its old/new expectation); any test failing for a semantic reason (dedup counts, dropped docs) = question-stop.
- [ ] **Step 5:** commit `feat(f96): doc ids digest URL + folded content (content-vintage identity)`.

---

### Task 2: The headline regression — the v15 RunPod re-enactment

**Files:**
- Test: `tests/gathering/test_f96_regression.py` (new)

**Interfaces:** consumes only existing public APIs: `normalize_documents`, `FindingStore` (@store.py), `content_hash`, and the wiki-ingest / dedup entry points — **Step 0 reads the existing wiki-ingest and dedup tests** (`grep -rln "wiki-ingest\|wiki_ingest\|prior_vintage" tests/ | head`) and reuses their fixture pattern rather than inventing one. The test must be end-to-end enough that on the OLD derivation it dies with `finding id collision with differing content` and on the new one it completes.

- [ ] **Step 0:** locate the existing dedup + wiki-ingest test fixtures; mirror their setup.
- [ ] **Step 1: Write the regression** (structure fixed; flesh out with the real fixture helpers found in Step 0):

```python
# tests/gathering/test_f96_regression.py — the five-sighting scenario, ended
def test_same_month_price_refetch_becomes_update_not_collision(tmp_path):
    # 1. cycle A (2026-07): ingest RunPod pricing at $3.29 -> finding written to FindingStore
    # 2. cycle B (same month): SAME URL re-gathered, content now $2.99
    # 3. assert: new doc id != old doc id; both findings append cleanly (no ValueError);
    #    dedup classifies the second as an UPDATE of the first (prior_vintage entity+indicator);
    #    the wiki-ingest path over both completes with zero exclusions.
    ...


def test_unchanged_refetch_is_still_idempotent(tmp_path):
    # same month, same content re-fetch -> same id -> FindingStore.append is a no-op
    ...
```

Write full bodies; the first test MUST be demonstrated failing against the pre-Task-1 derivation (Step 2 does this via `git stash`-free means: temporarily assert against a URL-only `_doc_id` reimplemented inline in the test's arrange step is NOT acceptable — instead run the test on the branch BEFORE Task 1's commit is applied? Task 2 runs after Task 1, so demonstrate the collision by constructing two findings with the SAME id and different content directly against `FindingStore.append`, asserting the `ValueError` message — that pins the tripwire still works — then the end-to-end path with the new derivation shows no collision).

- [ ] **Step 2:** run → the collision-tripwire assert passes (store check intact) and the end-to-end passes on the new derivation.
- [ ] **Step 3:** commit `test(f96): regression - same-month price re-fetch updates instead of colliding`.

---

### Task 3: Close-out — pins, suite, backlog, sentinel

- [ ] **Step 1:** full suite `../../.venv/Scripts/python -m pytest -q` → green; forbidden-diff check EMPTY; all four pins green (name each in the report). Explicitly run `tests/test_scoring_v1_replay_pin*.py` and confirm untouched-green.
- [ ] **Step 2:** update `docs/fix-backlog.md` F96 entry: append "FIXED <date> — content-vintage ids (spec/plan refs); store tripwire retained; un-ingested v15/v17 findings accepted as history (spec §3.5). Live criterion: next monthly-grain price re-gather logs zero collisions."
- [ ] **Step 3:** sentinel `.superpowers/handoffs/f96-content-ids-DONE.md` (summary, commits, the enumerated reconciled tests from Task 1, live criterion, "STOP before merge — only the user merges").
- [ ] **Step 4:** final commit, explicit paths.

---

## Self-Review

1. **Spec coverage:** §2 derivation → T1 (required param, fold reuse, comment update); §3.1 no-migration → constraint + no migration task exists (correct); §3.2 seen-docs → untouched by construction (no task edits it; suite guards); §3.3 dedup/update semantics + §3.5 wiki abort → T2 end-to-end; §3.4 F6 → forbidden-diff every commit + T3; §5 tests → T1 units, T2 regression + idempotence + tripwire-intact, T3 pins; §5 live criterion → recorded post-merge in T3's backlog note, not forced.
2. **Placeholders:** T2's test bodies are structured comments with an explicit fill-in instruction bound to fixtures located in its Step 0 — acceptable only because the arrange machinery genuinely depends on existing fixtures the implementer must read; the asserts themselves are enumerated. No other `...`/TBD.
3. **Type consistency:** `_doc_id(normalized_url, as_of, content_digest)` T1 signature used consistently; `content_hash` imported from `gpu_agent.gathering.dedup` in both tasks; sentinel/branch names consistent (`f96-content-ids`).
