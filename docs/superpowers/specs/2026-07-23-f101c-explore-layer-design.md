# F101 Phase C — The Deep Layer (the narrative's footnote system)

**Date:** 2026-07-23
**Status:** Spec (brainstormed interactively; all decisions interactive user picks — zero AFK)
**Parent:** `docs/superpowers/specs/2026-07-22-f101-narrative-page-design.md` §3.6, §10.3
**Scope:** renderer/copy layer ONLY — five new page families under `site/<category>/`, link
wiring, and a link-integrity build gate. No pipeline change, no prompts, no registry — the
F6 pin, narrator pin, scoring replay pin and F83 conformance are untouched by design.
**Build precondition:** dispatches only AFTER the Phase B lane merges (both touch
`story_model.py`/`story_render.py`; design now, build after — user-directed).

## 1. Governing principle (user-set, 2026-07-23)

Every day the narrative answers the one question — *is supply meeting demand, and why or why
not*. **The deep layer is that narrative's footnote system, not a separate destination.** The
reading path is one unbroken thread: the story makes a claim → the evidence panel shows the
claim's sources → Phase C answers the third click, *when the panel isn't enough*: the full
trail on that topic, the complete chart behind that number, the dossier on that company, how
the same story read last month. Primary entry into every Phase C page is FROM INSIDE the
story (panel footers, KPI chips, entity names, archive chips), landing pre-filtered to the
claim the reader came from, with a breadcrumb back to today's story. The Explore band is the
secondary entrance for roaming. No page is a generic data library: each opens with a one-line
tie-back ("Behind the verdict: …") and is organized around the question.

## 2. Decisions (interactive, this session)

| Decision | Pick |
|---|---|
| Scope | All five destinations in ONE lane (no dead tiles) |
| Findings UX | Client-side filter (self-contained script; extends the F95 relaxation to Explore pages — user-approved via this pick) |
| Entity pages | Dossier + live evidence (wiki prose is the spine; auto-appended findings + series keep it current) |
| History centerpiece | Verdict timeline (full-length gap chart with each month's headline pinned; dimension detail folds under) |
| Story archive | Page per day + index (permalinks; fallback days show their one-line notice) |
| Entry paths | Narrative-first (hard requirement, §1); Explore band secondary |

## 3. Pages

All under `site/<category>/`; every page: the shared stylesheet, a breadcrumb strip
("← today's story"), a one-line question tie-back under the title, `Source:` lines on every
chart, and the Phase A banned-word lint.

### 3.1 `story/index.html` + `story/<date>.html`
One permalink page per narrated day, rendered with the SAME scene renderer as the front page
(scenes, source lines, related coverage, evidence panel). Fallback days render the dated
one-line notice ("No narrated entry this day — the page ran on assembled data."). Index =
every day's headline, newest first, with fellBack days marked. Front-page archive chips and
"story archive →" now point here.

### 3.2 `findings/index.html`
All findings as server-rendered cards (statement, dimension tags, entity, date, evidence
links via the panel pattern). **Default view is the question, not a library:** two top-level
groups — "evidence demand is growing" and "evidence supply is (or isn't) catching up" —
derived from each finding's stored side/polarity fields. A self-contained filter script
narrows by dimension, entity, date range, source tier; arriving from a panel footer
pre-applies the filter via URL hash (e.g. `#dim=bottleneck&entity=nvidia` read by the same
script). Growth note: renders all findings for now; if the page exceeds ~1 MB the build
splits older months to `findings/<YYYY-MM>.html` (mechanical, no redesign).

### 3.3 `series/index.html`
One section per tracked series, grouped by the KPI framework: *the price of the gap* /
*demand gauges* / *supply arriving* / *relief ahead*. Each: full-history server-side SVG
chart (gap-chart visual language), latest value, the plain-words chip description, what its
movement means for the gap (one line), and a source table from the series rows. KPI chips on
the front page link to their section anchor.

### 3.4 `entities/index.html` + `entities/<slug>.html`
The wiki dossier markdown rendered as the body, prefaced by a one-line role-in-the-gap
("TSMC — where the supply bottleneck lives"), derived from which side the entity's findings
sit on (supply/demand/mixed). Auto-appended: findings mentioning the entity (newest first,
panel-linked) and any series it owns. Entity names in story prose become links. Index groups
entities by role (supply chain / buyers / makers / other).

### 3.5 `history.html`
The verdict timeline: the gap chart over ALL months (not the front page's 7), each month's
headline pinned along it with a leader line; under it, one expandable row per month
(`<details>`) with the six dimension ratings/directions and the binding constraint. Links to
the appendix for raw scores. Front-page "History" tile and the gap chart's "the gap, this
week" label link here.

## 4. Wiring

Explore band tiles → the five new routes (appendix stays, linked from History). Evidence
panel footer "see everything we have →" → `findings/index.html#<pre-filter>` for the claim's
dimension/entity. Scene "full page →" links → the story permalink (today) and topic anchors.
Breadcrumbs everywhere back to `index.html`.

## 5. Constraints

- Renderer/copy layer only; frozen core, brains, prompts, registry, eval fixtures untouched;
  no run-cycle change (site build already emits pages — these are more pages from the same
  `build_site` call).
- Scripting: the findings filter + panel scripts are self-contained inline `<script>` blocks
  (F95 relaxation extended to Explore pages per §2); no external assets, no fetch.
- Every internal href on every emitted page must resolve to an emitted file — this becomes a
  **link-integrity build gate** (build fails loud, like the story lint).
- Wall-clock isolation (`today` parameter); tests on the fixture store.

## 6. Testing

Per-page render tests (fixture store); lint-clean across every emitted page; the
link-integrity gate's own tests (dead href → build error); pre-filter hash wiring test
(panel footer href carries the claim's dimension/entity); story permalink reuses the scene
renderer (contract: same HTML for the same scene on front page and permalink); site-build
summary reports the new page count.

## 7. Out of scope

Multi-category generalization (the post-F101 roadmap conversation); any Phase B file until
that lane merges; F96/F102; deploy (user sequencing: deploy after B — if C is ready close
behind, one combined deploy is fine, user's call at merge time).
