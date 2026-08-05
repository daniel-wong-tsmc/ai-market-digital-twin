# Dashboard Revamp — Executive React/Astryx Rebuild (F110)

Date: 2026-08-05. All decisions below were interactive user decisions made in-session — ZERO AFK-defaults.

## 1. Problem and goal

The live category page (the F101/F103 story page) "tells a lot and nothing at the same time."
An executive cannot get the answer in 10 seconds. Goal: a verdict-led dashboard the executive
reads top-to-bottom in under a minute, with every deeper "why" one click away and every
statement traceable to its original online source.

## 2. Decisions and provenance (all user-approved, interactive)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Astryx role | **Full React rebuild** of the main category page using Meta's Astryx design system (React 19). Overrides the F95 no-scripting convention **for this page only** — user-approved 2026-08-05. |
| 2 | Scope | **Main dashboard page first.** Front page and deep pages (findings/series/history/story archive/entities) stay on the existing Python renderer, linked from the new page. |
| 3 | 10-second takeaway | **Verdict + so-what** leads; numbers support, never lead. |
| 4 | Daily story | **Condensed to 3 bullets** ("What changed"); full prose one click away. |
| 5 | Interactivity | **Click-to-explain** — one pattern everywhere: any number/light/chart opens a plain-English "why" panel with evidence. No tabs/filters/toggles in v1. |
| 6 | Build timing | **Build once, data daily.** React app compiled only on code changes, compiled output committed. Daily cycle stays pure Python and writes one JSON data file. Node is never in the scheduled-run path. |
| 7 | Per-bullet charts | Each daily bullet gets a small supporting chart from real online data. Source: **curated series library first, findings-history fallback, honest "no chart" panel when nothing defensible fits.** |
| 8 | Source references | **Every statement and every chart links back to its original online source** (see §6). |
| 9 | Visual contract | The approved mock at `docs/superpowers/specs/assets/2026-08-05-dashboard-mock.html` (built with the hallmark + dataviz skills, Astryx-neutral tokens, real 2026-08-05 data). The build matches its type scale, tokens, palette, chart forms, and tone. |

Agent-recommended, folded in after user approval of the mock: per-series **quality labels**
(§5) — the mock showed a curated composite series that would have read as hard fact when
drawn small; series must declare what they may honestly evidence.

## 3. The page (five zones, per the mock)

1. **Verdict** — the question in small type; the answer as the biggest text on the page;
   direction chip (stating the narrow truth, e.g. "Gap narrowing"), date, confidence;
   one "so what" line. Derived from existing scorecard + narrator artifacts.
2. **Gap chart** — demand-vs-supply lines with the gap shaded; one shared scale; annotation
   on the widest gap; hover readout; "Show the numbers" table for accessibility.
   Chart timeline uses real per-reading dates; backfilled runs are excluded (mock precedent).
3. **What changed** — three dated plain-English bullets condensed from the day's story +
   "read the full story →" link. Each bullet carries a mini-chart (or the dashed
   "no chart — nothing honest to draw" panel). Mini-charts inherit the demand/supply
   color semantics.
4. **Six dimensions** — plain-English renamed rows, status word next to the colored dot
   (color never the only signal), click-to-explain slide panel: reasoning left;
   direction/confidence/evidence right.
5. **Footer** — links to the existing deep pages.

Prose rules: executive plain English throughout; DMI/SMI never appear as acronyms;
stop-slop applies to all copy.

## 4. Architecture

- **`web/` React app**: Vite + React 19 + `@astryxdesign/core` + theme customized to the
  mock's tokens. Compiled output committed under `site/chips.merchant-gpu/` (replaces
  `index.html`; deep-page directories untouched). Cloudflare serves it statically.
