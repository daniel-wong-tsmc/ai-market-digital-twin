# F122 — Daily GPU leasing-price pull, in-repo, feeding the brief — design spec

**Date:** 2026-08-20
**Status:** Design APPROVED by user (interactive, 2026-08-20, section by section); spec awaiting user review.
**Scope:** Move the user's standalone `C:\Users\danie\gpu-price-tracker\pull_gpu_prices.py` into the repo as a
deterministic CLI verb, run it inside run-cycle step 7 every cycle, save one local (gitignored) snapshot per
day, and teach the existing price reader to read those snapshots so the dashboard price tile, the brief's
price lines, and the monthly rental series come back to life. Lane: `.worktrees/f122-price-pull`, branch
`f122-price-pull`, base `320a495`.
**Origin:** user request 2026-08-20 ("each time we run the GPU agent, I want us to also check the GPU prices.
The process should be laid out here [gpu-price-tracker]"). A prior session the same evening (21:03–21:14)
had already added a "Step 4: leasing-price pull" to the global launcher skill `run-gpu-market` (a Claude
subagent running the script outside the repo) and sketched a `history_paths` test it never implemented. The
user confirmed that session is finished and this lane takes over.

## Decision provenance (all interactive, user-selected; ZERO AFK-defaults)

1. **Scope = run + record + feed the brief** — over "run + record only" and "just run it".
2. **Script home = inside the repo** (`gpu_agent/pricepull.py` + tests in the main suite) — over "keep it
   separate under its own git" and "keep it separate, no git".
3. **Daily snapshots are LOCAL ONLY, not committed** — the user chose this over committing them under
   `store/`. Consequence accepted: price history lives on this machine only; a fresh clone shows no prices
   (same as the legacy feeds today).
4. **The prior session's work is taken over, launcher included** — its Step 4 is replaced by a pointer to the
   in-repo step (over "leave the launcher alone").
5. **Approach A** (in-repo verb + snapshot-backed reader) over B (keep the script outside, only add a reader)
   and C (convert the new data into the legacy folder formats).
6. Assistant judgment calls, stated in the design and approved as part of it: headline prices use
   **on-demand rows only, US regions** (Vast.ai marketplace/interruptible and spot/reserved rows are stored
   but do not enter the headline); **snapshot wins over legacy** whenever a snapshot exists at/before the
   requested date; backlog number **F122** minted by the assistant (F121 was taken mid-session by the
   report-quality-pair lane — renumber if collided again).

## What exists (verified 2026-08-20)

- `C:\Users\danie\gpu-price-tracker\pull_gpu_prices.py` (13.6 KB, stdlib only): fetchers for Azure (retail
  prices API), AWS (ec2.shop), RunPod (GraphQL), Vast.ai (bundles API), CoreWeave (HTML scrape), Lambda
  (optional, `LAMBDA_API_KEY`). Every price becomes one long-format row:
  `provider, gpu_model, price_type, usd_per_gpu_hr, usd_per_instance_hr, gpus_per_instance, instance,
  region, source, retrieved_at`. `price_type` ∈ {on_demand, spot, reserved_1yr, reserved_3yr, reserved_5yr,
  community, marketplace_min, interruptible_min}. Today's run: 873 rows (Azure 666, RunPod 88, AWS 53,
  Vast.ai 48, CoreWeave 18), zero provider errors. Output is overwritten each run — no history.
  `tests/test_pull_gpu_prices.py`: 20 unittest cases, all offline (fixture `coreweave_sample.html`); 19 pass,
  1 errors because `history_paths()` does not exist.
- `gpu_agent/pricefeed.py` (F78 Stage 5): reads the gitignored legacy folder `gpu_agent/scrape_data/`
  ({aws,coreweave,gcp,oracle} CSVs, last data 2026-07-08) into `PricePoint`s; `headline_prices(as_of)` =
  median of per-provider medians over fresh (≤ 45 days) on-demand gpu-class points for H100/H200/B200/B300;
  `price_delta`, `lookback_label`. DISPLAY-ONLY — never feeds scoring. Consumers: `dashboard/featured.py`
  (H100 tile via `registry/featured-metrics.json` kind `pricefeed`), `change.py` (`price_cells_from_feed`,
  `prices_by_lookback` for the brief). Both degrade to "no price" when the feed is empty.
