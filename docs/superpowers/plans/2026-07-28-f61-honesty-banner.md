# F61 — honesty line on the story page: implementation plan

Spec: `docs/superpowers/specs/2026-07-28-f61-honesty-banner-design.md`
Lane: `.worktrees/f61-honesty-banner`, branch `f61-honesty-banner` off `1546da8`.
Python: `../../.venv/Scripts/python` (shared root venv — never a per-worktree venv).
TDD throughout: test first, watch it fail for the right reason, then implement.

---

## Task 1 — Model: `story_model.evidence_honesty()` + wiring into `_base_model`

**Tests first** (`tests/dashboard/test_story_model.py`):

1. Full case: a store whose latest scorecard has dated evidence and
   `confidence: {level: high, basis: "self-consistency over 3 samples"}` →
   `model["honesty"] == {"median": …, "oldest": …, "stale_pct": …, "level": "high", "votes": 3}`.
2. Numbers agree with `report.evidence_vintage` on the same scorecard (single source of truth).
3. `basis` with no digits → `votes is None`, level still present.
4. No `confidence` key → `level is None`, vintage still present.
5. No dated evidence → `median is None`, confidence still present.
6. Neither → `model["honesty"] is None`.
7. Malformed evidence date (e.g. `"last spring"`) → `model["honesty"] is None`, no exception.
8. Determinism: two builds of the same store give equal `honesty` dicts.

**Implementation:**

- `_VintageAdapter` — a tiny private shim exposing `.asOf` and `.findings[].evidence[].date`
  from the raw scorecard dict, with the docstring explaining exactly why (spec §2). Skips
  evidence entries that are not dicts.
- `evidence_honesty(latest: dict, as_of: str) -> dict | None`: builds the adapter, calls
  `report.evidence_vintage`, extracts confidence, returns the dict or `None`. Wrapped in
  `try/except Exception` → warn to stderr, return `None`.
- `_base_model` gains `"honesty": evidence_honesty(latest, as_of)` in its model dict, so both
  the assembler path and the narrated-artifact path get it identically (they share `_base_model`).
- Import `evidence_vintage` from `gpu_agent.report` — verify no import cycle at module load
  (`site_model.py` already does the same top-level import from `dashboard/`; confirm by running
  the dashboard tests, and if a cycle appears, use the function-level-import idiom that F96 set
  as precedent and record it).

**Green gate:** `pytest tests/dashboard/test_story_model.py`.

## Task 2 — Render: the line under the dateline

**Tests first** (`tests/dashboard/test_story_render.py`):

1. `_headline_block` output contains the line inside `.st-head`, after the `.st-date` dateline.
2. Humanised dates at all three grains: `2026-05-12` → `May 12, 2026`; `2026-06` → `June 2026`;
   `2026` → `2026`. (Unit-test the date formatter directly.)
3. Stale share 0 → "none of it is more than six weeks old"; non-zero → "about N percent".
4. `votes is None` → "from separate reads that agreed"; votes present → "from 3 separate reads".
5. `model["honesty"] is None` → `_headline_block` output is byte-identical to today's (no empty
   element, no stray markup).
6. `lint_story_copy` returns no hits for a page carrying the line; in particular the line adds
   no "index"/"indexed" token (the existing whole-page lint test guards the one-token budget).
7. HTML-escaping: a scorecard confidence level containing `<` renders escaped.

**Implementation:**

- `_human_date(s: str) -> str` in `story_render.py`: day/month/year grain → long form; anything
  unparseable returns the input unchanged (never raises).
- `_honesty_line(model) -> str`: returns `""` when `model.get("honesty")` is falsy; otherwise a
  `<p class="st-honest">` with the two sentences per spec §3, every value `esc()`'d.
- `_headline_block` appends it after `.st-date`.
- `STORY_CSS` gains `.st-honest{...}` — small, muted, matching the existing `.st-date` treatment.

**Green gate:** `pytest tests/dashboard/`.

## Task 3 — Backlog + docs

- Tick the report.py half of F61 as done-by-F67 and rewrite the F61 entry to describe what
  actually shipped (story page; coverage out of scope), linking spec + plan.
- New entry **F109 — the gather step stopped recording coverage gaps durably** (renumbered from F106 at merge time: number collided with the concurrent HuggingNews mint): gaps are
  computed only by the gather skill's inline snippet, written to gitignored
  `work/<cycle>/docs/gather-log.json`, and as of the 2026-07-27 cycle not written at all (no
  `coverageGaps` key; `notCovered: []`), so the "21 gaps" figure lives only as prose in
  `store/cycle-log.json`. Nothing downstream can render or audit coverage.
  Include the concurrent-mint caveat line (F105 exists as of 2026-07-27; renumber if collided).
- Commit; **do not merge**.

## Task 4 — Full-suite gate + DONE sentinel

- `../../.venv/Scripts/python -m pytest` — full suite green, ~6 skips expected.
- Verify all four pins green by name: `test_evals_baseline_pin`, the scoring-v1 replay pin,
  `test_run_cycle_conformance`, the narrator `test_prompt_pin`.
- Verify the forbidden diff is empty across the branch: `fixtures/`, `registry/`,
  `gpu_agent/evals/`, `gpu_agent/narrator/`, `gpu_agent/scoring.py`, `gpu_agent/report.py`,
  `.claude/skills/run-cycle/`.
- Write `.superpowers/handoffs/f61-honesty-banner-DONE.md` at the **repo root** (not the
  worktree) and stop. Only the user merges.
