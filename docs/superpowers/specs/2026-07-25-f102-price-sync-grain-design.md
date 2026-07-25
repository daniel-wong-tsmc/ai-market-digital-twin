# F102 — price-sync Month-Grain Crash (date-parse fix + graceful degradation)

**Date:** 2026-07-25
**Status:** Spec (design presented interactively 2026-07-25; direction confirmed by the user's
request to spec it properly)
**History:** four sightings (v11, v14, v15, v17 cycles). `store/series/*` has not refreshed
since v13 — visibly: the front page's anchored "what a GPU rents for" gauge now wears an F103
aging mark it should not need.

## 1. Root cause (verified 2026-07-25)

`gpu_agent/price_local.py::sync_series` @:285 slices its `as_of` assuming day grain:
`as_of[2:4] + as_of[5:7] + as_of[8:10]`. The monthly cycle invokes
`price-sync --as-of 2026-07` (run-cycle SKILL.md @:367), so `as_of[8:10]` is empty and
`_yymmdd_date` (@:206) crashes on `int("")`. The v11 sighting was the same family
(empty-string date parse). The crash contradicts the step's own contract — run-cycle SKILL.md:
"Warnings are logged, never fatal — this step never blocks the cycle."

## 2. The fix

1. **Tolerant as-of parsing.** A new `_parse_as_of(as_of: str) -> str` (returns YYMMDD)
   accepting exactly two grains:
   - `YYYY-MM-DD` → behaves as today;
   - `YYYY-MM` → resolved to the month's TRUE last calendar day via the existing
     `_month_end_yymmdd` helper (@price_local.py, already correct for short months).
   `sync_series` uses it instead of the raw slice. Downstream staleness math
   (the >45-day check @:294) is unchanged; month-grain simply anchors at month-end —
   deterministic and consistent with how the monthly cycle thinks about its vintage.
2. **Graceful degradation on anything else.** A malformed/empty `as_of` must NOT raise out of
   `sync_series`: it returns the documented warning path (warning string appended, no series
   rows written, no partial writes), and the CLI verb exits 0 with the warning printed —
   honoring "never blocks the cycle" at the code level, not just the skill level.

## 3. Constraints

- `price_local.py` only (+ its tests). Display-only subsystem — price series never score;
  scoring replay pin trivially unaffected. Frozen core, brains, prompts, registries (except
  nothing — no registry change), eval + narrator fixtures: byte-untouched; all four pins green.
- No behavior change for day-grain callers; the curated `registry/price-benchmarks.json`
  trust boundary untouched.
- Wall-clock isolation preserved (`as_of` remains the only time input; no `date.today()`).

## 4. Testing

- Unit: `_parse_as_of("2026-07-17")` == day grain today; `_parse_as_of("2026-07")` == that
  month's last day (Feb/leap-year cases included); malformed inputs (`""`, `"garbage"`,
  `"2026"`, `"2026-7"`) → the warning path, no exception.
- Regression (the four-sighting reproduction): `sync_series(..., as_of="2026-07")` over a
  fixture data dir completes, writes series rows, zero warnings about dates.
- Idempotence/partial-write guard: malformed as-of leaves `series_dir` byte-identical.
- CLI: `price-sync --as-of 2026-07` exits 0 (fixture data), `--as-of garbage` exits 0 WITH the
  warning printed.
- Live criterion (post-merge, not forced): the next scheduled cycle's price-sync step logs a
  successful refresh and `store/series/gpuRentalOnDemand.jsonl` gains a 2026-07 row — the
  front-page rent gauge drops its aging mark.

## 5. Out of scope

F96 (separate lane, disjoint files); any change to the price CSV curation, benchmarks, or the
run-cycle step wording (the step already says never-fatal — the code now finally complies).
