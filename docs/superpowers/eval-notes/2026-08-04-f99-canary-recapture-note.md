# F99 canary re-capture — 2026-08-04

**Outcome: CATCH (accept) on the first attempt.** The seeded-regression canary is re-armed.

## What was done

Per the prep package (`.superpowers/handoffs/f99-canary-prep-PACKAGE.md`), under an explicit
interactive user grant given this session (verbatim scope: temporarily damage the extract brain
prompt inside a throwaway git worktree, one live capture, live prompt untouched, no rebaseline,
no commit without user say-so, max two captures):

- Throwaway worktree `.worktrees/f99-canary-capture` off `main` (`35b3e66`); the root checkout's
  `gpu_agent/extraction/prompt.py` was byte-untouched throughout (verified: empty diff after
  cleanup, F6 pin green in root before/after).
- **D1 damage** applied to `_SYSTEM_TEMPLATE` in the worktree only (never committed):
  1. added "Extract ONLY the single most eye-catching claim; ignore the rest of the document.";
  2. deleted the anti-invention rule ("Do not invent numbers … a missing number is honest.");
  3. deleted the "name every genuinely affected category" nudge (kept "mechanism states the
     causal link").
  Sanity check: F6 pin RED in the worktree on `extract` ONLY (judge/thesis/implication hashes
  unchanged) — the damage took and was seam-confined.
- ONE live run (`work/eval-f99-canary/r1`, preserved in the root's gitignored `work/`):
  15 brain cases + 20 graders, each its own tool-less Opus subagent (extract prompts passed
  inline; larger prompts via read-only prompt files, long lines wrapped with an explicit
  `<<WRAP>>` continuation marker so the Read tool could page them). F38 protocol held: 1 brain
  re-dispatch (thesis-2026-07-03-01, two triggers naming no observable) and 8 grader
  re-dispatches (mechanical format violations: `grades` as array instead of object; extra
  `reason` keys) — each re-dispatched singly with the exact violations appended, zero
  hand-edits, zero bypass flags. Total ~44 Opus dispatches.

## Result (verdict.json, pre-committed disposition table row: CATCH)

| condition | required | observed |
|---|---|---|
| damaged extract seam mean X | ≤ 5.533 (hard bar) | **5.375** |
| gate decision | hard-fail | **HARD-FAIL** |
| reasons name extract | yes | "regression on 'extract': 5.375 < bar 6.163" + crater on extract-2026-07-03 |
| all calibration negatives | ≤ 4 | 1 / 1 / 1 / 0 / 2 — all ok |

Informational seams (hash-identical, cannot bind): implication 7.00, judge 7.25, thesis 4.00.

## Disposition executed

- Fixture committed at `fixtures/evals/canary/extract-rules-stripped/report.json` (new folder;
  the old `extract-series-vocab-stripped/` 2026-07-15 capture retained as history).
- `tests/test_evals_canary_f79.py` repointed at the new fixture, the unconditional F99 park
  skip removed, docstring rewritten; test GREEN (suite skip count drops 6 → 5).
- `fixtures/evals/baseline.json` byte-untouched; **no rebaseline was run** (canaries are single
  captured reports, never baselines).
- Raw run data preserved at root `work/eval-f99-canary/` (gitignored; do not delete — the
  2026-07-18/28 raw eval folders were lost once already).

## Margin (why this canary should survive future rebaselines)

Hard bar 5.533 − damaged 5.375 = 0.158 below the HARD bar, and 0.788 below the soft bar —
against the old canary's +0.0875 ABOVE the bar. Because D1 damages the instructions (all 8
extract cases crater on completeness) rather than six vocabulary words (2 of 8 cases), a
future honest widening of the extract noise band has ~0.8 points of headroom before this
canary loses teeth.

## Side observations (recorded, no action taken)

- The thesis informational seam scored 4.00 vs bar 5.50 on an UNCHANGED thesis prompt — a
  LEVEL observation consistent with the F107 closure caveat (grader severity vs bar; latent,
  binds only when the thesis prompt next changes). Informational by design in this run; not a
  gate event.
- Grader format instability (array-vs-object, extra keys) cost 8 mechanical re-dispatches —
  the same class the eval-driver skill predicts; no new F-item minted, consistent with prior
  runs.
