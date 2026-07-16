# Executive Brief format — design spec

**Date:** 2026-07-16 (v3 — per-block information + visual treatment added; v2 restructured around the page outline; v1 section-prose. All user-directed.)
**Status:** APPROVED design direction (user-selected anchor + spec-only deliverable, interactive 2026-07-16). Implementation is a future lane.
**Scope:** The output FORMAT for the executive-facing market page (audience: a TSMC executive): the page outline, what each block says (information), how it looks (visual treatment), which store fields feed it, and the writing rules. It does NOT implement the renderer.
**Origin:** User asked for a format that showcases the agent's outputs for a TSMC executive and resolves the issues found in the 2026-07-16 critique of the deployed site (`ai-market-digital-twin.pages.dev/chips.merchant-gpu/`).

## Problem

The deployed page anchors on the daily run. On quiet days it reads "FLAT / no change / no tracked calls" — an empty page — while the store holds far richer material the site never shows: the monthly deep-read scorecard (narrative verdict, six rated dimensions), the thesis book (23 standing calls with conviction, verdicts, and falsifiable triggers), and the F65 "so what for TSMC" implication lines. The page also had wording that reads as broken ("ORANGE because no alert rule fired"), internal shorthand ("+15 more moved"), layperson glosses that condescend to this audience ("internal settings" for parameters), a headline index number with no scale (+0.07), and a ten-day-stale date with no self-awareness.

## Decision (user-selected)

**One page anchored on the monthly deep-read, with a compact dated signal strip.** The monthly read gives the page standing substance; per-check signals contribute a short dated list. (Alternatives considered: fix the daily page in place — rejected, quiet-day emptiness is structural; two separate pages — rejected, two surfaces to maintain.)

## The page outline (normative)

This outline is the spec's backbone. Blocks appear in exactly this order; every block below has a matching subsection defining information, visual treatment, bindings, and fallbacks. Example content shows the real July 2026 data.

```
┌────────────────────────────────────────────────────────────────┐
│ A · MASTHEAD                                                   │
│  AI market › Chips layer › Merchant GPU                        │
│  MERCHANT GPU — EXECUTIVE BRIEF                                │
│  Tracks the merchant AI-GPU market — demand, supply, pricing,  │
│  competition — and what it means one layer down: wafers,       │
│  packaging, memory.                                            │
│  Monthly read: July 2026 (8th revision)                        │
│  Last signal check: 15 Jul 2026        [Attention: elevated]   │
├────────────────────────────────────────────────────────────────┤
│ B · VERDICT                                                    │
│  STRONG / STEADY — demand and vendor margins are running hot;  │
│  the only ceiling is physical supply: high-bandwidth memory,   │
│  sold out through 2027.                                        │
│  <monthly narrative, verbatim — what's hot, where the ceiling  │
│   is, what to watch for relief>                                │
├────────────────────────────────────────────────────────────────┤
│ C · WHAT THIS MEANS FOR TSMC                    (3–5 bullets)  │
│  • Wafer starts — demand far ahead of supply; NVIDIA, AMD,     │
│    AWS and Google all ramping at once          [evidence][call]│
│  • Packaging — HBM has overtaken CoWoS as the binding limit;   │
│    top-3 clients take >85% of advanced packaging output        │
│  • Customer mix — ASIC shipments growing 44.6%/yr vs 16.1%     │
│    for GPUs; weight shifting toward second sources             │
├────────────────────────────────────────────────────────────────┤
│ D · STANDING CALLS                            (7 of 23 shown)  │
│  Call · Lens · Conviction · Verdict · Held · What would        │
│                                          change our mind       │
│  HBM binds supply      supply  high  strengthened ▲  1  "gap   │
│    re-widens above 20% or HBM books clear before 2028"         │
│  NVDA demand durability demand high  strengthened ▲  2  ...    │
│  Vendor-financed        risk   high  strengthened ▲  2  ...    │
│    circularity                                                 │
│  …                                       All 23 calls →        │
├────────────────────────────────────────────────────────────────┤
│ E · LATEST SIGNAL                        (dated, newest first) │
│  15 Jul — <one plain sentence: that check's biggest mover>     │
│  14 Jul — CoWoS shortfall keeps narrowing toward 10%; HBM      │
│           order books now stretch into 2028. (TrendForce)      │
│  06 Jul — Rack component costs inflating 2–3% per week on      │
│           memory and storage scarcity. (BigGo Finance)         │
├────────────────────────────────────────────────────────────────┤
│ F · THE SIX DIMENSIONS                          (2×3 tiles)    │
│  [Momentum        Very strong · improving · high confidence]   │
│  [Unit economics  Strong · steady · high]                      │
│  [Bottleneck      Mixed · improving · high]                    │
│  [Competitive     Mixed · worsening · medium]                  │
│  [Moat            Mixed · worsening · medium]                  │
│  [Strategic risk  Mixed · worsening · high]                    │
│  each tile: one rationale sentence + "how was this rated?"     │
├────────────────────────────────────────────────────────────────┤
│ G · EVIDENCE & METHOD                                (footer)  │
│  86 signals this month · median observed 2 Jul · 2 trace to    │
│  primary sources · full appendix →                             │
│  Built by an autonomous research agent; every claim on this    │
│  page links to its evidence.                                   │
└────────────────────────────────────────────────────────────────┘
 Cross-cutting (not blocks): counterweight rule; register
 contract; every claim links to evidence.
```

