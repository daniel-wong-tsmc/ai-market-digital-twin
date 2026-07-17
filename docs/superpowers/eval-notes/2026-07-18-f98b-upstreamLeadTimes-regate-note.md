# F98b eval re-gate notes — `upstreamLeadTimes` (S4) adoption

**Date:** 2026-07-18
**Lane:** `f98b-s4-leadtimes` (worktree). **Change under gate:** one new scoring indicator
`upstreamLeadTimes` in `registry/indicators.json` (commit `5caa82c`). **F6 gate + governance
rebaseline commit:** `4d48a27` (`fixtures/evals/baseline.json`).

## What changed (prompt-diff proof)
Only the **extract** brain-prompt seam changed. Verified two ways:
- F6 pin drift report: `drifted: ['extract']` (judge/thesis/implication hashes unchanged).
- Char-level diff of the emitted extract system prompt (HEAD vs `bd3b7b8`): a single 87-char
  insertion into the registered-indicator enumeration —
  `upstreamLeadTimes — Upstream long-lead component lead times (S4) (supply, unit weeks); ` —
  and nothing else. judge/thesis/implication bundles byte-identical.
So the gate is **seam-scoped to extract** (F65 precedent): extract is `[gated]`; the other three
seams are `[informational (hash-identical)]`.

## Procedure (eval-driver + run-eval, by the book)
Per-run steps 1–6 (`emit-brain` → tool-less Opus brains, byte-verbatim → `record-brain` →
`emit-grade` → tool-less Opus graders → `record-grade --as-of 2026-07-18`). Each brain/grader was a
separate tool-less Opus subagent (Read own prompt file + Write own answer file only — no gathering).
**No `--force`, no hand-edited answers.** F38 violation protocol used (re-dispatch only the violating
case with its violation appended):
- r1 brain: `extract-2026-07-05` (non-ISO observedAt), `implication-2026-07-01` (banned word "leverage").
- r1 grade: `thesis-2026-07-90` (invalid JSON).
- r3 brain: `thesis-2026-07-03-01` — the `export-control-exposure` standing thesis. thesis.py gate
  rule 2 requires EVERY judgment to cite ≥1 real cycle finding (no exception for a no-change verdict);
  resolved with a `reaffirmed` verdict citing 3 real findings.
- r3 grade: `thesis-2026-07-90` (invalid JSON).

## Results
| run | extract | implication | judge | thesis | decision |
|-----|--------:|------------:|------:|-------:|----------|
| r1  | 7.000   | 8.00 | 8.00 | 6.00 | **PASS** (decision run) |
| r2  | 6.375   | 8.00 | 8.00 | 6.00 | marginal-pass (top-up) |
| r3  | 6.125   | 8.00 | 8.00 | 6.00 | marginal-fail (top-up) |

- **Decision:** `eval verdict` accepts 1–2 run dirs. r1 alone = PASS (extract 7.00 vs bar 6.285).
  r1+r2 two-run mean = 6.688 = PASS. Decision is a clean PASS; no decision-replicate was mandated
  (r1 was not marginal).
- **Governance rebaseline:** `eval rebaseline --runs r1 r2 r3 --verdict r1/verdict.json`
  (+ `--human-review`). The 3 extract replicate means (7.00 / 6.375 / 6.125) have range **0.875 <
  DISPERSION_LIMIT 1.0** → noise, not breakage → **no `--force`**. `rebaseline_v2` builds the new
  baseline from the 3 raw replicate means (it does not filter marginal-fail; the non-poisoning
  `append_run_to_history` is the cycle-time path, not rebaseline — run-eval's "keep top-ups regardless
  of score" governs).

## Borderline flag (honest disclosure)
The feature is a **borderline pass**: the 3-run extract mean (6.50) clears the incumbent bar (6.285),
but r3 dipped below it and the r2+r3 pairing (6.25) would have marginal-failed. The clean PASS came
from the r1 decision draw. This is exactly the single-run variance replicates exist to absorb; the new
baseline captures the wider noise honestly. Recorded here and in the DONE sentinel for the user's review.
It is not a blocker: the decision run passed cleanly, dispersion is within limit, and no force was used.

## Post-gate state
F6 pin GREEN (baseline hashes == current bundle), scoring v1 replay pin GREEN throughout, baseline
integrity GREEN. Raw runs live in gitignored `work/eval-2026-07-18/{r1,r2,r3}` (never `git clean`).
