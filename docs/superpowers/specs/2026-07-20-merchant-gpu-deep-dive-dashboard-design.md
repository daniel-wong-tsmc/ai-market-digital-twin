# F100 — Merchant-GPU deep-dive dashboard revamp (design)

**Date:** 2026-07-20
**Status:** DESIGN — awaiting user review, then writing-plans
**Scope:** the `chips.merchant-gpu` category page (`site/chips.merchant-gpu/`) and its
deep-dive surfaces only. Other categories and the market home are out of scope (they can
adopt the pattern later once it is proven here).
**Change class:** renderer / copy layer only. Frozen core (`scoring.py`, `report.py`, the
brains, the eval fixtures, `registry/indicators.json`) is **not touched**; no run-cycle steps
are added, so no F83 fingerprint change; the F6 emitted-prompt pin is unaffected. This is the
same class of work as F97 (exec-brief renderer) and F98 Part A (agenda data-readiness).

## Problem

The live page (`ai-market-digital-twin.pages.dev/chips.merchant-gpu/`, rev 12) reads like a
well-written memo, not a dashboard: a single narrow column of near-monochrome text, no colour
used for meaning, no charts, and — the decisive gap the user named — **no way to ask "why is
this metric the way it is?"** Every number is a dead end that links out to a flat appendix.

## Goals

1. A scannable, modern **dashboard** for the merchant-GPU category, with colour used for
   meaning and real charts driven by existing data.
2. **Every element is a doorway.** Clicking any metric, dimension, or KPI opens its reasoning,
   evidence, trend, and confidence — the "why".
3. Reuse existing data and machinery; add no new gather/scoring/brain surface.

## Non-goals

- No change to how ratings, indices, findings, or calls are *computed*.
- No new indicators, series, or scoring weights.
- No redesign of other category pages or the market home (this revamp proves the pattern on one
  page first).

## The design

### A. Main page (top → bottom)

The main page gets **leaner**, not longer. Sections, in order:

1. **Eyebrow + attention chip** — breadcrumb (`AI Market › Chips › Merchant GPU`) and the
   existing attention-ladder chip (calm / watch / elevated / critical), top-right.
2. **Title + executive brief (chosen: "Option 4").** The rating label (e.g. *Strong /
   improving*) above a **two-sentence** trimmed brief (~45 words), replacing today's ~90-word
   paragraph. The full narrative is not deleted — it is reachable via a "full read →"
   affordance (opens the same deep-dive surface as everything else).
3. **Dynamic KPI cards** — a row of the **five standing executive-question cards** (see §C),
   light style, compact, with a monospace value and a coloured up/down delta. **DMI and SMI are
   intentionally excluded** here because the chart already shows them.
4. **Two-column band:**
   - *Left (wider):* **Demand-vs-supply momentum chart** — a dual line over the scorecard
     revision history: demand momentum (solid) and supply momentum (dashed), with the latest
     point marked. This is the flagship visual.
   - *Right:* **Six dimensions** — the clean labelled list, each row a coloured status dot +
     name + rating + trend arrow, each row clickable.
5. **Latest signal strip** — the dated news strip stays on the main page (kept as-is,
   restyled).

Everything in sections 2–5 that names a metric, dimension, or call is a **click target**
(§B).

### B. Deep dive (chosen: slide-in panel + full-page link)

Clicking any target opens a **slide-in panel** from the right; the dashboard stays visible
behind a scrim. The panel is themed to match the page (light / editorial). Panel contents,
all sourced from the existing scorecard + findings:

- **Header:** eyebrow (what kind of thing this is), title, and status badges (rating /
  direction / confidence).
- **Why it's rated this way:** the plain-language rationale (`dimensionRatings[dim].rationale`
  for dimensions; the finding `why` / statement for metrics).
- **Trend:** a mini line chart of the item over recent scorecard revisions (dimension ratings
  mapped to an ordinal; metrics from their series where one exists).
- **Evidence:** the driving signals (`findingIds` → finding `statement` + source + per-finding
  trend), each linking to the original source URL.
- **Confidence:** the vote spread (`confidence.basis`, `voteSpread`) and whether it is capped.
- **What would change our mind:** the related standing-call trigger, where one exists.
- **What this means for TSMC:** the relevant implication bullet(s) (see §D).
- **"Open full page for this topic →":** a shareable per-topic URL. Built on the existing
  appendix anchors (`appendix.html#dim-<name>`, `#f-<id>`) — i.e. the full page is the
  appendix section for that item, retained and lightly restyled. This gives a durable link
  without leaving the dashboard for routine browsing.

### C. Dynamic KPI cards (reuse the agenda band)

The five cards **are** the existing F97/F98 agenda band (`gpu_agent/dashboard/agenda.py` +
`registry/agenda-slots.json`): five standing executive questions —

1. Is the demand real and growing?
2. What caps shipments today?
3. Where is share moving?
4. Can the buyers keep paying?
5. How much demand is self-financed or policy-capped?

