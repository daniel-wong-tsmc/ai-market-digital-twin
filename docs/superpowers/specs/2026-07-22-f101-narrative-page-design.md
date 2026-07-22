# F101 — Narrative-first category page ("Is supply catching up to demand?")

**Date:** 2026-07-22
**Status:** Spec (brainstormed interactively with the user; all decisions below are interactive user picks unless marked otherwise — zero AFK-defaults)
**Scope:** `chips.merchant-gpu` category page + a new daily narrator pipeline step + evidence/provenance surfaces + Explore layer entry points
**Supersedes:** the F100 deep-dive dashboard as the category page's primary layout (F100 components are salvage donors, see §9)

## 1. Problem

The category page shows a snapshot dashboard while most of what the agent collects daily
(156 findings, 23 entity wiki pages, ~40 scorecards of history, 9 data series, thesis book,
implications) stays invisible. The user's diagnosis, verbatim in spirit: most data is
invisible; what is shown is too dense; there is no sense of change over time; no way to
explore; and above all **there is no obvious tell on whether supply is catching up to
demand — lots of information, but the overall narrative is not being told.**

## 2. The one question

The page exists to answer **"Is supply catching up to demand?"**

- **Glance 1** answers it directly, in plain human words.
- **Glance 2** shows *why*, via one time-based chart where the eye can see the gap
  opening or closing.
- **Scrolling** unfolds the why step by step, New York Times graphics-desk style, every
  claim backed by evidence we collected and/or outside coverage.
- The scroll section answers exactly one thing: **"Why not — and what would change the
  answer?"**

## 3. Page structure (top to bottom, all locked)

### 3.1 Headline verdict
News-headline voice (user picked "verdict statement" over "question & answer"):
a large headline, e.g. *"The GPU shortage got worse this week."*, a one-line deck giving
the why, and a dateline ("Tuesday, July 22, 2026 · updated daily"). Pins on scroll,
condensing to one line. **Language rule (hard):** no analyst/AI vocabulary anywhere in
page prose — banned: momentum, strengthening, tightening (outside direct quotes),
accelerating, DMI, SMI, allocation, index (except one small axis label). Write like a
newspaper graphics desk. Existing stop-slop conventions apply.

### 3.2 The gap chart (the centerpiece, directly under the headline)
- X = time (monthly ticks, trailing ~6–7 months). Y = plain-words label
  ("orders vs. chips shipped, indexed").
- Two lines: demand (warm/terracotta) and supply (cool/teal).
- **The gap between the lines is the graphic:** shaded amber/red, stronger shade for the
  most recent period, bold label ("the gap, this week"), dashed "now" line.
