# Executive Brief format — design spec

**Date:** 2026-07-16
**Status:** APPROVED by user (interactive) — spec only; mockup explicitly declined for now; implementation is a future lane.
**Scope:** The output FORMAT for the executive-facing market page (audience: a TSMC executive). This spec defines what the page says, in what order, bound to which store fields, and the writing rules. It does NOT implement the renderer.
**Origin:** User asked for a format that showcases the agent's outputs for a TSMC executive and resolves the issues found in the 2026-07-16 critique of the deployed site (`ai-market-digital-twin.pages.dev/chips.merchant-gpu/`).

## Problem

The deployed page anchors on the daily run. On quiet days it reads "FLAT / no change / no tracked calls" — an empty page — while the store holds far richer material the site never shows: the monthly deep-read scorecard (narrative verdict, six rated dimensions), the thesis book (23 standing calls with conviction, verdicts, and falsifiable triggers), and the F65 "so what for TSMC" implication lines. The page also had wording that reads as broken ("ORANGE because no alert rule fired"), internal shorthand ("+15 more moved"), layperson glosses that condescend to this audience ("internal settings" for parameters), a headline index number with no scale (+0.07), and a ten-day-stale date with no self-awareness.

## Decision (user-selected)

**One page anchored on the monthly deep-read, with a compact dated daily strip.** The monthly read gives the page standing substance; daily runs contribute a short "this week's signal" list. (Alternatives considered: fix the daily page in place — rejected, quiet-day emptiness is structural; two separate pages — rejected, two surfaces to maintain.)

## Page: "Merchant GPU — Executive Brief"

Sections in order, with data bindings. All bindings are to files that already exist in the store; no new gathering is required.

### 1. Masthead — honesty about time
- Title `MERCHANT GPU — Executive Brief`; crumb `AI market › Chips layer › Merchant GPU` (crumb segments become links when sibling pages exist; plain text until then).
- One-line scope: what this page tracks and why it matters one layer down the supply chain.
- Dual date line: `Monthly read: {month name} {year}, revision {K} · Last signal check: {date of newest daily scorecard or cycle-log entry}`.
- **Self-aware staleness:** if the last signal check is more than 3 days old, the masthead itself says so: `Signal checks paused since {date}` — the page never lets the reader discover staleness on their own.
- Bindings: latest `store/chips.merchant-gpu/<YYYY-MM>-v<K>.json` (highest K of newest month) for the monthly read; newest `<YYYY-MM-DD>-v*.json` and/or `store/cycle-log.json` for the last-check date.

### 2. The verdict — lead with the conclusion
- Category status as a sentence, not a colored dot:
  `**{rating} / {direction}** — {categoryStatus.reason, first sentence}` with the binding constraint named in words (`categoryStatus.constraintLabel`).
