# F61 — Evidence-vintage + honest-confidence line on the story page

**Date:** 2026-07-28
**Status:** Spec (re-aimed after investigation; all three forks answered interactively by the
user this session — zero AFK)
**Lane:** `f61-honesty-banner`, worktree `.worktrees/f61-honesty-banner`, branch off `1546da8`.
**Scope:** display/renderer only — `gpu_agent/dashboard/story_model.py` +
`gpu_agent/dashboard/story_render.py` + their tests, plus one new backlog entry.
**Explicitly OUT:** coverage gaps (see §6), `report.py`, scoring, every brain prompt, evals,
fixtures, registry, run-cycle SKILL.md.

---

## 1. Why this lane changed shape

F61 was filed on 2026-07-03 against the then-current text brief and scoped "`report.py` only".
Two things happened since:

- **F67 (merged `b0e8061`, 2026-07-04) already built it in `report.py`.**
  `report.evidence_vintage()` computes median date, oldest date and the share older than six
  weeks against `asOf` (no wall clock); `report.render_header()` prints both that line and
  `Confidence: vote agreement <level> (N votes) — agreement between raters, not evidence
  freshness`. That is F61's original text, word for word. **The report.py half of F61 is
  done-by-F67** and is recorded as such in the backlog.
- **The published surface moved.** Since F101 the category front page is the story page
  (`site/<cat>/index.html`), rendered by `story_model.py` + `story_render.py`. It carries no
  vintage line, no confidence label, no coverage note. Verified against the built site.

Two other renderers still compute an aggregate vintage — `site_model._why`'s "trust" entry
(feeding `site_render.render_category_page`) and the F97 `brief_render` footer — but
`site_build.py` emits neither page any more (`render_category_page` has no non-test callers).
So today the repo computes the number three times and shows the reader zero times.

**F103 does not overlap.** F103 is per-row (each evidence row dated, weight-sorted,
publisher-capped, dimmed when aging). It computes no aggregate and never touches the confidence
label. F61 and F103 are complementary; no F103 rework.

## 2. Decisions (interactive, user-approved this session)

| # | Fork | User pick |
|---|---|---|
| 1 | Which surface | **Story page front (the live product).** Mark the `report.py` half done-by-F67. |
| 2 | Coverage gaps | **Out of scope.** File the durable-data defect as a new backlog item. |
| 3 | Placement + wording | **One quiet plain-English line under the dateline**, stop-slopped for the executive reader. |

Mechanical choices made in-lane (no design weight, recorded here per convention):

- **Reuse of `report.evidence_vintage` is by duck-typed adapter.** `evidence_vintage` reads
  exactly two things off its argument: `sc.asOf`, and `sc.findings[].evidence[].date`. A full
  `Scorecard.model_validate()` is not available at this seam — the story model holds the
  scorecard as a raw dict, and `Finding` demands ~20 required fields that partial fixtures (and
  any legacy scorecard) do not carry, so validating would make the line vanish for the wrong
  reason. The story model therefore hands `evidence_vintage` a minimal adapter exposing only
  those two paths. **`report.py` is not touched**, and there remains exactly one implementation
  of the date math.
- **`evidence_vintage` is imported at function level, not module level.** `report.py` and
  `brief.py` already import each other and resolve at call time; a new top-level edge from the
  dashboard into that pair is avoidable risk for zero benefit. Same idiom as `publisher.py`, and
  the F96 precedent (user-chosen there for the same reason).
- **Wording amended during the build (recorded here, not a re-opened fork):** the confidence
  sentence says *how much* the reads agreed, never *that* they agreed. The first draft read
  "from 3 separate reads that agreed", which is only true at level "high" — the live scorecard
  on the day of the build read "medium". A regression test pins this at all three levels.
- **Confidence is read straight off the raw scorecard dict** (`confidence.level` +
  `confidence.basis`); the vote count is the first integer in `basis`, the same rule
  `report.render_header` uses.

## 3. What renders

One line, immediately under the dateline inside `.st-head`, in small muted type.

Full form (both halves available):