- 2–3 on-chart callouts with leader lines naming what moved ("Jun: memory makers cut
  back"), each openable (§5).
- NYT-style source line under the chart ("Source: …").
- Data: derived from stored scorecard history (demand/supply dimension trajectory) +
  series. Exact derivation is a plan-time decision; the chart must be reproducible from
  committed store data.

### 3.3 KPI band (under the chart — user-directed order: chart above KPIs)
- **One anchored gauge** (never changes): "What a GPU rents for" from the
  `gpuRentalOnDemand` series, marked with a pin ("always shown — the market's price of
  scarcity"). Rationale: the market-clearing rental price is the purest thermometer of
  the gap, and it is real monthly data we already collect (user: "remember we have data
  such as GPU leasing price to utilize").
- **Story-picked gauges — one per scene** (so 2–5, matching the day's scene count;
  four on a typical day): chosen daily by the narrator (user picked dynamic over
  fixed), each carrying a colored scene dot (①…) linking it to the scroll story, a
  plain-words label, value + arrow + tiny sparkline, and a micro-caption saying why it is
  here today.
- Band caption: "picked by today's story · tap any number to ask: says who?"
- Candidate pool = the 9 tracked series + scorecard/agenda indicators (wait time, buyer
  capex direction, ODM shipments, HBM capex, token economics, packaging spread, spot
  price, rental 1-yr, …).

### 3.4 The story, step by step (the scroll section)
Daily narrator-written walk-through: scenes on a vertical progress rail, colored dots
matching the KPI band.

Each scene = number dot + one-line title + 2–3 short plain paragraphs + **its own inline
chart/visual** + **NYT-style "Source:" line under the visual** + **a "Related coverage"
row** (2–3 outside articles on the same topic from the day's gathered corpus: outlet,
title fragment, date, outbound link) + dotted-underline evidence links (ⓘ) in prose that
open the evidence panel.

**Editorial rules (baked into the narrator prompt):**
1. The section answers only: *why isn't supply catching up, and what would change that.*
2. A scene that doesn't change the reader's understanding of the gap doesn't run.
   Interesting-but-irrelevant findings go to Explore, not the story.
3. Scene count flexes with the day (quiet day = maybe 2 scenes; loud day = maybe 5).
4. The last scene is always forward-looking: what would close the gap + what we're
   watching (with small gauges).
5. Every claim must be backed by named findings; every chart carries a source line.

### 3.5 Closing strip: the arc
"Tomorrow's entry will update this story." + chips for previous days' entries
("Jul 21 · Spot flat, rentals ease →") + "story archive →" link to the narrative archive.

### 3.6 Explore band
Four tiles exposing the deep layer: **Entities (23)** — "companies and players, each with
its own page"; **Findings (156)** — "every piece of evidence we've collected";
**Series (9)** — "the raw numbers over time"; **History (40)** — "how our answer has
changed". These sub-pages get their own smaller design pass at plan time; the category
page is the star of this spec.

### 3.7 Footer
"Built by an autonomous research agent · evidence-linked · revision N".

## 4. The daily narrator (the one new pipeline piece)

A new run-cycle step (after implication, before site build) where a tool-less brain
writes the day's story as **structured scenes**, stored as a dated artifact (like
findings are), e.g. `store/<category>/story/YYYY-MM-DD.json`:

- headline + deck + dateline
- scenes[]: title, paragraphs, scene visual spec (which series/chart + annotations),
  claim→finding-id links, source line, related-coverage doc references
- kpiPicks[]: 4 indicator ids + one-line "why it's here today" captions
- chart callouts for the gap chart

The renderer consumes this artifact; **the narrator never changes scores, findings, or
theses** — it reads what the cycle produced and writes prose + selection. Deterministic
gates validate the artifact (schema, finding-id existence, banned-word lint, scene-count
bounds, per-scene source-line presence).

**Gating:** a new brain prompt means the F6 prompt-pin gate fires by design → eval-driver
gate by the book. A new run-cycle step means the F83 fingerprint + `EXPECTED_STEPS`
lockstep re-record. Both handled as their own plan tasks, per standing rules.

## 5. "Says who?" — provenance surfaces (locked: slide-in evidence panel)

- **Hover** (new, user-added at final validation): hovering any KPI chip or marked chart
  element shows a tooltip with the fuller plain-English description — what the number
  measures, where it comes from at a glance, latest move. Static, no fetch.
- **Click** opens the slide-in evidence panel (right side, extends the proven F100 panel
  pattern): title restating the claim ("Servers shipped: +69% — says who?"), a
  **why-chain stepper**: the claim → the evidence we collected (finding rows: source
  name, date, one-line takeaway) → the original sources (outbound links ↗), a mini chart
  of the affected series, and a footer link into Explore ("all 156 findings →").
- On touch devices, tap goes straight to the panel.
- Every chart callout, KPI chip, and in-prose evidence link is panel-openable. The F100
  `encodeURI` href-escaping regression test carries over to all new panel links.

## 6. Interaction/scripting scope

The category page keeps the F100 precedent: self-contained inline `<script>` on the
category page only (scoped relaxation of F95 no-scripting, already user-approved for
F100; this design extends it to: pinned condensing header, hover tooltips, slide-in
panel, KPI↔scene dot linkage, progress rail). No external JS, no fetch at runtime —
everything server-rendered into the page. Mobile: single column; rail and band stack;
hover degrades to tap-panel.

## 7. Visual language

Light editorial: white page, dark text; terracotta = demand/warm, teal = supply/cool,
amber/red = the gap; scene accents cycle ① amber ② terracotta ③ teal ④ green (⑤ repeats). Headline
serif-feel, generous whitespace. Charts clean, small-multiples-plain, every chart with a
source line. (Dataviz skill to be consulted at build time.)

## 8. What this does NOT touch

- Frozen core: `scoring.py`, `report.py`, existing brains' judgment prompts, eval
  fixtures, existing `registry/indicators.json` entries — untouched.
- Scoring v1 replay pin and existing scorecard artifacts — untouched.
- The narrator is additive; site renderer changes are copy/renderer-layer.
- F6/F83 gates are gone *through*, never around (§4).

## 9. Relationship to F100

The F100 deep-dive dashboard ships out of the index slot. Salvage donors: the slide-in
panel mechanism (§5), the six-dimensions data model, appendix `#dim-` anchors (story
"full page →" links may reuse them), the KPI card plumbing (`deepdive_model`) for the
new band. Whether the old dashboard survives as a sub-page under Explore/History is a
plan-time decision (default: no — avoid two competing entry pages).

## 10. Phasing (build reality: several lanes, not one branch)

1. **Phase A — renderer skeleton on existing data** (no pipeline change, no F6): new
   page layout with an assembled-from-existing-data stand-in story (scorecard deltas +
   implications), gap chart, KPI band with static picks, panel + tooltips, archive strip,
   Explore tiles linking to existing appendix/wiki output.
2. **Phase B — the narrator** (gated lane: F6 eval gate + F83 step add): structured
   story artifact + gates; renderer switches from stand-in to narrator output; dynamic
   KPI picks; related-coverage rows.
3. **Phase C — Explore sub-pages + story archive** (renderer-only): entity pages on
   site, findings browser, series charts, history page, dated story archive pages.
Each phase is its own spec-plan-build lane with the standing question-stop rule.

## 11. Success criteria

1. A first-time reader answers "is supply catching up?" within one glance at the top,
   and "why?" within one more (the chart), without encountering analyst vocabulary.
2. Every number, callout, and KPI on the page can answer "says who?" via hover (short)
   and click (full chain to original sources).
3. The daily story reads as a story (scenes, arc, forward-looking close), is fully
   evidence-linked, and its archive accumulates browsable daily entries.
4. The KPI band always shows the anchored rent gauge + the day's four story-picked
   gauges with working scene links.
5. All existing suite gates green; F6/F83 crossed only via their own gated tasks.

## 12. Decision provenance (all interactive user picks this session)

| Decision | Pick |
|---|---|
| Pain points | all four offered + "no obvious supply/demand tell; narrative not told" |
| Reader mode | all three as layers (verdict / narrative / archive) |
| Verdict form | direction+speed → later reworked to plain-words news headline after user rejected jargon tiles |
| Narrative source | new daily narrator step; UI must reflect the day's story |
| Base layout | story spine (B), + consistent KPI element from split-stage (C) |
| KPI placement | scene-synced concept chosen over sticky band (A) for narrative primacy; overview kept pinned at top |
| Top rework | "one glance: is supply catching up" + time-axis chart + why; no AI jargon ("strengthening/tightening" rejected) |
| Opening voice | B — verdict statement (news headline) |
| KPI band shape | dynamic, day's-story-picked; leasing-price data utilized → anchored rent gauge + 4 picks |
| Order | chart above KPI band |
| Provenance | slide-in evidence panel; every label must answer "says who / what happened / which servers / where from" |
| Scroll story | NYT graphics style; charts + data source lines + related news articles; approved with editorial "one question" rule |
| Final addition | hover tooltips for detailed descriptions on KPIs/marked elements |

Mockups from the session (gitignored, retained): `.superpowers/brainstorm/66-1784722017/content/*.html`
(layout, layout-v2, concept-c-detail, top-redesign, top-assembled, provenance, scroll-story, final-page).
