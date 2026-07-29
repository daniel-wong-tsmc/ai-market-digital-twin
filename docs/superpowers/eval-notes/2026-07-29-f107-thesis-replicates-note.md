# F107 thesis-seam replicate note — 3 fresh thesis-only draws, unchanged prompt

**Date:** 2026-07-29
**Item:** F107 (thesis seam replicate instability, opened after the 2026-07-28 F105 run)
**Run dir:** gitignored `work/eval-2026-07-29-f107/` (never `git clean`)
**Full diagnostic package:** `.superpowers/handoffs/f107-thesis-instability-REPORT.md` (analysis +
the 2026-07-29 addendum this note summarises)
**Outcome:** F107 **CLOSED** as a single-run outlier — user decision (a), interactive 2026-07-29.

---

## Why this run happened

On 2026-07-28 the thesis seam scored 5.000 / 7.500 / 5.500 across three replicates on a prompt whose
fingerprint (`4a9d9817951c`) had not moved. That 2.5-point spread tripped the `DISPERSION_LIMIT = 1.0`
guard and blocked F105's rebaseline. The open question was narrow: **is the real single-run wobble the
historical 0.28, or the 1.32 seen on 2026-07-28?** The raw 2026-07-28 answer and grade files were
destroyed by a forced worktree removal, so the only way to answer was fresh draws.

Option B of the decision package was executed: three replicates over the **thesis seam only**, prompt
untouched, ~23 Opus dispatches. The pre-committed disposition was written to
`work/eval-2026-07-29-f107/DISPOSITION.txt` **before** any dispatch:

> if all three fresh thesis draws score `steelman` = 1 and the seam lands in 5.5-6.5, F107 closes as
> "single-run outlier, bar unchanged," with the caveat documented. If `steelman` moves off 1 in any
> draw, F107 escalates to a rubric lane (option D) and the bar stays untouched in the meantime.

## Scores

| replicate | thesis-2026-07-01 | thesis-2026-07-03-01 | seam mean | steelman |
|---|---|---|---|---|
| r1 | 5 (t2/m1/s1/d1) | 6 (t2/m1/s1/d2) | **5.50** | 1, 1 |
| r2 | 5 (t2/m1/s1/d1) | 5 (t2/m1/s1/d1) | **5.00** | 1, 1 |
| r3 | 5 (t2/m1/s1/d1) | 5 (t2/m1/s1/d1) | **5.00** | 1, 1 |

Criteria keys: t = trigger-quality, m = mechanism, s = steelman, d = delta-discipline.
Negative controls scored 0-2 total in every replicate — **calibration held**.

## The reading

- **`steelman` was 1 in all six fresh draws.** The 2026-07-28 swing (a 2 in one run, a 0 in another)
  did not reproduce. **The escalation branch did not fire** — no rubric lane is triggered.
- **Dispersion is small:** range 0.5 across the three replicate means. That supports the historical
  wobble figure of **~0.28**, not the 1.32 scenario. The gate's detection arithmetic stands at the
  current bar: 2026-07-28 reads as a **single-run outlier**.
- Both negative graders behaved. Two re-dispatches were needed for mechanical violations (2x
  truncated JSON, 2x `score_note` extra key), all resolved per F38 by targeted re-dispatch of only
  the violating case. **Zero hand-edits, zero `--force`, zero bypass flags.**

## CAVEAT carried forward (the closure branch did not fire cleanly)

The disposition required the seam to land in **5.5-6.5**. It did not: two of three draws landed at
**5.00**, with r1 exactly on the 5.5 bar. So the **level** sits at or below the bar even though the
**dispersion** question is answered.

Read plainly: **a healthy, unchanged thesis prompt would marginal-fail a real gate today.** That is a
new and narrower question than the one F107 asked — grader severity drift versus a true level shift
(today's graders uniformly gave `mechanism` = 1 with "asserted link" reasoning). It is a LEVEL
question, not the DISPERSION question, and F107 does not cover it.

**Standing disposition on the caveat:** do nothing now. The thesis bar only binds when the thesis
prompt actually changes, and it has not changed in the whole recorded window; recent gates scored
thesis as informational. **Revisit grader-severity-versus-bar ONLY when the thesis prompt next
changes** — that is the moment the exposure goes from latent to live.

## Deviations disclosed

1. **r1 case-01 coordinator transcription slip.** The first gate failure on r1's case-01 was the
   coordinator's error, not the brain's — a judgment was dropped while copying, and a missing closing
   brace was silently added during transcription. Caught, **reverted to byte-verbatim**, re-dispatched.
   The brain's answer was restored, never re-generated.
2. **r2/r3 dispatch wording expanded after r1.** r2 and r3 brain dispatch prompts carried two extra
   guidance sentences (judge every thesis; concrete trigger + citation) that r1's first dispatch
   lacked, added after r1's gate round-trips. Scores were near-identical with and without, so the
   effect is likely immaterial — but the three draws were **not byte-identical dispatch conditions**,
   and that is recorded rather than glossed.

## Standing rule — do NOT rebaseline from this

These are **filtered thesis-only runs**: a deliberately narrowed draw, not a governance artifact.
They **must NEVER be fed to `eval rebaseline`**, with or without `--force`. This was pre-committed
before the run and it stands. The pinned baseline in `fixtures/evals/baseline.json` is unchanged by
this work, and no file under `fixtures/` was touched.

## Side findings recorded (open, not filed as F-items)

Surfaced by the F107 investigation, deliberately **not** minted as new backlog items — named here so
they are not lost:

- **The rubric is not pin-covered.** `tests/test_evals_baseline_pin.py` pins the four brain prompt
  fingerprints and the baseline's internal consistency, but does not hash the rubric text. An edit to
  `steelman`'s wording would change how every future run is graded with no test turning red and no
  fingerprint moving.
- **`append_run_to_history` has no production caller.** The function whose job is to widen epsilon as
  real run-to-run noise accumulates is exercised only by its own tests. In practice epsilon moves only
  during a governance rebaseline.
