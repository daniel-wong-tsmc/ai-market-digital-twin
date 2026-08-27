# F127 — enforce the excerpt length cap in the extraction gate — DONE

**Date:** 2026-08-25
**Branch:** `f127-excerpt-length` (worktree `.worktrees/f127-excerpt-length`), off main `e6b9de3`
**Status:** complete on the branch. **NOT merged, awaiting coordinator.** Not pushed.

---

## Bottom line

An over-long excerpt is now thrown away by the gate, the same way an invented one
already was. The check sits in `gpu_agent/gate.py::check_finding`, which every
finding passing through the gate goes through, so it covers all three gated paths —
extraction, the judge, and the pipeline — not just extraction. (One un-gated writer
exists, `wiki-ingest`; see the code-review section.)

**The one thing the coordinator must read before merging:** the backlog item's own
premise was out of date, and following it literally would have thrown away real
work. Details in AFK-default 1 below. That is the decision most worth a second
opinion.

---

## Commits (oldest first)

| Hash | What |
| --- | --- |
| `6e1df10` | docs(F127): design and plan for the excerpt-length gate |
| `971938e` | feat(F127): word and sentence counters for the excerpt length cap |
| `e1cf771` | feat(F127): reject over-long excerpts in check_finding |
| `d2b68e2` | test(F127): extraction path drops an over-long excerpt |
| `7fc5b67` | docs(F127): tick the excerpt-length item and record the enforced cap |
| `fa5668e` | fix(F127): quarter and fiscal-year labels are not sentence ends |
| `d155b20` | refactor(F127): one callable rule, so the store audit cannot drift |
| `93b9bb8` | test(F127): pin the sentence counter's known limits as intentional |
| `c83f62c` | fix(F127): stop the sentence counter over-counting on abbreviations |
| _(final)_ | docs(F127): code-review corrections + this handoff |

`git diff --name-only main` is seven files and nothing else:

```
docs/fix-backlog.md
docs/publishing-posture.md
docs/superpowers/plans/2026-08-25-f127-excerpt-length.md
docs/superpowers/specs/2026-08-25-f127-excerpt-length-design.md
gpu_agent/gate.py
tests/test_extractor_v12.py
tests/test_gate_excerpt_length.py
```

Nothing under `store/`, `site/`, `registry/`, `fixtures/`, `work/`, or any prompt file.

Spec: `docs/superpowers/specs/2026-08-25-f127-excerpt-length-design.md`
Plan: `docs/superpowers/plans/2026-08-25-f127-excerpt-length.md`
Decision record: `.superpowers/sdd/2026-08-25-f127-excerpt-length/QUESTIONS.md`, copied to
`.superpowers/handoffs/f127-excerpt-length-QUESTIONS.md` per the CLAUDE.md question-stop
convention.

---

## What the rule is

An evidence excerpt is rejected when it is **over 50 words AND over two sentences**,
or when it is **over 100 words** regardless of sentence count.

```
f: excerpt too long (60 words > 50 and 4 sentences > 2)
f: excerpt too long (120 words > 100 absolute cap)
```

- Word count is `len(excerpt.split())` — the same way the posture doc measured.
- Sentence count is terminal punctuation, minus abbreviations, initials, decimals,
  quarter/fiscal-year labels, dotted acronyms, and any terminator not followed by a
  capital. Biased to **under**-count, because under-counting lets a long excerpt
  through while over-counting rejects honest work, and the count is only consulted
  once an excerpt is already over 50 words. Not infallible — see the two sections
  below, which name the case that still over-counts.
- `excerpt_length_violations(fid, excerpt)` is the single public definition of the
  rule. `check_finding` calls it, and so does the store-audit test, so the two
  cannot drift apart.

---

## Test results (run fresh on the final tree)

- `../../.venv/Scripts/python -m pytest -q` → **2765 passed, 6 skipped**, 1 warning, 449s.
- Baseline was 2720 passed / 6 skipped, so this lane adds **45 tests** and removes none.
  The 6 skips are the expected worktree skips (price-scrape data lives in the root checkout).
- Other pins, run together after the last commit: `test_scoring_v1_replay_pin`,
  `test_replay_v12`, `test_f66_live_replay`, `test_narrator_bullets_gate`,
  `test_narrator_issues_gate`, `test_run_cycle_conformance` → **97 passed**.
