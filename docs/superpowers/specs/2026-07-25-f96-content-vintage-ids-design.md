# F96 — Content-Vintage Document Ids (ending the same-month re-fetch collision)

**Date:** 2026-07-25
**Status:** Spec (brainstormed interactively; the identity decision is the user's pick — zero AFK)
**History:** five sightings (v8, v14, v15, v16-adjacent, v17). Latest damage: v15 aborted
`wiki-ingest` partway (12/17 written, 5 findings never ingested); every monthly cycle risks
silently losing same-month price refreshes.

## 1. Root cause (verified 2026-07-25)

`gpu_agent/gathering/ingest.py:39` `_doc_id(normalized_url, as_of)` digests the **URL only**:
`{slug}-{sha256(url)[:8]}-{as_of}`. Finding ids inherit the doc id (+ index suffix). A monthly
cycle's `as_of` is `2026-07`, so re-fetching the same pricing URL within the month after its
content changed yields the SAME id with DIFFERENT content — and the append-only
`FindingStore.append` (`gpu_agent/store.py:57`) correctly refuses. The store is right; the id
is wrong.

## 2. The fix (user decision: "URL + content vintage")

**A document's identity = its URL + its content, within its vintage month.**

- `_doc_id(normalized_url, as_of, content_digest: str)` →
  `{slug}-{sha256(normalized_url + "\n" + content_digest)[:8]}-{as_of}` — same 3-part shape,
  same charset (`_SAFE_ID` untouched), same length.
- `content_digest` = the folded-content SHA-256 the dedup layer already computes
  (`gpu_agent/gathering/dedup.py:56`) — ONE fold implementation, reused, never re-implemented.
- Unchanged re-fetch → identical fold → identical id → `FindingStore.append` idempotent no-op
  (exactly today's behavior).
- Changed content → new digest → NEW doc id → new finding ids. The L2 dedup layer receives
  them as candidate findings and classifies new/update/duplicate through its existing
  entity+indicator matching (`dedup.py:131 prior_vintage`) — a changed price reading lands as
  an UPDATE of the prior finding, which is precisely the intended semantics.
- The store collision check is UNTOUCHED — it remains the backstop tripwire; after this fix,
  tripping it again means a genuine new bug, not weather.

## 3. Blast radius (each verified in-plan, not assumed)

1. **No migration.** Committed findings/doc ids keep their names forever (append-only store);
   the new derivation applies to newly ingested docs only. Mixed id generations coexist —
   nothing parses the digest half of an id.
2. **`seen_docs.jsonl`** already keys on `{url, hash, asOf}` — unchanged.
3. **Dedup/corpus**: `prior_vintage` matches by entity+indicator, not by id — verified in-plan
   with a regression test reproducing the v15 RunPod scenario end-to-end (same month, changed
   price → update classified, wiki-ingest completes).
4. **F6 pin**: the pin hashes emissions from FROZEN fixture inputs; live id derivation is not
   part of any prompt template. The lane proves `fixtures/evals` + emitted-prompt hashes are
   byte-identical at every commit. Ingest is not a gated seam (registry/prompt/eval all
   untouched).
5. **Wiki ingest**: the aborted-partway failure mode disappears at the source; the un-ingested
   v15/v17 findings are NOT retro-repaired by this lane (the store is append-only; those
   specific readings are superseded by later cycles anyway — noted as accepted history).

## 4. Constraints

- Frozen core, brains, prompts, `registry/`, eval + narrator fixtures: byte-untouched. All
  four pins green at every commit.
- The scoring v1 replay pin must stay green — replays read committed findings by their
  existing ids; nothing rewrites them.
- Deterministic: same URL + same folded content + same month → the same id on every machine.

## 5. Testing

- Unit: derivation (unchanged content → stable id; one-char content change → new id; distinct
  URLs never merge; shape/charset unchanged).
- Regression (the headline test): simulated same-month re-fetch of a price URL with a changed
  value → ingest + dedup + wiki-ingest complete with an `update`, zero collisions, store
  consistent.
- Idempotence: identical re-append is still a no-op.
- Pins: full suite + all four pins green; `git diff --stat fixtures/ registry/ gpu_agent/evals`
  empty.
- Live criterion (post-merge, not forced): the next monthly-grain cycle that re-gathers a
  price URL logs zero id collisions (watch the cycle log's writeBack/wiki-ingest status).

## 6. Out of scope

F102 (price-sync date parse — separate small lane, next); retro-repair of previously
un-ingested findings; any change to `FindingStore` semantics.
