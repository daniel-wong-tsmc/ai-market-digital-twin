# F68 — F67 follow-up bundle: audit against current code (2026-08-04)

Lane: `f68-output-followups` (worktree `.worktrees/f68-output-followups`, branch
`f68-output-followups`).

## Why this audit exists

The F68 backlog entry (docs/fix-backlog.md line 543) carries the warning "partly ABSORBED
by F78's brief rewrite". Before building anything, this lane verified each sub-item
(a)–(f) against the code as it stands today.

**Headline finding: F68 (b)–(f) were already built and merged**, on the `fix/lane-polish`
branch (merge commit `e173ebc`, 2026-07-04), *before* the F78 rewrite. All five survived
F78 intact — each is still live in the current render path, each still has a passing test.
The backlog entry was simply never ticked. **Only sub-item (a) has residual work**, and
that residual work is a design fork, not a mechanical item — see below.

Net code change from this lane: the F68(a) wire-up only (after the user answered the
question-stop). Sub-items (b)–(f) needed no code.

## Per-sub-item verdicts

### (a) Thesis-prose deterministic lint — WAS question-stopped, now ANSWERED and BUILT

**Resolved 2026-08-04 (user-approved, interactive). See "Decision provenance" for the
three answers and "F68(a) wire-up as built" for what shipped.** The audit finding that
prompted the question-stop is preserved below.

- **Built:** `lint_thesis_prose(statement, mechanism)` exists at
  `gpu_agent/thesis.py:503` (commit `0547aea`). It reuses `reader.lint_prose` with
  `max_sentences=1` for both fields, which also picks up the finding-id and
  off-allowlist-acronym checks. Four unit tests in `tests/test_lane_polish.py:189-222`.
- **Not built:** the function has **zero callers**. Verified by repo-wide grep — the only
  non-test references are its own definition, its docstring, and the original lane plan.
  The lane-polish plan
  (`docs/superpowers/plans/2026-07-04-lane-polish.md:87`) explicitly permitted landing the
  function alone and deferring the wire-up, and the deferral was taken; the module comment
  at `gpu_agent/thesis.py:490-500` records it.
- **So the F68(a) thresholds/design question is already answered** (one sentence each,
  ids only in `falsifiableTrigger`, post-hoc, reuses `lint_prose`). What remains open is
  **whether and how to wire it in** — which is behaviour-shaping, so it is
  question-stopped rather than picked. See
  `.superpowers/handoffs/f68-output-followups-QUESTIONS.md`.
- **Blast radius measured, not guessed:** running the existing lint over the live thesis
  book (`store/theses/chips.merchant-gpu/book.json`, 52 standing entries) flags **6**
  entries — 5 two-sentence `statement`s and 1 off-allowlist acronym (`ASE`). All 6 are
  genuine violations, not splitter false positives. A fail-loud wire-up therefore blocks
  the next thesis cycle until those 6 are re-judged.

### (b) Citation map renders only each finding's first evidence item — DONE

`gpu_agent/report.py:767 render_citation_map` iterates `for ev in f.evidence`, one line
per evidence item (commit `317b8af`). Still wired into `render_report`
(`gpu_agent/report.py:1079`). Tests: `tests/test_lane_polish.py:42,65`.

### (c) BLUF reconciliation note keys off raw `smiContribution` sign — DONE

`gpu_agent/brief.py:50` gates the "supply is the constraint" note on
`ds.sdgiDirection == "supply-led"`; the raw-sign proxy is gone (commit `93be164`).
Survived the F78 brief rewrite. Tests: `tests/test_lane_polish.py:94,103`.

### (d) What-moved empty state double-states the folded count — DONE

`gpu_agent/brief.py:277` guards the always-on tail with `if movement.moved and
movement.foldedCount`, so the empty-state branch at line 271 owns the message alone
(commit `ffb0983`). Tests: `tests/test_lane_polish.py:128,137`.

### (e) `reader.label_ids_in_text` iterative-substitution chaining fragility — DONE

`gpu_agent/reader.py:80` is now a **single** `re.sub` over one alternation of all ids,
longest-first, so an inserted label is never re-scanned (commit `a70933a`). The docstring
carries a do-not-regress note. Tests: `tests/test_lane_polish.py:148,168` — including a
byte-identical pin for the real no-collision case.

Note: the sub-item's alternative fix ("add a registry lint") was **not** taken; the
single-pass substitution was chosen instead, which removes the failure mode at the source
and needs no registry change. That is the shipped answer, recorded here so it isn't
re-litigated.

### (f) Live thesis prose carries off-allowlist tokens (`MI`, `GB300`) — DONE

Both tokens are on `registry/acronyms.json` (`GB300` line 105, `MI` line 108; `MI` added
by commit `632539c`). Test: `tests/test_lane_polish.py:227`.