- `git status --porcelain store work fixtures registry` → empty. Nothing under `store/`,
  `work/eval-2026-08-24/`, `fixtures/` or `registry/` was touched.

### F6 pin: byte-untouched — YES

- `../../.venv/Scripts/python -m pytest tests/test_evals_baseline_pin.py -q` → **2 passed**,
  run on its own after the last code commit as well as inside the full suite.
- Evidence it could not have moved: `git diff --name-only main` (reproduced above) contains
  no prompt file, no cli vocab glue, no registry vocab data, and no `fixtures/`. The only
  product file changed is `gpu_agent/gate.py`. No baseline was re-recorded and
  `fixtures/evals/baseline.json` was never opened.

### Stored excerpts still pass — YES

`tests/test_gate_excerpt_length.py::test_every_committed_store_excerpt_survives_the_gate`
walks every `store/**/*.json`, feeds each excerpt to the real
`excerpt_length_violations`, and fails if any is rejected. It scans **644 excerpts**
and finds **zero** offenders. It also asserts it scanned more than 500, so it cannot
pass silently by finding nothing.

### The extraction path really is covered

`tests/test_extractor_v12.py::test_over_long_excerpt_dropped_even_though_it_is_verbatim`
sits beside the existing verbatim-check test. Its excerpt genuinely is in the source
document, so only the new length check can fire. Confirmed to exercise the new code by
temporarily raising `EXCERPT_MAX_WORDS` to 500 and watching it go red, then restoring 50.

---

## AFK-default decisions — the user was AFK and approved NONE of these

The standing question-stop rule in CLAUDE.md says a lane should park on a design fork
rather than pick one; this lane's dispatch brief instead directed AFK-default recording.
Flagging the tension rather than hiding it, as F124 did. A `-QUESTIONS.md` sentinel was
written as well, so the fork can still be relayed to the user.

### 1. "two sentences **or** 50 words" is read as OR, not AND — please review this one

The dispatch brief suggested a hard 50-word cap (">50 words rejected") and asked me to
confirm the new gate would not have rejected anything already stored. Re-measuring the
store falsified that premise:

| | Posture doc, 2026-08-04 | Measured on this branch |
| --- | --- | --- |
| Excerpts in the store | 334 | **644** |
| Longest | 40 words | **70 words** |
| Over 50 words | 0 | 1 |
| Over 2 sentences | not measured | 2 |
| Over **both** | — | **0** |

The 70-word excerpt is a verbatim, single-sentence AMD 10-Q gross-margin quote in
`store/findings/ir-amd-com-cfa508a5-2026-08-3.json`. The two multi-sentence excerpts are
29 words/4 sentences and 36 words/3 sentences — both short. So a hard 50-word cap would
have rejected a real, well-sourced finding, and a hard 2-sentence cap two more.

Reasons for the OR reading: it is literally what the DECIDED text says; the posture doc
justifies the norm by claiming it "costs nothing today", which is only true under OR; and
the harm the norm guards against is reproducing an article, which a single quoted sentence
from a filing is not.

**If the user wants AND instead:** it is one `and`→`or` in
`gpu_agent/gate.py::excerpt_length_violations`, plus a decision about the three stored
excerpts that would then be non-conforming and the store test that would go red.

### 2. The 100-word absolute ceiling is invented

Not in the posture doc. Added because without it the OR rule has a trivial bypass: text
with no sentence-ending punctuation counts as one sentence and passes at any length, so the
gate would not be a gate. 100 is twice the stated norm and well clear of the largest
excerpt ever stored (70). The doc's "never more than is needed" supports a ceiling in
spirit but names no number, so the number is mine.

### 3. Sentence counting was implemented rather than left as a documented norm

The brief allowed dropping it if it proved fragile. It did not — the hard cases in real
financial prose are abbreviations, initials, decimals and quarter labels, all handled in
about twenty lines of stdlib, and counting errors are biased to the safe direction.

### 4. The check lives in `gate.py`, not beside the verbatim check in `extractor.py`

The brief pointed at the verbatim check, but that check needs the fetched page and cannot
move. `check_finding` is the one function the extractor, `judgment/judge.py` and
`pipeline.py` all route through (verified by grep), so putting the length check there
covers every path an excerpt travels.

### 5. Nothing under `store/` was edited

