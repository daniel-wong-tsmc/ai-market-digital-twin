# F108 — seam-scoped rebaseline implementation plan

**Spec:** `docs/superpowers/specs/2026-07-28-f108-seam-scoped-rebaseline-design.md`
**Lane:** `f108-seam-rebaseline`. Python: `../../.venv/Scripts/python`. TDD throughout — test first,
watch it fail for the right reason, then implement.

## Task 1 — shared case-to-seam matching

Lift the prefix match out of `evaluate_v2` into a module-level `case_seam(cid, seams)` in
`gpu_agent/evals/harness.py`; have `evaluate_v2` call it. Pure refactor — no behaviour change.

Tests (`tests/test_evals_v2.py`): longest-prefix wins when one seam name prefixes another; exact-id
match; unmappable id returns `None`. Existing `evaluate_v2` tests must pass untouched.

## Task 2 — the merge

`merge_baseline_seam_scoped(existing, fresh, seams, run_dirs, force_reason, human_review)` in
`harness.py`, returning a new dict, mutating nothing.

Per the spec table: `promptHashes` / `seamMeans` / `epsilon` / `quanta` / `seamHistory` per-seam;
`caseMedians` per case by seam; `replicates` spliced entry-by-entry with `seamRunDirs` added and
`asOf` / `runDir` kept from the incumbent; `provenance` carried through with `seamRebaselines` merged in.

Tests:
- carried seams' mean, epsilon, quantum and history are identical objects' values to the incumbent's
- named seam's four values come from `fresh`
- case medians split correctly by seam, including a negative-case id
- each replicate entry keeps 3 entries, all four seams in `seamMeans`, `asOf`/`runDir` from incumbent,
  `seamRunDirs` naming the new dir for the named seam and the incumbent dir for the others
- carried seams' per-entry case grades byte-identical to the incumbent's
- top-level `provenance` fields untouched; `seamRebaselines` gains only the named seam; a second
  scoped rebaseline of a different seam keeps the first seam's entry
- serialising the merged baseline and re-reading it round-trips

## Task 3 — guards and wiring in `rebaseline_v2`

Add `seams: list[str] | None = None`. When `None`, the existing path runs unchanged. When given, apply
guards 1–7 from the spec, build `fresh`, merge, write.

Tests: one per guard (no incumbent; incumbent without 3 replicates; unknown seam name; un-named seam
drifted; dispersion over a named seam refuses while the same dispersion on an un-named seam does not;
naming an unchanged seam without force refuses and with force succeeds; verdict missing / not PASS /
seam informational / seam not `ok` each refuse; unmappable case id refuses). Plus the happy path: a
scoped rebaseline over an incumbent writes a file whose un-named seams are byte-identical.

**Regression guard:** a test asserting the no-`--seams` path is byte-identical to today's output —
build a baseline through `rebaseline_v2` with no seams and compare against `build_baseline_v2` directly.

## Task 4 — CLI

`--seams` (`nargs="+"`, default `None`) on the `eval` parser; pass through in `_eval`. On the scoped
path print rebuilt vs carried seams. Tests in `tests/test_cli_eval.py`: flag reaches the harness;
scoped run writes the expected file; a guard refusal exits 1 with the message on stderr; existing
whole-baseline CLI tests unchanged.

## Task 5 — docs and close-out

Document `--seams` in the in-repo `run-eval` skill (and note the machine-local `eval-driver` skill as a
follow-up). Tick F108 in `docs/fix-backlog.md`. Full suite (`python -m pytest`) green, ~7 skips in a
worktree. Verify all four pins green by name. DONE sentinel to root
`.superpowers/handoffs/f108-seam-rebaseline-DONE.md`. **STOP — no merge.**

## Invariants for every task

- No prompt text, no `fixtures/evals/baseline.json` content change, no fixture hand-edits.
- No test hard-codes an expected extract bar (F105-lane standing instruction).
- Any new design fork → question-stop, do not pick.