## Block specifications

Each block lists: **Information** (what kinds of content it carries), **Visual treatment** (the techniques that carry it), **Bindings** (store fields), and fallbacks. Visual treatments follow the dataviz discipline: form first, color last, status colors reserved and never color-alone.

### A · Masthead — honesty about time
- **Information:** market identity (crumb path through the twin's hierarchy); page name; one-line scope statement (what is tracked and why it matters one layer down: wafers, packaging, memory); currency (monthly-read month + revision number, last-signal-check date); attention level; staleness notice when applicable.
- **Visual treatment:**
  - Crumb in small uppercase muted text (segments become links when sibling pages exist; plain text until then). H1 page title; scope line in muted body text.
  - Date line in small meta text; dates in tabular figures.
  - **Attention chip, top-right:** a pill with icon + word — `Attention: {calm|watch|elevated|critical}` mapping GREEN/YELLOW/ORANGE/RED onto the status palette roles good/warning/serious/critical. Status color never carries meaning alone (icon + word always present) and the status palette appears NOWHERE else on the page (reserved). When the shown level differs from the raw read, chip subtext uses this fixed wording: `steps down after two calm days; today's raw read was {raw}`. The phrase "because no alert rule fired" is banned — it reads as a bug.
  - **Self-aware staleness:** if the last signal check is more than 3 days old, a full-width muted warning strip (warning status color + icon + text) under the date line: `Signal checks paused since {date}` — the reader never discovers staleness on their own.
- **Bindings:** latest `store/chips.merchant-gpu/<YYYY-MM>-v<K>.json` (highest K of newest month) for the monthly read; `store/cycle-log.json` `capturedAt` for the last-check date (fallback: newest dated scorecard). Alert ladder state from the daily page model.

### B · Verdict — lead with the conclusion
- **Information:** the category rating + direction; the binding constraint named in words; the one-sentence reason; the monthly narrative (what's running hot, where the ceiling is, what to watch for relief); counterweight cross-references where triggered.
- **Visual treatment:** hero-text technique, not a chart and not a colored dot — the verdict sentence is the largest text after the H1 (display-size, semibold): `**{rating} / {direction}** — {reason, first sentence}`. The narrative sits under it as body prose at a readable measure (~66 characters per line). No box, no tile: prose lede. Bold is reserved for the rating words; everything in ink tokens, no status color.
- **Bindings:** monthly scorecard `categoryStatus` (rating, direction, reason, constraintLabel), `narrative`.

### C · What this means for TSMC
- **Information:** 3–5 implications, each: the affected TSMC lever (wafer starts, packaging allocation, customer mix, pricing), the market fact driving it, the dimension(s) it comes from, links to the evidence and to the related standing call.
- **Visual treatment:** bulleted list directly after the verdict — the audience anchor. Each bullet opens with the lever phrase in bold, an em-dash, then the fact in plain prose. Dimension tags as tiny uppercase muted text at bullet end; evidence and related-call links as quiet inline links (accent color, the page's only link treatment). No tiles, no color coding — the content is prose and reads as prose.
- **Bindings:** `store/implications/chips.merchant-gpu/<YYYY-MM>.json` → `lines[]` (watchItem, dimensions, findingIds → appendix anchors, thesisIds → block D rows).
- **Fallback:** no implication file for the anchor month → use the newest available, labeled with its month; none at all → omit the block entirely (never render an empty header). Meituan-class signals (competitive threats to the customer base) must never again live only in the appendix.

### D · Standing calls board
- **Information:** per call: title, lens (demand/supply/competitive/risk), conviction, latest verdict, checks held, and **what would change our mind** (the falsifiable trigger, verbatim — the credibility maker: every call states in advance the observable condition that kills it). Board level: how many shown of how many tracked, link to the full book.
- **Visual treatment:** a table — the honest form for >7 enumerable classes; no chart, no per-lens colors. Inside a horizontal-scroll container so the page body never scrolls sideways. Verdict column: glyph + word, never glyph alone (`strengthened ▲` / `weakened ▼` / `reaffirmed ◆`), set in ink — not status colors (a weakening call is information, not an alarm; the attention chip owns alarm). Conviction as plain text (high/medium/low). Lens in small uppercase muted text. Held column right-aligned, tabular figures. Trigger column in smaller muted type, allowed to wrap. Hairline row separators; no zebra striping; row order IS the ranking (registered first, conviction high→low, then streak).
- **Selection:** `status == "registered"` first, ordered by conviction (high > medium > low), then streak descending. Cap 7 rows; below the table: `All {N} calls, including {M} provisional →` linking to the full book page.
- **Bindings:** `store/theses/chips.merchant-gpu/book.json` → `entries[]` (title, lens, conviction, lastVerdict, streak, status, falsifiableTrigger).
- **Cold start** (book empty): render one line — `No standing calls yet; first reads are being established.`

### E · Latest signal (dated strip)
- **Information:** the last ~7 signal checks: date, ONE plain sentence per check (that check's single biggest mover — highest-magnitude fresh finding — as prose), source name. Gaps between dates are self-explanatory; checks that didn't happen simply don't appear. No "no run yet at this horizon" placeholder lines.
- **Visual treatment:** a two-column timeline list, newest first: fixed-width date column (tabular figures, muted ink) beside the sentence in body text, source in muted parentheses at the end. Optional thin vertical rule joining the dates. No arrows, no symbols, no counts of unnamed movers — the strip is prose with dates.
- **Bindings:** one entry per scorecard revision (dated by that revision's newest fresh-finding `capturedAt`), plus dated daily scorecards where they exist; the existing what-changed computation may feed it, but its output must be re-rendered as prose.

### F · The six dimensions
- **Information:** per dimension (momentum, unit economics, bottleneck, competitive structure, moat, strategic risk): rating word, direction word, confidence level, the FIRST sentence of the rationale, any evidence caveat (e.g. confidence capped), and a "how was this rated?" method link. Replaces the old four-tile row (same gap metric twice, scale-less +0.07).
- **Visual treatment:** a KPI row of six **stat tiles** in a 2×3 grid (single column on narrow screens). Tile anatomy, top to bottom: dimension name as small uppercase muted label → the rating WORD as the tile's value (the tile's largest text — a word, deliberately not a number) → direction as word + glyph in meta text (`improving ↑` / `steady →` / `worsening ↓` — word always present) → confidence level in meta text → one rationale sentence in small body text → method link. All ink tokens; NO status colors on tiles — a worsening dimension is information, not an alarm, and repainting tiles red/green would make six alarms compete with the one real chip in the masthead. Hairline borders, consistent radius, whitespace over boxes.
  - **Future option (not v1):** a small sparkline per tile (the stat-tile-with-sparkline form) once ≥6 months of rating history accumulate; any such chart must then go through the full dataviz procedure (form → color → validator → hover → accessibility).
- **Bindings:** monthly scorecard `dimensionRatings.<dim>` (rating, direction, confidence.level, rationale); `dimensionStatus.<dim>` for caveats. Index numbers (DMI/SMI/SDGI, anchors, two-decimal scores) move entirely to the appendix — words carry the page; the appendix keeps the arithmetic.

### G · Evidence & method footer
- **Information:** evidence framing (signal count, median observation date, oldest date, primary-source count) linking to the full appendix (every finding, statement, source, observation date, primary/secondary tag — existing appendix content, kept); one method line (built by an autonomous research agent; every claim links to its evidence; method pages explain each rating).
- **Visual treatment:** a footer strip above a hairline rule: one muted meta-text line with interpunct separators — `{n} signals this check · median observation {date} · oldest {date} · {p} trace to primary sources · full appendix →`. The appendix link is the line's only accent-colored element. Method line beneath in the same muted register. Deliberately quiet: the footer certifies, it doesn't perform.
- **Bindings:** monthly/daily scorecard `sources`, findings' `observedAt`, existing trust computation.

## Visual system (cross-cutting)

- **Type scale, five steps:** page title (H1) → hero verdict → block headers → body → meta/muted. One sans family (system stack is fine). Body at 16px/1.5; narrative prose capped near a 66-character measure.
- **Color discipline:** near-black ink on white; one accent hue for links only; muted gray for meta; hairline gray for rules and borders. The **status palette (good/warning/serious/critical) appears exactly twice at most**: the attention chip and the staleness strip — always icon + word, never color alone, never reused for anything else. Direction and verdict glyphs stay in ink. Text always wears text tokens, never a status or accent color.
- **Numbers:** tabular figures in table columns and the date columns; proportional figures everywhere else. Every number keeps its unit; scale anchors where the scale isn't self-evident.
- **Layout:** single column, whitespace over boxes; the only bordered containers are the six tiles and the calls table. Tables and any future wide content scroll inside their own `overflow-x` container — the page body never scrolls horizontally.
- **Responsive:** tiles 2×3 → 1 column; calls table scrolls; masthead chip wraps under the title on narrow screens.
- **Print/PDF:** executives forward PDFs — the page must print clean in grayscale: chip meaning survives via icon + word; hairlines and ink survive; no page break inside a tile or table row.
- **Charts:** none on v1 of the page. The only sanctioned future chart forms are the per-tile sparkline (F) and a single trend line in the appendix; each must follow the full dataviz procedure (form → color-by-job → palette validator → hover layer → accessibility pass) when introduced.
- **Dark mode:** out of scope for v1 (light-only, print-first). If added later, dark steps are selected and validated, not auto-flipped.

## Cross-cutting rules (apply across blocks)

### Counterweight rule — show both sides on purpose
Wherever a block cites a positive whose evidence also feeds a risk-lens thesis (test: intersection of the cited findingIds with any risk thesis's evidence, or implication `thesisIds` containing a risk-lens entry), render an inline one-line cross-reference to that standing risk call. Canonical case: Nvidia vendor-financing cited as a demand positive (B or C) cross-references the `vendor-financed demand circularity` call in D. The same fact must never read as strength on the main page and as risk only in the appendix; surfaced side by side it becomes evidence the system doesn't cheerlead.

### Writing register (contract for renderer copy and the plain-language stage)
1. Industry vocabulary used straight, no glosses: HBM, CoWoS, ASIC, hyperscaler, parameters, gross margin, take-or-pay, lead time, wafer starts. The audience is a semiconductor executive; "1.6 trillion internal settings" style glosses are banned in exec copy ("parameters" is the word).
2. Banned tokens in exec copy: `+N more moved`; bare direction symbols (↓ + →) outside the calls-board verdict glyphs and tile direction cues (which always carry the word too); the word "run" (use "signal check" or "revision"); "because no alert rule fired"; internal feature codenames (F65 etc.).
3. Every number carries its unit and, where the scale is not self-evident, an anchor ("narrowing from ~20% toward 10%"). Two-decimal composite indices never appear on the main page.
4. Every claim either links to its evidence anchor or names its source inline.
5. Sentences, not fragments; one idea per sentence; no marketing adjectives.

## Critique-issue → resolution map

| # | Critique finding (2026-07-16) | Resolved by |
|---|---|---|
| 1 | Page ten days stale, silently | A: dual date + self-aware staleness strip |
| 2 | "ORANGE because no alert rule fired" reads as a bug | A: attention chip, fixed wording; phrase banned |
| 3 | "No tracked calls this run" — flagship section empty; all-FLAT page | B verdict anchor + D standing calls board |
| 4 | Most TSMC-relevant signal buried in appendix | C directly after the verdict |
| 5 | Demand positive contradicts appendix circularity risk | Counterweight rule |
| 6 | Cryptic shorthand, mixed symbols, "+15 more moved" | E prose-only strip + register rules |
| 7 | Scale-less +0.07 headline; duplicated gap tiles | F six dimensions; indices to appendix |
| 8 | Thin sourcing shown without framing | G framed evidence line (kept honest, now contextualized) |
| 9 | Crumb not clickable; no way to explore the twin | A crumb becomes links as sibling pages ship |
| 10 | Layperson glosses condescend to this audience | Register rule 1 |

Launch-checklist items from the critique that are real but OUTSIDE a format spec: custom domain, favicon, link-preview (Open Graph) tags, and re-running a fresh cycle before any executive viewing. Listed here so they are not lost; owned by the deploy checklist, not the renderer.

## Interactions and constraints

- **F79 scoring v2 (SHADOW):** this spec binds to v1 fields. Nothing in it may render v2 or flip the headline — that is the user-signed G4 cutover gate. The format is deliberately word-anchored (ratings, directions, rationales), so the eventual v1→v2 cutover changes bindings, not blocks.
- **Frozen core:** the format is renderer/copy-layer only. An implementation lane must not touch extract/judge/thesis brains; the register rules bind the plain-language/render stage.
- **F95 site:** this format replaces the F95 category-page layout for the exec surface; the daily ops detail (raw tiles, what-changed internals) remains available via appendix/method pages. Whether the old daily page layout is kept as a separate ops view is an implementation-lane decision, not required by this spec.
- **Testability:** register rules 1–3 are string-testable against rendered output (banned-token scan; unit-presence heuristics); D non-emptiness is assertable whenever `book.json` has a registered entry; A's staleness strip is assertable by fixture clock; "status palette only in chip + staleness strip" is assertable by scanning rendered CSS classes. An implementation lane should pin these as renderer tests.

## Acceptance criteria (for the future implementation lane)

1. Rendered page contains blocks A–G in outline order, populated from the real store with no placeholder text.
2. Calls board (D) non-empty whenever the thesis book has ≥1 registered entry.
3. Banned-token scan of rendered exec copy passes (register rule 2 list).
4. Attention chip wording matches the A template in both the aligned and hysteresis-lag cases.
5. Every finding statement rendered on the page carries a working link to its appendix anchor.
6. Status colors appear only in the attention chip and staleness strip, always paired with icon + word.
7. The page body never scrolls horizontally at any viewport width (wide content scrolls in its own container).
8. Existing suite, F6 pin, and F83 conformance untouched (renderer-only change).

## Decision log

- Page anchor = monthly brief + daily strip: **user-selected** (interactive, 2026-07-16) from three presented options.
- Deliverable = spec only, no mockup now: **user-selected** (interactive, 2026-07-16).
- Spec restructured around a normative page outline (blocks A–G): **user-directed** (interactive, 2026-07-16). Two refinements surfaced by the outline: attention chip moved to the masthead top-right (was: verdict block); strip renamed "Latest signal" (was: "This week's signal").
- Per-block Information + Visual treatment and the Visual system section added: **user-directed** (interactive, 2026-07-16). Visual choices follow the dataviz skill discipline; key call: status color is reserved for the attention chip + staleness strip, everything else in ink — one alarm on the page, not eight.
- All other choices (block order, selection rules, register list, counterweight rule): designer judgment within the approved anchor, open to revision at spec review.