The store is append-only. Under the rule as built nothing stored is non-conforming, so no
exemption list was needed either.

### 6. The handoff and QUESTIONS files were force-added to git

`.superpowers/` is in `.gitignore`, and every previous lane's DONE file is untracked and
lives in the root checkout. The brief said to commit the handoff on the branch and also
forbids writing to the root checkout, so `git add -f` was the only way to stop these files
dying with the worktree. Convention break, flagged. If the coordinator prefers the old
way: `git rm --cached` them and copy the files to the root checkout's
`.superpowers/handoffs/`.

---

## Code review found a real bug — worth knowing about

A reviewer subagent was dispatched against the branch and returned one MUST-FIX that was
genuine and is now fixed (`c83f62c`).

The first version of the sentence counter claimed its errors were always biased toward
under-counting, which is the safe direction. **That claim was false.** Dotted acronyms and
abbreviations not on the list — `A.I.`, `Ph.D.`, `R.O.E.`, `J.H.`, `2.1.`, `Fed.`, `Calif.`,
`Rev.`, `mn.` — were all read as sentence ends, and the reviewer produced a realistic 58-word,
two-sentence passage that the gate **rejected**. That is exactly the harm the design says it
avoids.

Fixed by two rules, which between them handle all nine reported inputs: a terminator only
counts when end-of-text or a capital follows it (real prose capitalises after a full stop;
abbreviations do not), and a token with a period inside it is never a sentence end. Both are
skip-only, so neither can introduce a new over-count. Regression tests cover all nine plus the
reviewer's 58-word passage.

The counter is still not perfect and the docstring now says so instead of overclaiming: an
abbreviation that is both unlisted and followed by a capitalised word over-counts by one. That
is a further reason the gate requires BOTH limits broken rather than trusting the sentence
count alone.

Also taken from the review: the O(n²) prefix re-slicing in the counter (1600 sentences 0.42s
→ 0.026s), a non-string guard on the now-public helper, and three documents that overstated
what the change covers.

**Reviewer finding NOT acted on, deliberately:** `gpu_agent/wiki/ingest.py::route_findings`
appends into the finding store without calling `check_finding` at all, so
`gpu-agent wiki-ingest --findings <file>` can write an over-long excerpt to `store/`. This is
pre-existing and not F127's — every other gate rule (F2e, F8, F17) is bypassed by the same
path, and in a normal cycle that file is the gated output of `extract`. Closing it changes
behaviour for every gate rule at once and deserves its own backlog item. The spec, the
QUESTIONS record and the backlog entry were corrected to stop claiming "every path".

---

## Known limits of the sentence counter

All in the **safe** (under-count) direction, all deliberate, none affecting the store:

- An abbreviation that is unlisted AND followed by a capitalised word over-counts by one.
  This is the one **unsafe** residue; it takes an excerpt already over 50 words for it to
  matter, and it is why both limits must break.
- A terminator inside a closing quote or bracket is not counted:
  `He said 'it is done.' Then he left.` counts 1, not 2.
- A sentence ending on a single-letter word is not counted: `The answer is A. The next is B.`
  counts 1. Same rule is what makes `U.S.` work.
- A sentence ending on a quarter label is not counted: `Shipments rose in Q3. Margins held.`
  counts 1.
- `in 2026.` **is** still a sentence end — the period-label regex is anchored to
  `FY`/`CY`/`Q`/`H` forms and does not swallow bare years.

Each of these makes a long excerpt more likely to pass, never more likely to be rejected.
If the counter is ever tightened, the store test must be re-run first.

---

## What the coordinator must do

1. **Read AFK-default 1** and decide whether the OR reading stands. Everything else follows
   from it. Nothing else in this lane is contentious.
2. **Merge normally.** There is no rebuild step, no schema change, and no store or site
   artefact to regenerate — this lane only adds a rejection rule and tests.
3. **Nothing to re-record.** The F6 baseline was not touched and must not be.

Nothing was left out of the brief except the eval-gate *run* itself: the brief said an
extraction prompt/gate change re-runs the eval gate with F6 expected byte-untouched. F6 was
verified in-lane and is byte-untouched (evidence above), and since no prompt byte changed,
the emitted brain prompts are identical to main's, so a replicate eval run would be
comparing a tree that produces the same prompts. If the coordinator wants the full eval
replicates run anyway, that is a separate, unblocked step.