> How current this is — the evidence behind this story is typically dated **June 2026**; the
> oldest piece is from **May 12, 2026**, and about **31 percent** of it is more than six weeks
> old. Confidence in today's reading is **high**, from **3** separate reads that agreed — that
> is the reads agreeing with each other, not a sign that the evidence is fresh.

Rules:

- **Dates are humanised, never ISO.** `2026-05-12` → `May 12, 2026`; `2026-06` → `June 2026`;
  `2026` → `2026`. Evidence dates come at day, month or year grain and all three occur in the
  store.
- **Zero stale share reads as words, not "0 percent"**: "…and none of it is more than six weeks
  old."
- **Vote count omitted when `basis` carries no number**: "Confidence in today's reading is
  **high**, from separate reads that agreed — that is the reads agreeing with each other, not a
  sign that the evidence is fresh."
- **Six weeks is not a new number.** It is `evidence_vintage`'s existing 42-day cutoff, stated
  in the reader's units.

## 4. Degradation (the page must never break or overclaim)

| Situation | Behaviour |
|---|---|
| No evidence dates at all | Vintage half dropped; confidence half still renders. |
| No `confidence` on the scorecard | Confidence half dropped; vintage half still renders. |
| Neither available / no scorecard | **No line at all** — no empty strip, no "not recorded" filler. |
| Malformed date string anywhere | Whole line dropped, warning to stderr — same degradation contract `build_story_model` already uses for a bad artifact. The live page never crashes on data shape. |

## 5. Constraints this lane respects

- **Clock-free.** Staleness is measured against the scorecard's `asOf`, never `date.today()` —
  inherited free from `evidence_vintage`. Equal inputs give a byte-identical page.
- **Copy lint.** The rendered line must pass `lint_story_copy`: none of the banned words
  (`DMI`, `SMI`, `momentum`, `strengthening`, `tightening`, `accelerating`, `allocation`,
  `doctrine`, `robust`, `leverage`) and — critically — **it must not contain "index" or
  "indexed"**; the page's single allowed use is already spent by the gap chart's axis label.
- **Escaped.** Every interpolated value goes through `esc()`; dates and levels come from stored
  data.
- **Pins.** Nothing here touches scoring, prompts, evals, fixtures, registry or the run cycle.
  All four pins (F6 baseline, scoring-v1 replay, F83 conformance, narrator prompt) must stay
  green; if any reddens the lane STOPS and reports.

## 6. Coverage gaps: why they are out, and the defect found

Coverage gaps cannot be rendered from committed data today:

- `manifest.compute_coverage_gaps()` has **no production caller in the package** — only the
  gather skill's inline snippet runs it.
- Its output belongs in `work/<cycle>/docs/gather-log.json` under `coverageGaps`, and `work/`
  is gitignored. Scorecards carry no coverage field.
- **In practice it is not being written at all.** The 2026-07-27 cycle's `gather-log.json` has
  no `coverageGaps` key; `corpus-report.json`'s `notCovered` is `[]`. The cycle's own "21 gaps
  (13 source, 8 indicator)" figure survives only as free-form prose in `store/cycle-log.json`.

Rendering it would need a persistence step in gather/run-cycle — outside a display-only lane.
Filed as its own backlog item in this branch.

## 7. Testing

- **Model:** median/oldest/stale-share pass-through from `evidence_vintage`; confidence level +
  vote extraction; each degradation row of §4; a malformed date does not raise; the model is
  identical for two builds with the same inputs.
- **Render:** the line appears under the dateline inside `.st-head`; humanised dates at all
  three grains; the "none of it" wording at zero share; the no-vote-count wording; nothing
  rendered when both halves are absent; the line survives `lint_story_copy`; no "index" token
  added (the whole-page lint test already guards the budget).
- **End-to-end:** the existing `render_story_page` page-lint test stays green and the front page
  builds.

## 8. Post-merge criterion (not forced in-lane)

The next cycle's rebuilt front page shows the line under the dateline with real numbers. Only
the user merges; this lane stops at a green suite and a DONE sentinel.