- **JSON exporter** (`gpu_agent/dashboard/export_json.py` or similar): a deterministic
  transform of existing artifacts (scorecard, narrator story, series, audit) into one
  `site/chips.merchant-gpu/data/dashboard.json` — verdict, chart points, bullets with
  chart payloads + captions + sources, dimension rows with resolved source URLs.
  Runs as part of the daily cycle's site-build step. **No new AI prompts anywhere.**
- **Series library**: new `registry/chart-series.json` — per series: id, plain-English
  name, online source (named + URL pattern), fetch cadence (quarterly series fire only
  around earnings dates via the manifest's `earningsDates`), topic tags, and a
  **quality label** (`hard-fact` | `estimate`); `estimate` series never render as
  mini-charts. Fetchers live in `gpu_agent/chartdata/`, write `store/series/*.jsonl`,
  and record per-point source URL + retrieval date.
- **Bullet→chart matcher**: deterministic Python at export time. Topic tag → curated
  series; no fit → findings-history chart if dense enough (threshold set in the plan);
  else the no-chart panel. Never a forced fit.

## 5. Data flow

Daily cycle (unchanged Python) → artifacts in `store/` → fetch step updates due series →
exporter writes `dashboard.json` → commit + push → Cloudflare redeploys → the compiled
React app fetches `data/dashboard.json` at page load.

## 6. Source references ("where's this from?")

- Universal pattern: every statement — verdict, bullets, dimension reasoning, evidence
  lines — carries a small source marker; clicking shows title, outlet, date, and a link
  to the original online source.
- The scorecard stores evidence IDs, not URLs: the exporter resolves every ID to its
  original URL from the document store. This is required work, not optional.
- Charts: caption-level source link per chart; per-point source URL + retrieval date
  stored in the series files.
- Synthesis sentences (the system's own judgment) are labeled "our assessment, based
  on:" with links to each underlying source — never a fabricated single citation.

## 7. Rule changes, pins, and guardrails

- **F95 no-scripting**: overridden by the user for this page only (2026-08-05). The deep
  pages keep the old rule.
- **F83 run-cycle conformance**: adding the fetch + export steps re-records the
  fingerprint in-lane from `EXPECTED_STEPS` (F109 precedent). Expected, not a red pin.
- **Must not touch**: `gpu_agent/scoring.py`, `report.py`, all brain prompts,
  `gpu_agent/evals/`, `fixtures/evals/`, `fixtures/narrator/`,
  `registry/indicators.json`, `registry/series-indicators.json`,
  `registry/freshness.json`. `registry/chart-series.json` is a NEW file and allowed.
  F6 / narrator / scoring-v1-replay pins must stay green and unmoved.
- Fetcher failures can never block the daily cycle (stale-marking only).

## 8. Error handling

- `dashboard.json` missing/stale → the app renders the last good payload with a visible
  "as of <date>" notice.
- Stale series → chart dims with a dated caption; past shelf life → no-chart panel.
- JavaScript disabled → `<noscript>` plain-text verdict summary + link.

## 9. Testing

- Python: exporter golden tests; matcher tests; fetcher parsing tests against saved
  sample pages (tests never hit the network). Existing suite stays green; pytest never
  needs Node.
- JS: component tests (vitest + Testing Library); a shared JSON Schema for
  `dashboard.json` validated on both sides — shape drift fails tests, not the live page.
- Merge gate: full suite green; all four pins green; forbidden diff (§7) empty.

## 10. Out of scope (v1)

Front page + deep-page migration to React; tabs/filters/chart toggles; any brain/prompt
work; judge-side or narrator-side changes; multi-category generalization (design the JSON
per-category so it generalizes, build only chips.merchant-gpu).

## 11. Live criteria (post-merge, not forced in-lane)

1. The next scheduled cycle writes `dashboard.json` with zero manual steps and the live
   page renders it.
2. At least one daily bullet renders a curated-series mini-chart with a working source
   link; a bullet with no defensible series renders the honest no-chart panel.
3. Every visible statement on the live page resolves to a working source reference.
