# F96 content-vintage ids — DONE

## What F96 fixes, in plain words

When the agent re-checks a price page within the same month, it used to build the
same tracking id for that finding no matter what the page's content actually said.
If the price on the page changed since the last check, the new finding collided
with the old id and the update got rejected (rolled back) to protect the store
from corruption. So a same-month price refresh could silently fail to update the
corpus, even though the scorecard for that cycle still published fine.

The fix makes the id depend on the page's web address (URL) plus a short digital
fingerprint (a "digest") of the page's actual content, not just the month. Now,
if the content changes, the id changes with it, so a re-check with different
content is treated as a genuine update instead of a collision. If the content is
identical, the id stays the same too — that's not a bug, that's correct dedup
(you never want the same info stored twice).

The store's built-in tripwire (its safety check that stops writes on unexpected
same-id-different-content collisions) is unchanged and still active — it's there
to catch anything future changes might miss.

## Commits

1. `8dd14a8` — feat: doc ids digest URL + folded content (Task 1: the derivation
   change itself — id now built from `{normalized_url}-{content_digest}-{as_of}`
   instead of URL/date alone).
2. `da472ee` — test: regression - same-month re-fetch updates instead of
   colliding (Task 2: added the regression test, an idempotence test showing
   identical content still dedups, and a tripwire-intact test).
3. This task's close-out commit — `chore(f96): close-out - pins + suite green,
   backlog + sentinel` (Task 3: proof the whole test suite and all four
   guard-rail tests still pass, backlog updated, this sentinel written).

## Task 1's reconciled tests (the "did fixing this break something else" check)

**NONE existed.** There was no pre-existing test in the suite that pinned the old
URL-only digest value, so Task 1's derivation change required zero test
reconciliations — nothing had to be updated to tolerate the new id shape.

## Live criterion (only provable after this merges and a real cycle runs)

The next monthly-grain price re-gather (a normal live cycle that re-checks price
pages within the same month) must log **zero id collisions** — watch the cycle
log's `writeBack` and `wiki-ingest` status fields for that run. This cannot be
forced or faked in this task; it's confirmed the first time it happens for real
after merge.

## Verification done in this close-out task

- Full test suite: **1979 passed, 7 skipped** (green, matches expectation).
- Four pinned guard-rail tests, run individually, all green:
  - `tests/test_evals_baseline_pin.py` (the F6 gate — checks the brain's prompts
    haven't drifted) — PASS
  - `tests/test_scoring_v1_replay_pin.py` (scoring replay pin) — PASS
  - `tests/test_run_cycle_conformance.py` (F83 conformance) — PASS
  - `tests/narrator/test_prompt_pin.py` (narrator prompt pin) — PASS
- Frozen-area check: `git diff --stat fixtures/ registry/ gpu_agent/evals
  gpu_agent/narrator` — **empty** (nothing under those protected folders was
  touched).

## STOP before merge — only the user merges

This sentinel closes out the F96 lane's own work. The orchestrator still runs a
whole-branch review after this. Nobody should merge this branch except the user.
