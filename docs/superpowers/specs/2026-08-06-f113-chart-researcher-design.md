# F113 — Same-Day Chart Researcher + Dashboard Render Fixes

Date: 2026-08-06. All decisions interactive user decisions (screenshot review session) — ZERO
AFK-defaults. Follow-up to F110 (spec 2026-08-05).

## 1. Problem

The F110 matcher is passive: it draws a chart only when a pre-curated series fits the day's
bullet. On 2026-08-06 all three bullets rendered "No chart" panels — the library will miss on
most news days, and three dashed boxes in a row read as "the product is broken." The user wants
charts that RELATE to each bullet's story (e.g. MediaTek demand over time, memory supply vs
demand), which requires actively digging external sources at cycle time.

## 2. User decisions (interactive, 2026-08-06)

1. **Add a chart researcher** — a new daily step digs external sources for a relevant PUBLISHED
   series when no curated series fits a bullet.
2. **Quarantine + verify** — researched series NEVER enter the curated registry
   (`registry/chart-series.json` stays purely human-curated; promotion is a human edit).
   They live in a separate store and render only after a deterministic verification pass.
   Rendered researched charts are labeled "found today — single source".

## 3. The researcher step

- Runs in the daily cycle AFTER the narrator (bullet topics known), BEFORE `dashboard-json`.
- For each bullet with no curated match: a tool-USING research agent (WebSearch/WebFetch/
  agent-reach; same dispatch pattern as gather, NOT the tool-less brains) hunts for a published
  numeric series that directly supports or contextualizes the bullet. Prompt rules: published
  numbers only; every point needs the URL it came from; ≥ 3 points or a clearly-labeled
  comparison (e.g. supply vs demand pair); no estimates presented as fact; give up honestly.
- Output: candidate file in `work/<cycle>/chart-research/<bullet-n>.json`:
  `{seriesName, unit, form, points: [{label, value, sourceUrl, publishedAt}], sourceName, notes}`.
- The researcher prompt is a NEW file (`gpu_agent/chartdata/research_prompt.py`), not pinned —
  its quality mechanism is the verifier below, mirroring the narrator gate philosophy.
  It must NOT modify any existing pinned prompt.

## 4. The verifier (deterministic, the trust gate)

- `gpu_agent/chartdata/verify.py`: for every candidate point, fetch its `sourceUrl` and confirm
  the value appears in the page text (rounding tolerance rules reused from the F66 citation
  audit's number-matching). Any point that fails → the whole candidate FAILS (no partial charts).
- Passing candidates are written to the quarantine store:
  `store/<cat>/research-series/<date>-<slug>.json` (append-only, committed with the cycle).
- Failing or absent candidates → the bullet renders the quiet no-chart line (§6). The verifier
  never blocks the cycle; failures are logged in the cycle journal.
- The exporter (`export_json.py`) prefers: curated match → verified researched series (with
  `"researched": true` in the chart payload) → findings fallback → no chart.

## 5. Registry promotion (human-only)

A researched series that keeps proving useful is promoted by a HUMAN edit to
`registry/chart-series.json` (+ a fetcher if recurring). The cycle journal lists each day's
verified researched series so promotion candidates are visible. No automatic promotion, ever.

## 6. Render fixes riding in this lane (same surface, web/src)

1. **Chartless bullets go full-width**: text spans the row; the reason becomes one quiet grey
   line ("No published number behind this yet."). The dashed panel is reserved for the mixed
   state (some bullets charted, this one deliberately not) where the omission carries meaning.
2. **No-chart copy varies by cause** (no published number / our-own-estimate / nothing dense
   enough) — never the same sentence twice on one page.
3. **Source badges render inline at the end of the sentence** (superscript, footnote-style),
   never floating mid-paragraph or below the line.
4. **Researched-chart label**: caption prefix "Found today — single source:" + source link.

## 7. Schema change

`dashboard.schema.json` bullet.chart gains optional `"researched": bool` (default false) and
`noChartReason` becomes `{reason: str, cause: "no-published-number"|"estimate-only"|"too-sparse"}`.
Schema version bumps to 1.1; the web contract test updates in lockstep.

## 8. Guardrails

- MUST NOT TOUCH: all pinned prompts, `gpu_agent/evals/`, `fixtures/evals/`, `fixtures/narrator/`,
  `gpu_agent/scoring.py`, `report.py`, `registry/indicators.json`, `series-indicators.json`,
  `freshness.json`. Curated `registry/chart-series.json` gains NO automatic writers.
- F83 re-record in-lane for the new `chart-research` step (F109 precedent) — the only pin touch.
- Researcher/verifier failures can never block the cycle or strand a scorecard.
- Verifier tests run against saved fixture pages; tests never hit the network.
- Headless-cost note: researcher dispatches only for chartless bullets (max 3/day).

## 9. Sequencing

Build AFTER F114 merges (both touch `gpu_agent/dashboard/bullets.py`/exporter and web bullet
components; F114 is the exclusive prompt-affecting lane and is smaller).

## 10. Live criteria (post-merge, not forced)

1. A live cycle where a bullet with no curated match renders a verified researched chart with
   the "found today" label and working per-point source URLs.
2. A candidate that fails verification renders the quiet no-chart line and appears in the
   journal as rejected — no partial chart.
3. `registry/chart-series.json` untouched by any live cycle.
