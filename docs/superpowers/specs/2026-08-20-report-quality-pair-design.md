# F119 + F120 — Report Quality Pair (design)

Lane: `report-quality-pair` (branch `report-quality-pair`, worktree
`.worktrees/report-quality-pair`). Renderer-only: `gpu_agent/report.py` (+ tests).
No schema, scoring, or brain-prompt changes; no `store/`, `site/`, `web/`,
run-cycle SKILL.md, or pin changes.

## Decision provenance

- **Q1 (F119) — user-approved 2026-08-20 (interactive, via orchestrator relay of
  `.superpowers/handoffs/report-quality-pair-QUESTIONS.md`): Option B.** Add a second
  shrink lever: when THE CALLS is already at its `top_k == 1` floor and the top half is
  still over `_ABOVE_FOLD_BUDGET`, fold QUICK GLANCE Tier 2 (Scarcity) and Tier 3
  (Money) to one honest summary line each; the full rows are guaranteed in the appendix.
  Tier 1 (Verdict) never folds. Under-budget pages stay byte-identical.
  **Sub-answer (same approval): if both levers bottom out and the page is still over 88
  lines, ship over budget — exactly today's user-accepted (2026-07-13) behavior.**
- **Q2 (F120) — user-approved 2026-08-20 (same relay): Option A, BLOCK.** One final
  `reader.lint_acronyms` pass over the fully assembled above-fold string right before
  `render_report` returns; any off-allowlist all-caps token raises an error naming the
  token(s). Consistent with the fleet posture separately approved for the scheduler
  lane: unattended runs that hit a blocking condition fail loud and park. Recovery =
  one-line `registry/acronyms.json` edit + re-render from saved artifacts (render is a
  pure function over stored data; nothing is re-spent).
- **Brainstorm discovery (recorded, not a fork):** the backlog's other F119 candidate
  lever — lowering `_CHANGE_LINE_CAP` — is a dead end: it caps how many moved items are
  *named within one line per horizon* (the rest fold to "+N more moved" on the same
  line), so lowering it saves zero above-fold lines. Only the QUICK GLANCE fold can
  shorten the page.
- **Mechanical choices (lane-decided, trivial):**
  - The final F120 lint checks only text above `reader.APPENDIX_DIVIDER` (the appendix
    legitimately carries raw acronyms like DMI/SMI) and uses only the existing
    `reader.lint_acronyms` — no new lint rules.
  - The block raises `ValueError` (the module's existing error convention, e.g.
    `load_scorecard`) with a message naming the token(s) and the remediation file.
  - Fold summary wording: `Tier 2 — Scarcity: N tracked, M moved — full rows below the
    divider` (mirrors the ranked-calls fold line's pointer pattern; passes the acronym
    lint; "moved" = rows whose nearest-horizon arrow is not the unchanged arrow).
  - The full (un-folded) QUICK GLANCE is inserted into the appendix right after the
    full THE CALLS block (same "promise made above, kept below" pattern, and only when
    the fold actually fired).
  - F120's lint runs after F119's shrink/fold loop, so it lints exactly the text that
    ships.

## F119 — second shrink lever (QUICK GLANCE Tier 2/3 fold)

`render_quick_glance(state, change=None, registry=None, fold_detail=False)` gains the
keyword-only-by-position-default `fold_detail` flag. `False` (every existing caller) is
byte-identical. `True` renders Tier 1 unchanged, then one summary line per tier in
place of each of Tier 2 and Tier 3 (header line + rows collapse into the one line).

`render_report`'s existing budget loop (change-first path only) gains a step after
`top_k` bottoms out: if still over budget and `state is not None`, re-render
`top[3]` with `fold_detail=True`, insert the full QUICK GLANCE at `appendix[2]`
(right after the divider and the full THE CALLS), rebuild `body`. If still over
budget after that: return as-is (ship over budget, user-accepted).

## F120 — assembled above-fold acronym block

At the end of `render_report`, immediately before `return body`:
lint `body.split(reader.APPENDIX_DIVIDER)[0]` with `reader.lint_acronyms`; if any
offenders, raise `ValueError` naming them and pointing at
`registry/acronyms.json` ("allowed"). Applies to both the legacy and change-first
paths, monthly and daily (one renderer — one gate).

## Testing

TDD, RED first, per-item commits (F119 then F120, independently revertible):
- F119: a change-first render big enough to still overshoot at `top_k == 1` comes in
  at/under 88 lines with the fold marker above the fold, Tier 1 rows intact, and the
  full Tier 2/3 rows present in the appendix's QUICK GLANCE; a small render carries no
  fold marker; both-levers-bottomed-still-over ships (no exception, over budget).
- F120: a thesis title carrying a fabricated off-allowlist token (e.g. `ZORPX9`)
  blocks the render with a `ValueError` naming the token; clean renders (the whole
  existing suite) stay green.
- Full suite green in the worktree (~2547 passed, 6 skips); all pins byte-untouched.