— each of which already **auto-selects the best metric to answer it every cycle**
(freshness × magnitude × evidence grade, with stickiness vs the prior pick). So the "different
each run" behaviour the user asked for **already exists**; this revamp only restyles the band
into the compact card treatment and adds a coloured delta vs the prior revision. No change to
the selection logic.

### D. Folding the lower sections (chosen: fold into deep-dives)

Today's three lower sections change as follows:

- **"What this means for TSMC"** (dimension-tagged bullets) → each bullet moves **into the
  deep-dive panel of the dimension it is tagged with** (e.g. the CoWoS/packaging bullet appears
  in the Bottleneck panel). The mapping already exists via each bullet's dimension tag.
- **"Standing calls"** (conviction table) → each call surfaces **inside the deep-dive of the
  dimension/topic it relates to** (matched by lens), under a "Standing calls" subsection, with
  its trigger feeding the panel's "what would change our mind". The complete calls list is
  retained on the full appendix page.
- **"Latest signal"** (news strip) → **stays on the main page.**

Net effect: the main page is the summary + the news strip; the implications and calls live one
click deep, next to the rating they explain.

## Data sources (all existing — nothing new gathered)

| Element | Source |
|---|---|
| Rating, brief, attention | scorecard `categoryStatus`, `narrative`, `dimensionStatus` |
| KPI cards | agenda band over `findings` + `store/series/*.jsonl` |
| Demand/supply chart | `indices.momentum` / `outlook` + `demandSupply` across scorecard history |
| Six dimensions | `dimensionRatings[*]` (rating, direction, confidence, rationale, findingIds) |
| Deep-dive evidence | `findings[*]` (statement, why, trend, evidence[].url) |
| Calls + triggers | existing thesis/standing-calls store |
| TSMC implications | existing implication bullets (dimension-tagged) |

## Components (modules)

Renderer-layer only. Expected touch points (exact lines pinned in the plan):

- `gpu_agent/dashboard/brief_model.py` / `brief_render.py` — main-page model + HTML.
- `gpu_agent/dashboard/agenda.py` — restyle the band into cards + add prior-revision delta
  (selection logic unchanged).
- **New:** a deep-dive model + renderer (panel content assembled per target) and the panel
  markup/JS; a per-topic full-page (appendix anchors, restyled).
- The category stylesheet (`site/chips.merchant-gpu/style.css` source) — new light dashboard
  theme, charts, panel, cards.
- A small self-contained JS for panel open/close (no external libraries — the site is static,
  self-contained, Cloudflare Pages).

## Governance / safety

- Renderer + copy only. `scoring.py`, `report.py`, brains, eval fixtures, and
  `registry/indicators.json` are **out of bounds** — the plan must state this verbatim per the
  question-stop rule.
- No run-cycle step added → no `EXPECTED_STEPS` / F83 fingerprint change.
- F6 emitted-prompt pin and the scoring v1 replay pin must stay green throughout.
- Output prose is read by a non-technical executive persona → run all new copy through the
  stop-slop skill; no AI/doctrine/internal jargon.
- Build stays a static, self-contained bundle (inline CSS/JS; no CDN) so Cloudflare Pages
  serves it unchanged.

## Testing

- Real-store smoke build (`[site] pages=N`, lint-clean); every deep-dive target resolves to a
  panel with non-empty why/evidence; every "full page" link resolves to a real anchor.
- The renderer model layer keeps its "never raises" contract (missing data degrades to a
  graceful placeholder, never a traceback) — unit tests per the F97 precedent.
- Full suite green at merge (expect 3–4 skips); F6 pin + F83 conformance green.

## Decision provenance (all interactive, this session — zero AFK)

1. Full rebuild + add data visuals (charts). — user
2. Look: light editorial base; **no dark KPI strip** (light cards). — user
3. Brief: **Option 4**, two trimmed sentences. — user
4. Chart: demand-vs-supply dual line (from mockup C). — user
5. Six dimensions: labelled-list treatment (from mockup A). — user
6. KPI cards: compact card treatment (from mockup B), **DMI/SMI excluded**, dynamic per run. — user
7. Deep dive: **slide-in panel + full-page link**. — user
8. Lower sections: **fold "what this means"/calls into deep-dives**; keep latest-signal on the
   main page. — user
9. Scope: **merchant-GPU page + its deep-dives only**. — user

## Open items / risks

- **Concurrent live cycle:** a `2026-07-v13` cycle was mid-run during this design session; this
  spec touched only `docs/`. The build lane must claim a worktree and never sweep `store/`.
- Dimension-rating trend needs an ordinal mapping (e.g. Weak…Very strong → 0…4) to plot; define
  it once in the deep-dive model.
- Full-page-per-topic reuses appendix anchors; if a topic lacks an anchor, the panel omits the
  full-page link rather than dead-linking.