- `gpu_agent/price_local.py` (F98 `price-sync`): reads the gitignored `gpu_agent/data/gpu_leasing_data/`
  (last data 2026-07-15) → `store/series/{gpuSpotPrice,gpuRentalOnDemand,gpuRentalSpot,gpuRental1yr}.jsonl`.
  Hardware purchase prices (thinkmate/serversimply rows named in `registry/price-benchmarks.json`) drive
  `gpuSpotPrice`; rental on-demand comes via `pricefeed.load_points`, spot via `aws_spot_price.csv`, 1-year
  via `aws_price.csv`. **Coupling defect:** one `stale` flag (hardware newest > 45 days old) also suppresses
  the *current month's rental rows* (`if m == current_period and stale: continue`), so fresh rental data
  cannot write while the hardware folder is stale. Every cycle since July logs
  `stale price folder: newest data 260602`.
- run-cycle `SKILL.md` step `### 7. Price-sync (deterministic — no LLM)`: "Warnings are logged, never
  fatal — this step never blocks the cycle." Sub-steps 7b–7e follow. The Procedure step list is pinned by
  `tests/test_run_cycle_conformance.py::EXPECTED_STEPS` + the SKILL fingerprint comment (F83); step 7 is
  pinned as `("7", "price-sync")`.
- Scheduled nightly job `~/.claude/jobs/gpu-daily-cycle.ps1` prompts "Use the run-gpu-market skill…", so the
  launcher IS on the nightly path; its Step 4 currently dispatches an `opus` subagent to run the external
  script and keep `history\` outside the repo ("full repo integration is a separately-filed backlog item" —
  nothing was filed).
- Cycle-log entries carry free-form keys beside the required header (e.g. `priceSync`, `seriesRefresh`); no
  model field lists them (grep `priceSync` over `gpu_agent/*.py` = 0 hits). Verify the integrity tripwire
  (`tests/test_store_cycle_log_integrity.py`) tolerates a new key at implementation time.

## Components

### 1. `gpu_agent/pricepull.py` — the ported puller (new)

The script moved nearly verbatim: `NORMALIZE_RULES`/`normalize`, `AZURE_SKUS`/`fetch_azure`/
`azure_item_to_price`, `AWS_FAMILIES`/`fetch_aws`, `fetch_runpod`, `VAST_MODELS`/`fetch_vast`/
`pick_vast_offer`, `fetch_coreweave`/`parse_coreweave`, `fetch_lambda`, `FETCHERS`, `row`, `http_get`.
House-rule adjustments only:

- **No wall-clock inside the module.** `retrieved_at` / `as_of` are parameters; the CLI edge computes
  today's date (the `price-sync` precedent in `cli.py::_price_sync`).
- **Output folder is a parameter**, default `gpu_agent/data/leasing_snapshots/` (inside the already
  gitignored `gpu_agent/data/`). File name `gpu_prices-<YYYY-MM-DD>.csv`. `snapshot_path(out_dir, as_of)`
  is the pure naming helper the prior session's test wanted (`history_paths` renamed; one CSV, no JSON —
  the JSON duplicated the CSV and only added `errors`, which now go to the printed summary + cycle log).
- `run_pull(as_of, out_dir, fetchers=FETCHERS, retrieved_at=...)` → `PullResult`
  `{date, path|None, rows, perProvider: {name: count}, failed: [{provider, error}]}`. Each fetcher is
  try/excepted individually (as today). **Zero rows → no file written**, `path: None`. Same-day re-run
  overwrites that day's file (idempotent).
- The printed summary tables from the script's `main()` are dropped (the cycle log and report carry the
  outcome); the CLI prints the `PullResult` as JSON.

### 2. CLI verb `price-pull`

```
.venv/Scripts/python -m gpu_agent.cli price-pull --as-of <YYYY-MM-DD> [--out DIR]
```
`--as-of` defaults to today's ISO date computed at the CLI edge. Exit 0 always — including when every
provider fails (the result says so); exit 2 only for operator mistakes (malformed `--as-of`, unwritable
`--out`), mirroring `series-refresh`. Prints the `PullResult` JSON on one line.

### 3. `pricefeed.py` — snapshot backend (extend, don't replace)

- `DEFAULT_SNAPSHOT_DIR = Path(__file__).parent / "data" / "leasing_snapshots"`.
- `_snapshot_file(as_of, snapshot_dir)` → the newest `gpu_prices-<date>.csv` whose date ≤ `period_end(as_of)`
  (the same nearest-at-or-before rule the legacy readers use), or None.
- `_snapshot_points(as_of, snapshot_dir)` → `PricePoint`s from that file: rows with
  `price_type == "on_demand"` and a US region per the table below; `provider` = lower-cased provider name;
  `model` via the existing `_match_model` over `gpu_model` (unmatched names skipped, e.g. RTX cards);
  `vendor` via `_vendor`; `gpu_class = "gpu"`; `term = "on_demand"`; `price_date` = the file's date as
  YYMMDD; `instance`/`region` copied for provenance.

  | provider | US-region rule |
  |---|---|
  | Azure | `armRegionName` starts with one of exactly `eastus`, `westus`, `centralus`, `northcentralus`, `southcentralus`, `westcentralus` (covers `eastus2`, `westus3`; excludes `australia*`, `usgov*`) |
  | AWS | region starts with `us-` |
  | Vast.ai | region ends with `, US` |
  | RunPod | `global` passes (no region concept) |
  | CoreWeave | `us` passes |
  | Lambda | `varies` passes |
  If a provider has rows but none match its US rule, that provider contributes nothing (no silent
  fallback to other regions — the old reader's explicit-fallback list was per-instance and documented; here
  the honest answer is "no US price").
- `load_points(as_of, data_dir=DEFAULT_DATA_DIR, snapshot_dir=DEFAULT_SNAPSHOT_DIR)`: **if a snapshot
  exists at/before `as_of`, return snapshot points; else the legacy four readers** (unchanged). `PROVIDERS`
  grows to `("aws","coreweave","gcp","oracle","azure","runpod","vast.ai","lambda")` so `headline_prices`'s
  per-provider median loop sees the new providers. `headline_prices`, `price_delta`, `_fresh`,
  `custom_silicon_series` unchanged in logic (custom silicon is legacy-only; snapshots carry none).
- Consequences, for free: `featured.py` H100 tile, `change.py` price cells, and `price_local`'s on-demand
  rental reading all revive. `price_delta` honestly returns `None` deltas until a snapshot ≥ 30 days old
  exists.

### 4. `price_local.py` — rental from snapshots + decoupled staleness

- `_spot_points` / `_term_points` gain a snapshot path: when `pricefeed._snapshot_file` finds a file for
  the month-end, spot = median over rows `price_type == "spot"` (US rule, models ∈ the generation's rental
  models), 1yr = median over `price_type == "reserved_1yr"`; `source` = the snapshot file name. Legacy
  `aws_spot_price.csv` / `aws_price.csv` paths remain the fallback when no snapshot exists.
- **Staleness split:** `stale_hw` (hardware newest > 45 days; drives the existing warning text and the
  `gpuSpotPrice` current-month skip) and `stale_rental` (no rental point within 45 days of `as_of`; drives
  the rental current-month skip and a separate warning `stale rental data: ...`). The existing hardware
  warning keeps its wording so operators recognise it; it will keep firing honestly because this lane adds
  no hardware purchase-price source.

### 5. run-cycle `SKILL.md` step 7 (gated edit — F83 pin moves EXACTLY once)

Heading becomes `### 7. Price-pull + price-sync (deterministic — no LLM)`. Body: run
`price-pull --as-of <YYYY-MM-DD>` (cycle day) first; record its JSON under a `pricePull` cycle-log key
(`result: done|empty|failed`, `rows`, `perProvider`, `failed`, `snapshot`); then the existing `price-sync`
text verbatim. The "never blocks the cycle" rule covers both. `EXPECTED_STEPS` entry
`("7", "price-sync")` → `("7", "price-pull + price-sync")` and the fingerprint comment re-recorded in the
**same commit** as the SKILL edit. No other step, no F6 prompt, no narrator prompt, no registry touched —
`tests/test_evals_baseline_pin.py` and the narrator pin must stay byte-green.

### 6. Launcher `~/.claude/skills/run-gpu-market/SKILL.md` (outside the repo)

Step 4 collapses to: "Leasing prices are pulled inside run-cycle step 7 (`gpu-agent price-pull`,
deterministic, never blocks); nothing to dispatch here." Step 6's "plus the leasing-price pull outcome
line" stays. The `opus` subagent dispatch is removed.

### 7. `C:\Users\danie\gpu-price-tracker\MOVED.md` (outside the repo)

One paragraph: new home, new command, where snapshots land. Nothing deleted — the user decides.

### 8. Tests (all offline)

- `tests/test_pricepull.py`: the 19 ported cases (normalize, CoreWeave fixture parse, Azure item pricing,
  Vast offer pick) converted to pytest; `snapshot_path` naming; `run_pull` with injected fake fetchers into
  `tmp_path` — writes the CSV with the exact column order, per-provider counts, a raising fetcher lands in
  `failed` and the others still write, all-failing → no file + `path None`; same-day re-run overwrites.
- `tests/test_pricefeed_snapshot.py`: nearest-at/before file pick; US-region filter per provider; model
  matching; `load_points` prefers snapshot, falls back to legacy when the snapshot dir is empty/missing;
  `headline_prices` over a 2-provider snapshot = median of provider medians.
- `tests/test_price_local.py` additions: snapshot-backed spot/1yr; `stale_hw` true + fresh rental →
  current-month rental rows written, hardware warning still present.
- `tests/test_cli_price_pull.py` (or inside an existing CLI test module): `--as-of` malformed → exit 2;
  default run with fake fetchers → exit 0 + JSON.
- `tests/test_run_cycle_conformance.py`: `EXPECTED_STEPS` + fingerprint re-record (one commit with the
  SKILL edit).

### 9. Verification (evidence, not assertion)

Full suite green from the worktree (`../../.venv/Scripts/python -m pytest -q`; expect the 6 worktree
skips); `npm --prefix web test` untouched (no web change). Then on this machine: one real `price-pull`
(prove fetch works — print the JSON), `price-sync --as-of <today>` (show `gpuRentalOnDemand` written for
2026-08 and the warnings), and `dashboard-json` (show the H100 tile carries today's number). Exact outputs
go in the DONE sentinel.

## Data flow

```
run-cycle step 7
  price-pull --as-of D  ── fetch 5–6 providers ──► gpu_agent/data/leasing_snapshots/gpu_prices-D.csv  (local only)
                                                          │
  price-sync --as-of D ──► price_local ──► pricefeed.load_points(D)  ◄── snapshot (else legacy folders)
                              │                     │
                              ▼                     ▼
            store/series/gpuRental*.jsonl     headline_prices(D) ──► dashboard H100 tile, brief price lines
```

## Error handling

Per-provider fetch errors → `failed[]`, others proceed. All fail → no file, `result: empty`, cycle log says
so, cycle continues. Snapshot folder missing/empty → legacy readers → possibly `{}` → consumers show "no
price" exactly as today. Malformed snapshot row (bad number) → row skipped. Nothing in this lane can raise
into the cycle; `price-pull` never exits non-zero on data problems.

## Out of scope (explicit)

- Hardware purchase prices (thinkmate/serversimply) — the script does not collect them; `gpuSpotPrice` and
  its staleness warning are unchanged.
- Committing snapshots to git (user decision 3). Revisit only if the user changes their mind.
- Any scoring/DMI/SMI use of prices (F8 display-only stands).
- Backfilling history before the first snapshot.
- New providers or GPU models beyond what the script already handles.

## Backlog

File **F122** in `docs/fix-backlog.md` (this lane; tick at merge) with the concurrent-mint caveat. Note in
the entry: the prior session's launcher Step 4 is superseded.
