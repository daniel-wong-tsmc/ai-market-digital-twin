# F98 Part A — Agenda-band data-readiness + unit hygiene — design spec

**Date:** 2026-07-17
**Status:** Design APPROVED by user (interactive, 2026-07-17); spec awaiting user review.
**Scope:** F98 **Part A only** (backlog `docs/fix-backlog.md` F98). Renderer/config/local-data work: make the three tracked-but-unslotted merchant-gpu indicators data-ready, fix agenda slot placements, and fix the visible unit/format bugs on the live Executive Brief. **Part B (S4 upstream lead-time adoption, F6-gated) is explicitly out of scope** and stays a separate lane.
**Origin:** 2026-07-17 SDEWS cross-reference session (built on `docs/2026-07-11-sdews-metric-extraction.md`, whose lane calls stand). Parent surface: the F97 Executive Brief (spec `2026-07-16-executive-brief-format-design.md` v5).

## Decision provenance (all interactive, zero AFK-defaults)

1. **Part A scope = full data-readiness for all three indicators** (gpuSpotPrice, apiArr, releaseCadence) — user-selected over config-only and gpuSpotPrice-only options.
2. **Data sources = existing gather pipeline for apiArr/releaseCadence; the local `gpu_agent/data/gpu_leasing_data/` folder for prices** — user-directed ("I have it in a data folder").
3. **Price tile tracks the LATEST-generation accelerator benchmark, dynamic across modalities** (hardware street price, on-demand, spot, 1-year term), rolling forward as platforms ship, with changes shown — user-directed (supersedes the assistant's H100-benchmark recommendation).
4. **The data folder is auto-refreshed** by the user's collector — per-cycle re-derivation is safe; staleness still handled defensively.

## What exists (verified 2026-07-17)

- `gpu_agent/pricefeed.py` already reads the folder: `_aws_points/_oracle_points/_gcp_points/_coreweave_points`, `load_points`, `headline_prices`, `price_delta`, `lookback_label`, freshness guard. AWS files carry a `term` column (`1 year`, on-demand) and spot files exist — term/modality data is real.
- Hardware-price files are NOT yet read: `thinkmate_gpu_price.csv` (34 card rows × daily cols 2025-02→2026-07-08, wide format `gpu,YYMMDD,...`), `serversimply_gpu_price.csv` (15 platform rows incl. `(EOL)` aging-market entries, HGX B200 8-GPU, MI350X/MI355X). Known warts: duplicate model rows; at least one broken series ("HGX H200 8x SXM" at $3,498); platform rows are SYSTEM prices (÷ GPU count needed), card rows are per-card.
- Registry entries for `gpuSpotPrice`, `apiArr`, `releaseCadence`, `flopsPerDollar` already exist in `registry/indicators.json` — **no registry change is needed, so the F6 pin is never exposed.**
- The agenda engine (F97 `gpu_agent/dashboard/agenda.py`) already consumes `store/series/*.jsonl` + measured findings and picks the strongest fresh signal per slot with stickiness and a `(was: X)` continuity note.
- Live bugs this spec fixes: binding-constraint tile "500 USD billion" (non-canonical unit alias echoed verbatim); demand-quality tile "1 credit_condition_index" (index unit needs a word map); raw indicator ids as tile metric labels; S9 (alternative supply) misplaced in the binding-constraint family.

## Components

### 1. `registry/price-benchmarks.json` — curated benchmark config (new)

The trust boundary for the price files. Explicit named rows only; anything unlisted never enters a series.

```json
{
  "generations": [
    {"id": "blackwell", "rank": 3, "hardware": [
       {"file": "serversimply_gpu_price.csv", "row": "NVIDIA HGX B200 8-GPU",
        "perGpuDivisor": 8, "label": "B200 platform, per GPU"}],
     "rental": {"models": ["B200", "GB200"]}},
    {"id": "hopper", "rank": 2, "hardware": [
       {"file": "thinkmate_gpu_price.csv",
        "row": "NVIDIA® H100 NVL GPU Computing Accelerator - 94GB HBM3 - PCIe 5.0 x16",
        "perGpuDivisor": 1, "label": "H100 NVL card"}],
     "rental": {"models": ["H100", "H200"]}},
    {"id": "ampere", "rank": 1, "hardware": [
       {"file": "thinkmate_gpu_price.csv",
        "row": "NVIDIA® A100 GPU Computing Accelerator - 80GB HBM2",
        "perGpuDivisor": 1, "label": "A100 80GB card"}],
     "rental": {"models": ["A100"]}}
  ]
}
```

- Exact row strings are pinned at implementation time against the real files (the strings above are indicative; the implementer verifies each against the CSV and resolves duplicate rows by picking the longest series).
- **Latest-gen rule:** highest `rank` whose selected rows have a reading within the freshness window (90 days) wins. When Rubin rows appear in the collector's files, adding a `rank: 4` block is a data edit — no code change, no gate.
- Prior-generation readings are still derived and stored (SDEWS P3's glut signal lives in prior-gen price decay); they ride in the series `note` and remain available to the selection engine.

### 2. `price-sync` — folder → series, once per cycle (new CLI verb)

- New module `gpu_agent/price_local.py` + append-only `cli.py` verb `price-sync`:
  - Reads hardware rows per the benchmark config (wide CSV → dated points; `_read_csv` conventions from `pricefeed.py` reused; per-GPU divisor applied; label carried).
  - Reads rental modalities for the latest generation via the EXISTING pricefeed readers plus a `term` dimension on AWS/Azure rows (on-demand / spot / 1-year).
  - Emits monthly readings (latest dated value within each month) into:
    - `store/series/gpuSpotPrice.jsonl` — unit `USD`, one reading per month, `note` carries generation id + benchmark label + prior-gen context.
    - `store/series/gpuRentalOnDemand.jsonl`, `gpuRentalSpot.jsonl`, `gpuRental1yr.jsonl` — unit `USD_per_hr`, latest-gen instance basket medians. These are SERIES ONLY (renderer-side data for the D6 price story); they do NOT add registry indicators.
  - Idempotent: re-running replaces the current month's reading in place, appends history forward-only; never rewrites past months (auditability). Source stamped per reading (`source.title` = file + row/basket).
  - Backfill: first run writes the full history from the files (Feb 2025 →). This is renderer-side series data, not scorecard math — no governance sign-off required, but readings carry `estimateGrade: true` and the derivation note, per the existing series conventions.
- **Cycle integration:** run-cycle invokes `price-sync` before the site rebuild (prose step addition to the run-cycle skill); also callable manually. Deterministic, local-IO only, no network.
- **Staleness:** if the folder's newest date is > 45 days old, `price-sync` logs a warning into its output and still writes nothing new; the agenda band's existing 90-day rule then dims/de-selects the readings. No silent death (SDEWS §3.3 principle).

### 3. Agenda slot-family fixes (`registry/agenda-slots.json`)

| Change | From → To | Why |
|---|---|---|
| `S9` (alternative supply) | binding-constraint → **customer-mix** | AMD/TPU/Huawei is the who-else-supplies question, not what-caps-shipments |
| `gpuSpotPrice`, `gpuRentalOnDemand`, `gpuRentalSpot`, `gpuRental1yr`, `flopsPerDollar` | (unslotted) → **end-market-economics** | the price/efficiency story: can buyers keep paying, what does the market clear at |
| `apiArr` | (unslotted) → **demand-quality** | demand self-funding vs vendor-financed — same question, opposite pole |
| `releaseCadence` | (unslotted) → **demand-durability** | funding/release windows lead compute orders 1–2 quarters |
| `S10` | stays in binding-constraint | inventory tightness is constraint evidence; its bad tile was the unit bug, not placement |

The engine's existing dynamic selection then delivers the user's "keep it dynamic" requirement for free: whichever price modality (or other slot signal) scores strongest appears, with the `(was: …)` note on change.

### 4. Unit hygiene + tile upgrades (`gpu_agent/dashboard/agenda.py`, `brief_render.py`)

- **Alias map** before formatting: `"USD billion"→USD_B`, `"USD_billion"→USD_B`, `"percent"→pct` (implementer greps stored findings for other aliases in the wild and pins each with a test). Fixes the live "500 USD billion" tile.
- **New formats:** `USD` → `$29,999` (thousands-separated; ≥ $1M → `$1.2M`); `USD_per_hr` → `$3.99/hr`; `flops_per_USD` → `209 GFLOPS/$` (scaled engineering units).
- **Word-maps for index-style units:** `credit_condition_index` (+1 → `loosening`, 0 → `neutral`, −1 → `tightening`), `revision_direction` (+1 → `raised`, 0 → `held`, −1 → `cut`) — rendered as the WORD with the unit dropped; fixes "1 credit_condition_index".
- **Change line on tiles:** when the occupant is series-backed, render a delta vs the reading ~90 days back: `−8% vs Apr` (percentage for money units; word deltas for index units). Uses the series history already loaded by the engine; no new state.
- **Plain-English metric labels:** tile metric label = registry `label` (e.g. "GPU rental price"), with the benchmark config's `label` overriding for price tiles ("B200 platform, per GPU"). Raw indicator ids never render (register-lint gains a check that no bare `\b[DSPX]\d{1,2}\b` code appears in a tile label; page-wide codename banning already exists via the F97 lint).
- Per-GPU normalization honesty (design caveat): the tile label ALWAYS names what is priced (card vs platform-per-GPU); the two are never merged into one series.

### 5. Gather-manifest additions (apiArr, releaseCadence)

- Add targeted sources to the merchant-gpu coverage manifest: AI-application-revenue disclosure coverage (hyperscaler AI run-rate statements, model-lab ARR reporting) and frontier release/funding trackers. Measured findings then land through ordinary cycles; the slots light up when they do — no synthetic seeding.
- Gather-side config only: extraction/judge/thesis prompts are built from the registry, which is untouched. **F6 pin must stay green untouched; if it moves, the lane STOPS** (something leaked into a pinned seam).

## Guardrails carried forward

- No edits to `registry/indicators.json`, brains, `gpu_agent/report.py`, eval fixtures (frozen core; F6).
- The F97 register-lint build gate keeps covering the page; new copy (word-maps, delta lines, labels) must pass it.
- Real units only on the band; the C/G disjointness rule holds (new price series are numbers-with-units, not judgment words).
- Work in a claimed worktree lane (`.worktrees/f98-agenda-data`), branch `f98-agenda-data`; stop-before-merge; only the user merges.

## Acceptance criteria

1. After `price-sync` on the real folder: `store/series/gpuSpotPrice.jsonl` + the three rental series exist with full backfill and a current-month reading; every reading carries source, unit, and note.
2. The live-rebuilt brief shows a latest-generation price tile in *End-market economics* with a real `$` value, the benchmark label naming what's priced, a trend word, and a change line.
3. Generation roll test: fixture rows for a newer generation flip the benchmark with config-only change.
4. Curation test: a deliberately broken fixture row (unlisted) never reaches a series.
5. "500 USD billion" and "1 credit_condition_index" tiles render as `$500B` and a word (e.g. `loosening`) respectively; alias/word-map table pinned by tests.
6. `S9`-family finding no longer occupies binding-constraint; slot families match §3's table exactly.
7. No raw indicator id renders as a tile label (lint check).
8. Manifest additions present for apiArr/releaseCadence source families; cycle logs show the gatherer targeting them.
9. Full suite green; F6 pin green UNTOUCHED; F83 conformance green.
10. Staleness: with a fixture folder aged > 90 days, price tiles de-select/dim per the existing rule (no silent stale numbers).

## Out of scope (recorded so nothing is silently dropped)

- Part B: S4 upstream lead-time index adoption (registry change → F6 gate) — separate lane per backlog F98.
- Azure hardware/1-yr parsing beyond what the existing readers + `term` column give cheaply; second-hand marketplaces (eBay sold data) — future source for true P3 resale prices (current files are new-hardware street + EOL prices; the tile label says so).
- Sparklines on price tiles (F97's future option; needs the dataviz procedure when it comes).
