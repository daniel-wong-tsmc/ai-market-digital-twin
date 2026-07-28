# F108 — seam-scoped rebaseline design

**Date:** 2026-07-28
**Lane:** `f108-seam-rebaseline` (worktree `.worktrees/f108-seam-rebaseline`, branch off main `3e45625`)
**Backlog:** F108 (this item), F107 (the thesis-noise item this unblocks work around) — commit `d101c4a`
**Scope:** harness code + CLI + tests only. No prompt text, no `fixtures/evals/baseline.json` content
change, no fixture hand-edits. All four pins (F6 baseline pin, scoring-v1 replay, F83 conformance,
narrator pin) stay green.

## Problem

`rebaseline_v2` rebuilds the whole baseline from all four seams at once. Every seam's mean, epsilon,
quantum, history and case medians are recomputed together, and the dispersion guard
(`DISPERSION_LIMIT = 1.0` on a seam's replicate range) is applied to every seam.

That makes a clean single-seam change hostage to unrelated noise. The F105 run is the live case:
extract — the only seam whose prompt moved — scored 6.500 / 6.750 / 7.125 (range 0.625) and cleared
its bar of 5.599 in a PASS verdict, but thesis, whose prompt is byte-identical to the baseline's,
swung 5.000 / 7.500 / 5.500 (range 2.500) and the guard refused the whole rebaseline. The only escapes
today are a whole-baseline `--force` (which would have dropped the thesis bar from 5.50 to 3.35 and
loosened judge and implication as well) or parking the fix.

## Solution

`eval rebaseline --seams <seam> [<seam> …]` rebuilds only the named seams. Named seams get new mean,
epsilon, quantum, history and case medians from the replicate reports. Every other seam's baseline
entry carries forward unchanged from the incumbent. The dispersion guard applies only to the named
seams. The baseline records which seams were rebuilt, when, and from which runs.

With no `--seams`, behaviour is exactly today's, byte-identical on the default path.

## The merge, field by field

Let `existing` be the incumbent baseline and `fresh` be `build_baseline_v2(...)` over the three new
reports. `named` is the set of seams given on the command line.

| field | rule |
|---|---|
| `schemaVersion` | unchanged (2) — additive change only, no bump |
| `promptHashes` | per seam: named → `fresh`, otherwise → `existing` |
| `seamMeans`, `epsilon`, `quanta`, `seamHistory` | per seam: named → `fresh`, otherwise → `existing` |
| `caseMedians` | per case, by seam of the case id: named seam → `fresh`, otherwise → `existing` |
| `replicates` | spliced, see below |
| `provenance` | `existing` carried through untouched, plus a `seamRebaselines` entry per named seam |

A named seam's `caseMedians` come wholly from `fresh` — cases the incumbent had for that seam and the
new runs do not are dropped, and vice versa. Carried seams' case medians are untouched.

`seamHistory` for a named seam is REPLACED by the three new replicate means, not appended to. That
matches what a whole rebaseline does, and epsilon is derived from history, so appending would mix two
prompt generations' noise into one band.

### The `replicates` splice (Q1, user pick: option B)

The block keeps its three-entry shape. Entry `i` of the new baseline pairs `existing["replicates"][i]`
with `fresh["replicates"][i]`:

- `seamMeans`: per seam, named → fresh entry's value, otherwise → existing entry's value.
- `cases`: per case, by seam of the case id — named seam → fresh entry's grades, otherwise existing's.
  Grader-calibration negatives (`extract-2026-07-90` etc.) map to their seam by prefix like any other
  case, so they travel with their seam.
- `asOf` and `runDir`: kept from the existing entry — they are the entry's original identity.
- `seamRunDirs` (**new**): every seam mapped to the run dir its numbers actually came from — the new
  run dir for named seams, the existing entry's `runDir` for carried ones. This is the visible note
  the user asked for; it is what makes the stitching legible rather than hidden.

Accepted consequence, stated plainly: after a seam-scoped rebaseline the `replicates` block is no
longer a record of three literal runs. It is a record of where each seam's numbers came from. The
alternative — leaving it literal — makes the stored numbers contradict the bars built from them, which
is the worse failure for a file whose whole job is to be auditable.

Pairing entry `i` with entry `i` is arbitrary but harmless: nothing reads across entries except
per-seam aggregates, and those are per-seam consistent by construction.

### Provenance (Q2)

Added under the existing `provenance` object, additive:

```
"provenance": {
  "asOf": "2026-07-18", "graderModel": "opus", "forceReason": null, "humanReview": "…",
  "seamRebaselines": {
    "extract": {"asOf": "2026-07-28", "runDirs": ["…r1", "…r2", "…r3"],
                "humanReview": "…", "forceReason": null}
  }
}
```

The top-level fields keep meaning "the last time the WHOLE baseline was rebuilt" and are never
rewritten by a scoped run. Re-running a scoped rebaseline for a seam replaces that seam's entry;
other seams' entries persist. No schema version bump: the key is additive and every existing reader
ignores unknown keys. The F6 pin's `test_baseline_integrity` asserts those four fields are *present*,
never that they are the only ones, so the pin is unaffected.

## Guards

Preserved from today's whole-baseline path, unchanged: exactly 3 run dirs; every run has a
`report.json`; all three runs share one prompt-hash set and one seam set; no run is grader-miscalibrated;
the runs' hashes match the current working tree.

Added or narrowed for the scoped path:

1. **Needs an incumbent.** A scoped rebaseline requires an existing schema-v2 baseline with exactly 3
   replicate entries — there is nothing to carry forward otherwise. Refuse.
2. **Unknown seam name** → refuse, listing the valid seams.
3. **Un-named drift (Q3).** If any seam NOT named has a current tree hash differing from the
   incumbent's, refuse and name the drifted seams. Writing that baseline would pin a hash the tree no
   longer has, leaving the F6 pin red with a misleading message and silently freezing the drift.
4. **Dispersion guard, narrowed.** Applied only to the named seams. Un-named seams' replicate spread
   in these runs is irrelevant — their bars are not being rebuilt from these runs.
5. **Naming an unchanged seam (Q4)** — allowed, but requires `force_reason`, mirroring today's
   "re-baselining the same bundle over a v2 baseline is a judgment call" rule. There is a real future
   use (re-measuring the thesis bar after F107); it just should not be casual.
6. **Verdict governance (Q5).** For a named seam whose hash DID change, the supplied verdict must have
   `decision == "pass"`, `promptHashes` equal to the current tree, and must show that seam as `gated`
   and `ok`. A seam the verdict only carried informationally has not earned a new bar. `force_reason`
   overrides, as today.
7. **Unmappable case id** → refuse rather than guess, matching the verdict's fail-closed treatment.

`--force` (Q6) is scoped: the reason overrides the guards for this invocation and is recorded against
the named seams in `provenance.seamRebaselines`. It never writes the top-level `forceReason`, so a
forced single-seam rebuild can never later be misread as "the whole baseline was forced."

## Case-to-seam matching

The verdict already maps case ids to seams by longest-prefix match (`cid == seam` or
`cid.startswith(seam + "-")`). That logic is lifted out of `evaluate_v2` into a module-level
`case_seam(cid, seams)` helper and reused here, so the two code paths cannot drift apart. `evaluate_v2`
keeps its existing behaviour exactly, including returning `None` for an unmappable id.

## CLI

```
eval rebaseline --runs <d1> <d2> <d3> --seams extract --verdict <run>/verdict.json --human-review "…"
```

`--seams` takes one or more seam names; omitted means today's whole-baseline rebuild. On success the
scoped path prints which seams were rebuilt and which were carried, so the operator sees the scope
they actually got.

## Out of scope

- Fixing the thesis noise itself — that is F107.
- Any change to `fixtures/evals/baseline.json`. This lane ships the capability; the F105 lane runs it.
- The machine-local `eval-driver` skill (`~/.claude/skills/`) lives outside the repo and is not edited
  here; the in-repo `run-eval` skill gets the new flag documented. Flagged as a follow-up.

## Decision provenance

- **Q1 splice-per-seam, and Q2–Q6 as recommended** — user, interactive 2026-07-28, user-approved, NOT
  AFK. Full text: `.superpowers/handoffs/f108-seam-rebaseline-QUESTIONS.md`.
- **Build the capability rather than `--force` the whole baseline or park F105** — user, interactive
  2026-07-28, user-approved, NOT AFK.
- Mechanical picks made by the lane (no design weight): the `--seams` flag name and `nargs="+"` shape;
  `seamRunDirs` as the per-entry note key; `seamRebaselines` as the provenance key; entry-`i`-to-entry-`i`
  pairing in the splice; refusing rather than guessing on an unmappable case id; extracting `case_seam`
  as a shared helper instead of duplicating the prefix match.
- **Not hard-coding any expected extract bar in tests** — standing instruction from the F105 lane
  record; the F105 resume step confirms the number the implementation actually writes.