- The monthly `narrative` verbatim underneath (it is already exec-grade prose: what's running hot, what the ceiling is, what to watch).
- The alert light survives but demoted to a small labeled chip: `Attention: {calm|watch|elevated|critical}` mapping GREEN/YELLOW/ORANGE/RED. When the shown level differs from the raw read, the chip's subtext uses this fixed wording: `steps down after two calm days; today's raw read was {raw}`. The phrase "because no alert rule fired" is banned — it reads as a bug.
- Bindings: monthly scorecard `categoryStatus`, `narrative`; alert ladder state from the daily page model.

### 3. What this means for TSMC
- 3–5 bullets, each one implication line's `watchItem`, tagged with its dimension(s) and linking to its evidence (findingIds → appendix anchors) and related standing calls (thesisIds → calls board rows).
- Placement: directly after the verdict. This is the audience anchor — the Meituan-class signals (competitive threats to the customer base, wafer/packaging exposure) must never again live only in the appendix.
- Bindings: `store/implications/chips.merchant-gpu/<YYYY-MM>.json` → `lines[]`.
- Fallback: if no implication file exists for the anchor month, use the newest available and label its month; if none exists at all, omit the section entirely (never render an empty header).

### 4. Standing calls board
- Source: the thesis book — NOT "what moved today". The board persists across runs, so it is never empty after cold start.
- Selection: `status == "registered"` entries first, ordered by conviction (high > medium > low), then streak descending. Cap at 7 rows; below the table: `All {N} calls, including {M} provisional →` linking to the full book page.
- Columns: Call (title) · Lens (demand/supply/competitive/risk) · Conviction · Latest verdict (`strengthened ▲` / `weakened ▼` / `reaffirmed ◆` — word plus glyph, never glyph alone) · Streak (`held {n} checks`) · **What would change our mind** (`falsifiableTrigger`, verbatim).
- The falsifiable-trigger column is the credibility maker for this audience: every call states, in advance, the observable condition that kills it.
- Bindings: `store/theses/chips.merchant-gpu/book.json` → `entries[]` (title, lens, conviction, lastVerdict, streak, status, falsifiableTrigger).
- Cold start (book empty): render one line — `No standing calls yet; first reads are being established.`

### 5. This week's signal (daily strip)
- The last ~7 daily runs as a dated list, newest first, ONE plain sentence per day: the day's single biggest mover (highest-magnitude fresh finding), stated as prose with its source named. Example register: `Jul 6 — Rack component costs still inflating 2–3% per week; the packaging gap keeps narrowing. (BigGo Finance)`
- Days without a run simply do not appear; the visible dates make gaps self-explanatory. No "no run yet at this horizon" placeholder lines.
- Banned here: bare arrows/symbols without a legend, counts of unnamed movers ("+15 more moved"), and the word "run" in page copy (say "signal check").
- Bindings: daily scorecards `<YYYY-MM-DD>-v*.json` (findings by magnitude/freshness); the existing what-changed computation may feed it, but its output must be re-rendered as prose.

### 6. The six dimensions
- Replaces the old four-tile row (which showed the same gap metric twice and a scale-less +0.07). Six tiles, one per rated dimension: momentum, unit economics, bottleneck, competitive structure, moat, strategic risk.
- Each tile: rating word · direction word · confidence level · the FIRST sentence of the dimension's `rationale` · a "how?" link to the existing method page.
- Index numbers (DMI/SMI/SDGI, anchors, two-decimal scores) move entirely to the appendix. Words carry the main page; the appendix keeps the arithmetic for anyone who asks.
- Bindings: monthly scorecard `dimensionRatings.<dim>` (rating, direction, confidence.level, rationale), `dimensionStatus.<dim>` for evidence caveats (e.g. confidence capped).

### 7. Counterweight rule — show both sides on purpose
- Wherever the page cites a positive whose evidence also feeds a risk-lens thesis (test: intersection of the cited findingIds with any risk thesis's evidence, or implication `thesisIds` containing a risk-lens entry), render an inline one-line cross-reference to that standing risk call. Canonical case: Nvidia vendor-financing cited as a demand positive cross-references the `vendor-financed demand circularity` call.
- Purpose: the same fact must never read as strength on the main page and as risk only in the appendix — that near-contradiction was critique finding #7; surfaced side by side it becomes evidence the system doesn't cheerlead.

### 8. Evidence & method footer
- One framed line: `{n} signals this check · median observation {date} · oldest {date} · {p} trace to primary sources` linking to the appendix (every finding, its statement, source, observation date, primary/secondary tag — the existing appendix content, kept).
- One method line: built by an autonomous research agent; every claim on the page links to its evidence; method pages explain each rating.
- Bindings: monthly/daily scorecard `sources`, findings' `observedAt`, existing trust computation.

## Writing register (contract for renderer copy and the plain-language stage)

1. Industry vocabulary used straight, no glosses: HBM, CoWoS, ASIC, hyperscaler, parameters, gross margin, take-or-pay, lead time, wafer starts. The audience is a semiconductor executive; "1.6 trillion internal settings" style glosses are banned in exec copy ("parameters" is the word).
2. Banned tokens in exec copy: `+N more moved`; bare direction symbols (↓ + →) outside the calls-board verdict glyphs (which always carry the word too); the word "run" (use "signal check" or "revision"); "because no alert rule fired"; internal feature codenames (F65 etc.).
3. Every number carries its unit and, where the scale is not self-evident, an anchor ("narrowing from ~20% toward 10%"). Two-decimal composite indices never appear on the main page.
4. Every claim either links to its evidence anchor or names its source inline.
5. Sentences, not fragments; one idea per sentence; no marketing adjectives.

## Critique-issue → resolution map

| # | Critique finding (2026-07-16) | Resolved by |
|---|---|---|
| 1 | Page ten days stale, silently | §1 dual date + self-aware staleness line |
| 2 | "ORANGE because no alert rule fired" reads as a bug | §2 attention chip, fixed wording; phrase banned |
| 3 | "No tracked calls this run" — flagship section empty; all-FLAT page | Monthly anchor (§2) + standing calls board (§4) |
| 4 | Most TSMC-relevant signal buried in appendix | §3 TSMC implications directly after the verdict |
| 5 | Demand positive contradicts appendix circularity risk | §7 counterweight rule |
| 6 | Cryptic shorthand, mixed symbols, "+15 more moved" | §5 prose-only strip + register rules |
| 7 | Scale-less +0.07 headline; duplicated gap tiles | §6 six dimensions; indices to appendix |
| 8 | Thin sourcing shown without framing | §8 framed evidence line (kept honest, now contextualized) |
| 9 | Crumb not clickable; no way to explore the twin | §1 crumb becomes links as sibling pages ship |
| 10 | Layperson glosses condescend to this audience | Register rule 1 |

Launch-checklist items from the critique that are real but OUTSIDE a format spec: custom domain, favicon, link-preview (Open Graph) tags, and re-running a fresh cycle before any executive viewing. Listed here so they are not lost; owned by the deploy checklist, not the renderer.

## Interactions and constraints

- **F79 scoring v2 (SHADOW):** this spec binds to v1 fields. Nothing in it may render v2 or flip the headline — that is the user-signed G4 cutover gate. The format is deliberately word-anchored (ratings, directions, rationales), so the eventual v1→v2 cutover changes bindings, not sections.
- **Frozen core:** the format is renderer/copy-layer only. An implementation lane must not touch extract/judge/thesis brains; the register rules bind the plain-language/render stage.
- **F95 site:** this format replaces the F95 category-page layout for the exec surface; the daily ops detail (raw tiles, what-changed internals) remains available via appendix/method pages. Whether the old daily page layout is kept as a separate ops view is an implementation-lane decision, not required by this spec.
- **Testability:** register rules 1–3 are string-testable against rendered output (banned-token scan; unit-presence heuristics); §4 non-emptiness is assertable whenever `book.json` has a registered entry; §1 staleness line is assertable by fixture clock. An implementation lane should pin these as renderer tests.

## Acceptance criteria (for the future implementation lane)

1. Rendered page contains sections §1–§8 in order, populated from the real store with no placeholder text.
2. Calls board non-empty whenever the thesis book has ≥1 registered entry.
3. Banned-token scan of rendered exec copy passes (register rule 2 list).
4. Attention chip wording matches the §2 template in both the aligned and hysteresis-lag cases.
5. Every finding statement rendered on the page carries a working link to its appendix anchor.
6. Existing suite, F6 pin, and F83 conformance untouched (renderer-only change).

## Decision log

- Page anchor = monthly brief + daily strip: **user-selected** (interactive, 2026-07-16) from three presented options.
- Deliverable = spec only, no mockup now: **user-selected** (interactive, 2026-07-16).
- All other choices in this spec (section order, selection rules, register list, counterweight rule): designer judgment within the approved anchor, open to revision at spec review.
