# F109 — Coverage gaps recorded durably (design spec)

**Lane:** `f109-coverage-gaps` · worktree `.worktrees/f109-coverage-gaps` · branch `f109-coverage-gaps`
**Date:** 2026-08-04
**Status:** BUILT. The design fork was question-stopped and answered by the user interactively on
2026-08-04 (see §5 — all four answers are user-approved, zero AFK-defaults). Questions as put:
`.superpowers/handoffs/f109-coverage-gaps-QUESTIONS.md`.

---

## 1. The problem, verified against the repo (not restated from the backlog)

F109's claim is that coverage gaps are computed but never recorded durably. Every part of that
checked out in this worktree:

- **No production caller.** `compute_coverage_gaps()` is defined in `gpu_agent/manifest.py:192`.
  A grep across `gpu_agent/` finds **zero** callers. The only invocation anywhere in the shipped
  system is an inline `python -c` snippet pasted inside `.claude/skills/gather-category/SKILL.md`
  (lines 316-330), whose output the coordinator is told to hand-copy into `gather-log.json` under
  a `coverageGaps` key.
- **The destination is gitignored.** `gather-log.json` lives under `work/<cycle>/docs/`. `work/` is
  ignored, and CLAUDE.md's own note ("never `git clean` here — gitignored `work/` holds raw eval
  replicate runs") confirms that tree is scratch, not record.
- **Scorecards carry no coverage field.** `gpu_agent/schema/scorecard.py:51-63` — `Scorecard` has
  `findings`, `dimensionRatings`, `demandSupply`, `narrative`, `confidence`, `sources`,
  `provenance`, `dimensionStatus`, `categoryStatus`, `indices`. Nothing about coverage.
- **The committed cycle log doesn't carry it either, despite the contract saying it should.**
  `docs/.../artifact-landing-map.md:79` documents `gather.coverageGaps` and
  `gather.coverageGapCounts` as fields of each cycle-log entry. The committed
  `store/cycle-log.json` (2026-07-29 run) has **neither key** on its one entry — its `gather` block
  holds 20 other keys and stops there. So the documented durable slot exists on paper and is empty
  in practice.
- **And `cycle-log.json` is single-cycle anyway.** It is a dict for ONE cycle (`asOf`, `mode`,
  `capturedAt`, `scope`, `runDir`, `entries`), overwritten each run. Cycle history survives only in
  git history, not as addressable per-cycle data.

**Root cause (this is the part that shapes the fix).** The failure is not a missing file format.
It is that the only path from `compute_coverage_gaps()` to any record runs through a
**human/agent transcription step** — "print JSON, then append it to a file by hand". That step was
skipped in the v19 (2026-07-27) cycle, which is exactly why the 21 claimed gaps survive only as a
free-text sentence. Any fix that keeps a manual copy step will fail the same way again. The fix has
to make computing and persisting the gaps **one deterministic command**.

## 2. Constraints this lane operates under

- MUST NOT TOUCH: brain prompt bytes (`tests/test_evals_baseline_pin.py` must stay green),
  `fixtures/evals/baseline.json`, `fixtures/narrator`, `registry/indicators.json`,
  `gpu_agent/scoring.py`, `gpu_agent/report.py`, `gpu_agent/narrator/prompt.py`.
- `tests/test_run_cycle_conformance.py:214` asserts the recorded pipeline writes **only** the
  scorecard carve-out under `store/`. Any option that makes `build_scorecard` emit a second store
  file on the recorded path reddens that test. (An option that writes a sidecar from a *separate
  CLI verb* does not touch it.)
- This lane is the only one permitted to re-record the F83 run-cycle conformance pin
  (`EXPECTED_STEPS` in `tests/test_run_cycle_conformance.py:159` + the
  `run-cycle-step-fingerprint` comment at `.claude/skills/run-cycle/SKILL.md:52`), and only if the
  approved design adds a run-cycle step. The fingerprint is regenerated from `EXPECTED_STEPS`,
  never hand-computed.
- Baseline suite: 2147 passed / 5 skipped.

## 3. Options considered

### Option A — tracked store sidecar, written by a new deterministic CLI verb

`store/<categoryId>/coverage-<asOf>.json`, produced by a new verb (working name
`coverage-record`) that loads the manifest, computes gaps through the existing pure function, and
writes the structured list plus counts and the inputs it used.

- Exact precedent already in the repo: `store/<categoryId>/dedup-<asOf>.json`, written by the
  `wiki-dedup` verb, tracked in git, documented in the architecture contract and readable via
  `store_inspect dedup`. Same shape, same keying, same lifecycle.
- Adds one run-cycle step → F83 pin re-record (authorised for this lane).
- Touches nothing near prompts, scoring, or report rendering. Zero pin risk on the brain side.
- Cost: a second file per cycle; a renderer must load it separately from the scorecard.

### Option B — additive-optional `coverage` field on the `Scorecard` model

One artifact; the renderer already loads the scorecard, so nothing new to find.

- Requires threading gather-time data (blob URLs, found indicator ids) all the way to score time
  via a new flag on the score/pipeline verb — coverage provenance ends up inside a scoring
  artifact, which is a category error the repo has otherwise avoided.
- All ~40 historical scorecards would lack the field, so every reader must be `None`-safe anyway —
  which removes most of the "it's already loaded" advantage.
- Higher blast radius: `report.py` (untouchable this lane), `change.py`, `brief.py` all load
  scorecards.

### Option C — hybrid: sidecar is the record, scorecard carries counts + a pointer

Full detail lands in the sidecar; the scorecard gets a small `coverage: {gapCount, requiredGapCount,
ref}` summary so a scorecard-only reader knows coverage data exists and how bad it is.