**Residual, surfaced by this audit:** the same class of token has recurred — the live book
now carries `ASE` (the packaging supplier) off-allowlist. This is exactly the recurring
pattern docs/fix-backlog.md:1050 already flags as needing a durable fix, so it belongs to
that item and not to F68. Recorded, not fixed here.

## Out-of-scope confirmations

No sub-item required a change to emitted brain-prompt bytes.
`tests/test_evals_baseline_pin.py` passes untouched. None of the forbidden paths
(fixtures/evals, fixtures/narrator, registry/indicators.json, gpu_agent/scoring.py, the
run-cycle skill, gpu_agent/narrator/prompt.py, gpu_agent/gathering, gpu_agent/manifest)
were read-modified by this lane.

## F68(a) wire-up as built

- **`_adjusted_statement(verdict, rationale)`** (`gpu_agent/thesis.py`) — the
  `"ADJUSTED:"`-prefix parse, lifted verbatim out of `_apply_judgment_record` so the lint
  and the apply path can never check different text. Returns `None` for "no replacement
  statement" and `""` for the bare-`ADJUSTED:` empty replacement, preserving the old
  inline behaviour exactly; pinned by
  `test_adjusted_statement_distinguishes_no_replacement_from_an_empty_one`.
- **`lint_answer_prose(answer)`** (`gpu_agent/thesis.py`) — lifts `lint_thesis_prose` to a
  whole `ThesisAnswer`. Lints proposals' `statement` + `mechanism`, judgments' `mechanism`,
  and an `adjusted` verdict's replacement statement. Labels each violation with the same
  key `gate_answer` uses (thesis id / routed slug) so a blocked cycle names what to
  re-dispatch.
- **`gpu_agent/cli.py` `_thesis`** — runs the lint BEFORE `gate_answer`, returning through
  the existing `_report_voice_violations` so it shares the judge path's `voice-lint: `
  stderr prefix that the run-cycle skill already greps. `store.write` is never reached, so
  a blocked answer leaves the book byte-unchanged.
- **`registry/acronyms.json`** — `"ASE"` added to the `allowed` data list.
- Tests: `tests/test_thesis_prose_lint.py` (11), TDD — RED on the missing import first.

**Live blast radius, re-measured after the ASE addition:** 5 of 52 standing entries would
violate (down from 6; all five are two-sentence `statement`s). In practice the bite is
smaller still: the lint only sees prose written in a *recorded answer*, and a statement is
only rewritten by an `adjusted` verdict — so these five are inert until someone adjusts
those specific theses. Per the user's instruction they were **not** rewritten by this lane;
they clean up as they are re-judged in live cycles.

## Decision provenance

- Verdicts (b)–(f) = **verified facts about current code**, not choices. Each cites the
  file:line and the commit that produced it.
- **(a) Q1 — switch the checker on (vs. delete it): USER-APPROVED (interactive,
  2026-08-04)** — wire the existing tested function into the thesis path.
- **(a) Q2 — BLOCK on violation: USER-APPROVED (interactive, 2026-08-04)** — match the
  judgment-prose check's semantics (one targeted rewrite re-dispatch, then fail loud);
  mirror the existing pattern exactly.
- **(a) Q3 — add `ASE` to `registry/acronyms.json`'s `allowed` list now: USER-APPROVED
  (interactive, 2026-08-04)** — the sanctioned data-extension path per eval-driver
  discipline, taken because blocking was chosen. This supersedes the audit's earlier
  "leave it to the durable fix" recommendation. The recurring-token problem itself still
  belongs to the durable fix at docs/fix-backlog.md:1050.
- None of the three was an AFK-default; all were answered interactively by the user and
  relayed by the orchestrator.
- Mechanical choices made under the trivial-choice clause, recorded here as required:
  (1) **no `--no-voice-lint`-style bypass flag on `thesis`** — F75 removed the whole-run
  `--no-sufficiency` escape hatch on exactly this reasoning, so adding a new one would cut
  against it; (2) **non-adjusted judgments' `rationale` is not statement-linted** — it is a
  history field, never exec-facing book prose, and no statement is written; (3) lint runs
  **before** `gate_answer`, mirroring the judge path's lint-before-gate order.

## Verification

- Full suite: **2157 passed / 6 skipped** (was 2146/6 before this lane; +11 new tests).
- `tests/test_evals_baseline_pin.py` **GREEN** — no emitted brain-prompt bytes changed.
  Verified structurally too: `registry/acronyms.json` is read only by
  `gpu_agent/reader.py`'s allowlist loader (lint side), by no prompt builder; the CLI and
  thesis edits touch no prompt string and `_THESIS_SYSTEM_TEMPLATE` is untouched.
- Untouched per brief: fixtures/evals, fixtures/narrator, registry/indicators.json,
  gpu_agent/scoring.py, the run-cycle skill, gpu_agent/narrator/prompt.py,
  gpu_agent/gathering, gpu_agent/manifest.