- Best for downstream rendering (F61's descoped coverage half), at the price of writing two
  artifacts per cycle and one additive-optional schema change.

### Sub-fork — where the verb's inputs come from

- **(i) From the run's `blobs.json` + gated findings (work-dir inputs at cycle end).** Accurate:
  `blob_urls` is genuinely every URL the gather fetched. But it is only computable *during* the
  run — no backfill, and correctness depends on the run passing the right paths.
- **(ii) Derived from the committed scorecard alone.** `Finding` carries `evidence[].url` and
  `indicatorId` (`gpu_agent/schema/finding.py`), so both inputs to `compute_coverage_gaps()` can be
  reconstructed from a committed scorecard — fully reproducible and backfillable forever. But it is
  **semantically different**: a source that was fetched and yielded no gated finding would be
  reported "not covered" when it was in fact covered. That *overstates* gaps.
- **(iii) (i) as the input, with the URL list and manifest ref recorded inside the artifact.**
  Accurate at write time and self-auditing afterwards: a reader can see exactly which URL set the
  verdict was computed over, without needing the gitignored work dir.

## 4. Recommendation (not a decision — awaiting the user)

**Option A with input mode (iii)**, and no backfill of historical cycles.

Rationale, in order of weight:

1. It removes the transcription step, which is the actual root cause. The verb computes and writes
   in one call; there is no intermediate JSON for anyone to forget to paste.
2. It reuses an in-repo precedent verbatim (`dedup-<asOf>.json`), so the store shape, the naming,
   the tracked-in-git status, and the inspect story all already have an answer.
3. It has the smallest blast radius consistent with the constraints: no scorecard schema change, no
   scoring-pipeline threading, no risk to the recorded-pipeline write-discipline test, and nothing
   within reach of the prompt pins.
4. Recording the input URL set inside the artifact makes the gap verdict auditable after the work
   dir is swept — which is the specific durability failure F109 names.

No backfill: the pre-existing cycles' blob URL sets are gone with their work dirs, and the v19
"21 gaps" sentence cannot be honestly reconstructed. Better an empty history that starts telling
the truth at the next cycle than a set of plausible-looking reconstructed artifacts.

## 5. Decision provenance

| Decision | Status |
|---|---|
| Q1 — which durable artifact | **Option A, USER-APPROVED (interactive, 2026-08-04)**: the tracked sidecar `store/<categoryId>/coverage-<asOf>.json`, written by a new deterministic CLI verb, mirroring the dedup-report precedent. |
| Q2 — where the verb's inputs come from | **Option (iii), USER-APPROVED (interactive, 2026-08-04)**: live inputs from the run, with the fetched-URL set and manifest reference written into the artifact so it stays auditable after the work dir is swept. |
| Q3 — backfill past cycles | **No, USER-APPROVED (interactive, 2026-08-04)**: history starts honest at the next cycle; old cycles are not reconstructed. |
| Q4 — the gather skill's inline snippet | **Replaced, USER-APPROVED (interactive, 2026-08-04)**: one code path; the manual transcription step is deleted. |
| Verb name `coverage-record`, artifact name `coverage-<asOf>.json` | Mechanical; follows the `wiki-dedup` / `dedup-<asOf>.json` precedent. |
| Covered indicators read from the **gated findings**, not the fetched URLs | Mechanical: it is `compute_coverage_gaps()`'s own documented semantics ("if the gather fetched the source but the coordinator never produced a finding for this indicator, that is still a gap"). This is also why (d3) sits after write-back rather than at gather time — the findings do not exist earlier. |
| `capturedAt` passed in, not read from the clock | Mechanical: without it, re-running a cycle's coverage check shows up as a spurious diff. |
| Step placed at (d3), after write-back | Follows from the line above; skipped alongside write-back when the scorecard failed. |
| Fingerprint regenerated from `EXPECTED_STEPS`, never hand-computed | Fixed by the lane brief; done via the test module's own `_expected_fingerprint()`. |
| No backfill implies no committed scorecard or store artifact was altered | Follows from Q3. Confirmed: this branch adds no `store/` data. |

## 6. What was built

- `gpu_agent/manifest.py` — `CoverageRecord` model, `build_coverage_record()` (pure, clock-free),
  `_count_gaps()`. `compute_coverage_gaps()` itself is unchanged; F109 was never a maths bug.
- `gpu_agent/cli.py` — the `coverage-record` verb: computes and persists in one call.
- `tests/test_coverage_record.py` — 14 tests, including a guard that fails if the hand-copy snippet
  ever returns to the gather skill.
- `.claude/skills/run-cycle/SKILL.md` — new step (d3); F83 fingerprint re-recorded
  `d7359d33` → `5b25bf8f`, regenerated from `EXPECTED_STEPS`.
- `.claude/skills/gather-category/SKILL.md` — snippet deleted, replaced by a pointer to the verb.
- Store landing map + CLI verb reference document the new artifact; the landing map's stale claim
  that the cycle log carries `coverageGaps` / `coverageGapCounts` is corrected.

Suite: **2160 passed / 6 skipped** (2146 / 6 before this lane's 14 tests). All four pins green.

## 7. What F109 does NOT do (deliberate)

- **No rendering.** Nothing shows coverage to a reader yet. That is F61's descoped coverage half,
  which was blocked on this artifact existing and is now unblocked.
- **No backfill**, per Q3 — `store/` gains no data on this branch. The first real record appears at
  the next live cycle.
- **No scorecard schema change.** If the coverage line later wants to travel with the scorecard,
  Option C in §3 is the upgrade path; the sidecar stays the record either way.
