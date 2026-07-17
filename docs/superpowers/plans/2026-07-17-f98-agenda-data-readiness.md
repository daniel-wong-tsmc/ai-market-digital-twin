# F98 Part A — Agenda-Band Data-Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Executive Brief's agenda band fully data-ready per spec `docs/superpowers/specs/2026-07-17-f98-agenda-data-readiness-design.md`: a dynamic latest-generation price benchmark fed from the local `gpu_agent/data/gpu_leasing_data/` folder, slot-family fixes, unit hygiene, and gather-manifest sources for apiArr/releaseCadence.

**Architecture:** New `gpu_agent/price_local.py` (curated hardware+rental readers → monthly series) driven by `registry/price-benchmarks.json`, exposed as an append-only `price-sync` CLI verb and a run-cycle step. Renderer upgrades live in `gpu_agent/dashboard/agenda.py` (unit aliases/word-maps, labels, delta lines) and `brief_render.py`. Slot config and manifest are data edits.

**Tech Stack:** Python 3 stdlib (csv, json, re, datetime, pathlib, statistics) + existing `gpu_agent.pricefeed` helpers + pydantic-validated manifest loader. Tests: pytest, `tmp_path` fixtures.

## Global Constraints

- Lane: worktree `.worktrees/f98-agenda-data`, branch `f98-agenda-data` (create at execution start via superpowers:using-git-worktrees). Never work on root main.
- Python from the worktree: `../../.venv/Scripts/python`; tests: `../../.venv/Scripts/python -m pytest`.
- DO NOT touch: `registry/indicators.json`, `gpu_agent/report.py`, brains/prompts, `gpu_agent/scoring.py`, eval fixtures. `tests/test_evals_baseline_pin.py` (F6) must stay green UNTOUCHED — if it reddens, STOP the lane and report.
- `gpu_agent/pricefeed.py` is modified ONLY additively (new exported helper reuse; no change to existing functions, `DEFAULT_DATA_DIR`, or `PricePoint`).
- Series files under `store/series/` follow the existing row schema: `{"indicatorId","period","value","unit","publishedAt","capturedAt","source":{"url","title"},"estimateGrade","note"}` (+ new optional `"label"`).
- Determinism: no wall-clock inside `price_local.py` or dashboard modules — `as_of` / `today` are parameters; `cli.py` isolates `datetime.date.today()` at the edge (F95 `_now_stamp` precedent).
- Exec-copy register rules (F97 spec) bind all new rendered copy; the register-lint build gate must pass.
- All store-derived text HTML-escaped; files written with `newline="\n"`.
- `git log --oneline -1` immediately before every commit (concurrent-instance guard).
- The real data folder `gpu_agent/data/gpu_leasing_data/` is gitignored — tests use fixture CSVs; only Task 8 touches the real folder (read-only + `store/series/` writes, which ARE committed).

---

### Task 1: Benchmark config + curated hardware-price reader

**Files:**
- Create: `registry/price-benchmarks.json`
- Create: `gpu_agent/price_local.py`
- Test: `tests/test_price_local.py`

**Interfaces:**
- Consumes: nothing new (stdlib + config).
- Produces:
  - `BENCHMARKS_PATH = "registry/price-benchmarks.json"`; `load_benchmarks(path=BENCHMARKS_PATH) -> list[dict]` (generations sorted by `rank` DESC).
  - `@dataclass(frozen=True) HardwarePoint`: `generation: str`, `label: str`, `date: str` (YYMMDD), `usd_per_gpu: float`, `source_file: str`, `row_name: str`.
  - `read_hardware_points(data_dir, benchmarks) -> list[HardwarePoint]` — wide-CSV parse; ONLY rows named in config; per-GPU divisor applied; duplicate row names resolved by keeping the row with the most non-empty cells; unparseable cells skipped.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_price_local.py
import json
import pytest
from gpu_agent.price_local import (
    BENCHMARKS_PATH, HardwarePoint, load_benchmarks, read_hardware_points)


def test_load_benchmarks_real_config_sorted_by_rank_desc():
    gens = load_benchmarks()
    ranks = [g["rank"] for g in gens]
    assert ranks == sorted(ranks, reverse=True)
    ids = [g["id"] for g in gens]
    assert "blackwell" in ids and "hopper" in ids
    for g in gens:
        for h in g["hardware"]:
            assert h["file"] and h["row"] and h["perGpuDivisor"] >= 1 and h["label"]


BENCH = [{"id": "hopper", "rank": 2, "hardware": [
            {"file": "hw.csv", "row": "NVIDIA H100 Card", "perGpuDivisor": 1,
             "label": "H100 card"}], "rental": {"models": ["H100"]}},
         {"id": "blackwell", "rank": 3, "hardware": [
            {"file": "hw.csv", "row": "HGX B200 8-GPU", "perGpuDivisor": 8,
             "label": "B200 platform, per GPU"}], "rental": {"models": ["B200"]}}]


def _write_hw(tmp_path, rows):
    lines = ["gpu,250601,250715,260701"]
    lines += rows
    (tmp_path / "hw.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_read_hardware_points_curates_divides_and_skips(tmp_path):
    _write_hw(tmp_path, [
        "NVIDIA H100 Card,30000.0,29500.0,29999.0",
        "HGX B200 8-GPU,,260000.0,260128.0",
        "Broken Junk Row,1.0,2.0,3.0",              # unlisted -> never read
    ])
    pts = read_hardware_points(tmp_path, BENCH)
    by_gen = {(p.generation, p.date): p for p in pts}
    assert by_gen[("hopper", "250601")].usd_per_gpu == 30000.0
    assert by_gen[("blackwell", "260701")].usd_per_gpu == pytest.approx(260128.0 / 8)
    assert ("blackwell", "250601") not in by_gen          # blank cell skipped
    assert not [p for p in pts if p.row_name == "Broken Junk Row"]
    assert by_gen[("hopper", "250601")].label == "H100 card"


def test_read_hardware_points_duplicate_rows_keep_longest(tmp_path):
    _write_hw(tmp_path, [
        "NVIDIA H100 Card,30000.0,,",               # 1 cell
        "NVIDIA H100 Card,31000.0,30500.0,29999.0", # 3 cells -> wins
    ])
    pts = read_hardware_points(tmp_path, BENCH)
    hopper = sorted([p for p in pts if p.generation == "hopper"],
                    key=lambda p: p.date)
    assert [p.usd_per_gpu for p in hopper] == [31000.0, 30500.0, 29999.0]


def test_read_hardware_points_missing_file_is_empty(tmp_path):
    assert read_hardware_points(tmp_path, BENCH) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/test_price_local.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gpu_agent.price_local'`

- [ ] **Step 3: Write config + implementation**

First VERIFY the real row names (the spec's strings are indicative). From the worktree:
`../../.venv/Scripts/python -c "import csv; [print(repr(r[0])) for r in csv.reader(open('../../gpu_agent/data/gpu_leasing_data/thinkmate_gpu_price.csv', encoding='utf-8'))]"` and the same for `serversimply_gpu_price.csv`. Pin the EXACT strings for: H100 NVL (thinkmate, the n=420 row), A100 80GB (thinkmate), HGX B200 8-GPU (serversimply). Where a name appears twice the duplicate-resolution rule (most non-empty cells) makes either safe, but pin the canonical spelling.

```json
// registry/price-benchmarks.json  (rows below MUST be replaced by the verified strings)
{
  "generations": [
    {"id": "blackwell", "rank": 3,
     "hardware": [{"file": "serversimply_gpu_price.csv",
                   "row": "NVIDIA HGX B200 8-GPU", "perGpuDivisor": 8,
                   "label": "B200 platform, per GPU"}],
     "rental": {"models": ["B200", "GB200", "B300"]}},
    {"id": "hopper", "rank": 2,
     "hardware": [{"file": "thinkmate_gpu_price.csv",
                   "row": "<VERIFIED H100 NVL ROW>", "perGpuDivisor": 1,
                   "label": "H100 NVL card"}],
     "rental": {"models": ["H100", "H200"]}},
    {"id": "ampere", "rank": 1,
     "hardware": [{"file": "thinkmate_gpu_price.csv",
                   "row": "<VERIFIED A100 80GB ROW>", "perGpuDivisor": 1,
                   "label": "A100 80GB card"}],
     "rental": {"models": ["A100"]}}
  ]
}
```

```python
# gpu_agent/price_local.py
"""F98 price-sync — curated local price data -> store/series (renderer-side only).

Reads the auto-refreshed gpu_agent/data/gpu_leasing_data/ folder. The benchmark
config is the trust boundary: only rows named there ever reach a series.
DISPLAY-ONLY (F8): never feeds scoring.py / DMI / SMI. No wall-clock: as_of is
always a parameter."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

BENCHMARKS_PATH = "registry/price-benchmarks.json"
DEFAULT_LEASING_DIR = Path(__file__).parent / "data" / "gpu_leasing_data"


def load_benchmarks(path: str = BENCHMARKS_PATH) -> list[dict]:
    with open(Path(path), encoding="utf-8") as fh:
        gens = json.load(fh)["generations"]
    return sorted(gens, key=lambda g: -g["rank"])


@dataclass(frozen=True)
class HardwarePoint:
    generation: str
    label: str
    date: str            # YYMMDD column key
    usd_per_gpu: float
    source_file: str
    row_name: str


def _wide_rows(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    """gpu,YYMMDD,... wide CSV -> (date_headers, {row_name: cells}); duplicate row
    names keep the row with the most non-empty cells."""
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], {}
    dates = rows[0][1:]
    best: dict[str, list[str]] = {}
    for r in rows[1:]:
        if not r:
            continue
        name, cells = r[0], r[1:]
        filled = sum(1 for c in cells if c.strip())
        cur = best.get(name)
        if cur is None or filled > sum(1 for c in cur if c.strip()):
            best[name] = cells
    return dates, best


def read_hardware_points(data_dir, benchmarks) -> list[HardwarePoint]:
    data_dir = Path(data_dir)
    cache: dict[str, tuple[list[str], dict[str, list[str]]]] = {}
    out: list[HardwarePoint] = []
    for gen in benchmarks:
        for hw in gen["hardware"]:
            fname = hw["file"]
            if fname not in cache:
                p = data_dir / fname
                cache[fname] = _wide_rows(p) if p.exists() else ([], {})
            dates, rows = cache[fname]
            cells = rows.get(hw["row"])
            if cells is None:
                continue
            div = float(hw["perGpuDivisor"])
            for d, c in zip(dates, cells):
                c = c.strip()
                if not c:
                    continue
                try:
                    v = float(c.replace("$", "").replace(",", ""))
                except ValueError:
                    continue
                out.append(HardwarePoint(generation=gen["id"], label=hw["label"],
                                         date=d, usd_per_gpu=v / div,
                                         source_file=fname, row_name=hw["row"]))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/test_price_local.py -v`
Expected: 4 passed. (`test_load_benchmarks_real_config...` reads the real config — it must pass with the verified row strings in place.)

- [ ] **Step 5: Commit**

```bash
git add registry/price-benchmarks.json gpu_agent/price_local.py tests/test_price_local.py
git commit -m "feat(f98): benchmark config + curated hardware-price reader"
```

---

### Task 2: Rental-modality readers (on-demand / spot / 1-year)

**Files:**
- Modify: `gpu_agent/price_local.py`
- Test: `tests/test_price_local.py` (append)

**Interfaces:**
- Consumes: `gpu_agent.pricefeed` exports — `load_points(as_of, data_dir)`, `AWS_INSTANCE_MAP`, `_nearest_at_or_before` (import the private helper deliberately; it is stable and pinned by pricefeed's own tests), `lookback_label`.
- Produces:
  - `@dataclass(frozen=True) RentalPoint`: `modality: str` ("on_demand"|"spot"|"1yr"), `model: str`, `date: str` (YYMMDD), `usd_per_gpu_hour: float`, `source: str`.
  - `read_rental_points(leasing_dir, models: set[str], month_end_yymmdd: str) -> list[RentalPoint]`:
    - **on_demand:** `pricefeed.load_points(as_of_label, data_dir=leasing_dir)` filtered to `models` (pricefeed already normalizes per-GPU-hour; `leasing_dir` works because the folder is a superset of `scrape_data` with identical file names/format).
    - **spot:** `aws_spot_price.csv` (long format `,instance,region,date,avg_price,high,low`): keep rows whose `instance` is in `AWS_INSTANCE_MAP` with a model in `models`; per-GPU divide by the map's count; for the month, take the newest date ≤ month-end per instance, then the median across instances/regions.
    - **1yr:** `aws_price.csv` rows with `term == "1 year"` and instance in the map with model in `models`; nearest date column ≤ month-end; per-GPU divide; median.

- [ ] **Step 1: Write the failing tests** (append)

```python
from gpu_agent.price_local import RentalPoint, read_rental_points


def _mk_leasing(tmp_path):
    # aws_price.csv: on-demand + 1yr rows for p5.48xlarge (H100 x8 per AWS_INSTANCE_MAP)
    (tmp_path / "aws_price.csv").write_text(
        "instance,term,region,260601,260708\n"
        "p5.48xlarge,OnDemand,US East (N. Virginia),98.32,96.00\n"
        "p5.48xlarge,1 year,US East (N. Virginia),63.20,60.80\n",
        encoding="utf-8")
    (tmp_path / "aws_spot_price.csv").write_text(
        ",instance,region,date,avg_price,high,low\n"
        "1,p5.48xlarge,us-east-1a,260705,41.60,42.0,41.0\n"
        "2,p5.48xlarge,us-east-1b,260706,44.80,45.0,44.0\n",
        encoding="utf-8")
    return tmp_path


def test_read_rental_points_all_three_modalities(tmp_path):
    d = _mk_leasing(tmp_path)
    pts = read_rental_points(d, {"H100"}, "260708")
    by_mod = {p.modality: p for p in pts}
    assert by_mod["on_demand"].usd_per_gpu_hour == pytest.approx(96.00 / 8)
    assert by_mod["1yr"].usd_per_gpu_hour == pytest.approx(60.80 / 8)
    # spot: median of the two newest-per-instance readings (same instance, two
    # regions -> both kept; median of 41.60/8 and 44.80/8)
    assert by_mod["spot"].usd_per_gpu_hour == pytest.approx((41.60 + 44.80) / 2 / 8)
    assert all(p.model == "H100" for p in pts)


def test_read_rental_points_ignores_unwanted_models_and_missing_files(tmp_path):
    d = _mk_leasing(tmp_path)
    assert read_rental_points(d, {"B200"}, "260708") == []
    assert read_rental_points(tmp_path / "nope", {"H100"}, "260708") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/test_price_local.py -v`
Expected: new tests FAIL with `ImportError: cannot import name 'RentalPoint'`

- [ ] **Step 3: Implement** (append to `price_local.py`)

```python
import statistics

from gpu_agent.pricefeed import (AWS_INSTANCE_MAP, _nearest_at_or_before,
                                 load_points)


@dataclass(frozen=True)
class RentalPoint:
    modality: str        # "on_demand" | "spot" | "1yr"
    model: str
    date: str            # YYMMDD actually used
    usd_per_gpu_hour: float
    source: str


def _yymmdd_to_label(yymmdd: str) -> str:
    return f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"


def _map_rows_for(models):
    return {inst: (vendor, model, cnt)
            for inst, (vendor, model, klass, cnt) in AWS_INSTANCE_MAP.items()
            if klass == "gpu" and model in models}


def _spot_points(leasing_dir, models, month_end) -> list[RentalPoint]:
    path = Path(leasing_dir) / "aws_spot_price.csv"
    if not path.exists():
        return []
    wanted = _map_rows_for(models)
    newest = {}   # (instance, region) -> (date, price_per_gpu)
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            inst = (row.get("instance") or "").strip()
            if inst not in wanted:
                continue
            d = (row.get("date") or "").strip()
            if not d or d > month_end:
                continue
            try:
                price = float(row.get("avg_price") or "")
            except ValueError:
                continue
            _, model, cnt = wanted[inst]
            key = (inst, row.get("region") or "")
            if key not in newest or d > newest[key][0]:
                newest[key] = (d, price / cnt, model)
    if not newest:
        return []
    per_gpu = [v[1] for v in newest.values()]
    used_date = max(v[0] for v in newest.values())
    model = sorted({v[2] for v in newest.values()})[0]
    return [RentalPoint("spot", model, used_date,
                        statistics.median(per_gpu), "aws_spot_price.csv")]


def _term_points(leasing_dir, models, month_end) -> list[RentalPoint]:
    path = Path(leasing_dir) / "aws_price.csv"
    if not path.exists():
        return []
    wanted = _map_rows_for(models)
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f))
    if not rows:
        return []
    header = rows[0]
    date_cols = {h: i for i, h in enumerate(header) if h.strip().isdigit()}
    per_gpu = []
    used = None
    for r in rows[1:]:
        if len(r) < 4:
            continue
        inst, term = r[0].strip(), r[1].strip().lower()
        if inst not in wanted or term != "1 year":
            continue
        avail = [d for d in date_cols if r[date_cols[d]].strip()]
        d = _nearest_at_or_before(month_end, avail)
        if d is None:
            continue
        try:
            price = float(r[date_cols[d]])
        except ValueError:
            continue
        _, model, cnt = wanted[inst]
        per_gpu.append(price / cnt)
        used = (d, model)
    if not per_gpu:
        return []
    return [RentalPoint("1yr", used[1], used[0],
                        statistics.median(per_gpu), "aws_price.csv")]


def read_rental_points(leasing_dir, models, month_end_yymmdd) -> list[RentalPoint]:
    out: list[RentalPoint] = []
    try:
        pts = load_points(_yymmdd_to_label(month_end_yymmdd), data_dir=leasing_dir)
    except Exception:
        pts = []
    od = [p for p in pts if p.gpu_class == "gpu" and p.model in models]
    if od:
        med = statistics.median(p.usd_per_gpu_hour for p in od)
        used = max(p.price_date for p in od)
        model = sorted({p.model for p in od})[0]
        out.append(RentalPoint("on_demand", model, used, med, "pricefeed"))
    out += _spot_points(leasing_dir, models, month_end_yymmdd)
    out += _term_points(leasing_dir, models, month_end_yymmdd)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/test_price_local.py tests/test_pricefeed*.py -v`
Expected: all pass, including pricefeed's own untouched suite. Note: the on-demand fixture relies on `load_points` parsing `aws_price.csv` — if pricefeed's AWS reader requires columns the fixture lacks, extend the FIXTURE to match its real expectations (read `_aws_points` first); never modify pricefeed.

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/price_local.py tests/test_price_local.py
git commit -m "feat(f98): rental modality readers - on-demand, spot, 1-year term"
```

---

### Task 3: Series emission + `price-sync` CLI verb

**Files:**
- Modify: `gpu_agent/price_local.py`, `gpu_agent/cli.py` (append-only)
- Test: `tests/test_price_local.py` (append)

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces:
  - `latest_generation(benchmarks, hardware_points, as_of_yymmdd, max_age_days=90) -> dict | None` — highest-rank generation with a hardware point within the window.
  - `sync_series(data_dir, series_dir, as_of: str, benchmarks=None) -> dict` — writes/updates 4 series files, returns summary `{"written": {...}, "warnings": [...]}`:
    - `gpuSpotPrice.jsonl` — one reading per month (latest dated hardware value in that month, latest generation at that month; earlier months may be an older generation — the note says which), unit `USD`, `label` = benchmark label, `note` = generation + prior-gen context (`"hopper H100 NVL card $29,999 (prior gen)"` style).
    - `gpuRentalOnDemand.jsonl`, `gpuRentalSpot.jsonl`, `gpuRental1yr.jsonl` — unit `USD_per_hr`, `label` like `"B200 on-demand rent"`.
    - Idempotent: existing months other than the current `as_of` month are NEVER rewritten; the current month's row is replaced in place. First run backfills all months present in the data.
    - Staleness: newest data date older than 45 days vs `as_of` → a warning string in the summary (and nothing new written for the current month).
  - CLI: `price-sync` verb — `--data` (default the real leasing dir), `--series` (default `store/series`), `--as-of` (default: today's ISO date, computed at the CLI edge only).

- [ ] **Step 1: Write the failing tests** (append)

```python
from gpu_agent.price_local import latest_generation, sync_series


def test_latest_generation_rolls_with_freshness(tmp_path):
    hw = [HardwarePoint("hopper", "H100 NVL card", "260701", 29999.0, "f", "r"),
          HardwarePoint("blackwell", "B200 platform, per GPU", "260305",
                        32516.0, "f", "r")]
    # blackwell newest reading is >90d old at 2026-07-08 -> hopper wins
    g = latest_generation(BENCH, hw, "260708")
    assert g["id"] == "hopper"
    hw.append(HardwarePoint("blackwell", "B200 platform, per GPU", "260630",
                            32516.0, "f", "r"))
    assert latest_generation(BENCH, hw, "260708")["id"] == "blackwell"
    assert latest_generation(BENCH, [], "260708") is None


def test_sync_series_backfills_and_is_idempotent(tmp_path):
    d = _mk_leasing(tmp_path)
    _write_hw(tmp_path, ["NVIDIA H100 Card,30000.0,29500.0,29999.0",
                         "HGX B200 8-GPU,,260000.0,260128.0"])
    series = tmp_path / "series"
    s1 = sync_series(d, series, "2026-07-08", benchmarks=BENCH)
    rows = [json.loads(l) for l in
            (series / "gpuSpotPrice.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["period"] for r in rows] == ["2025-06", "2025-07", "2026-07"]
    assert rows[-1]["unit"] == "USD" and rows[-1]["label"]
    # blackwell has a fresh 2026-07 point -> latest month is blackwell per-GPU
    assert rows[-1]["value"] == pytest.approx(260128.0 / 8)
    assert "blackwell" in rows[-1]["note"]
    # rentals written too
    od = [json.loads(l) for l in
          (series / "gpuRentalOnDemand.jsonl").read_text(encoding="utf-8").splitlines()]
    assert od[-1]["unit"] == "USD_per_hr"
    # idempotent: run again, same as_of -> same row count, current month replaced
    s2 = sync_series(d, series, "2026-07-08", benchmarks=BENCH)
    rows2 = (series / "gpuSpotPrice.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows2) == len(rows)


def test_sync_series_stale_folder_warns_and_freezes(tmp_path):
    d = _mk_leasing(tmp_path)
    _write_hw(tmp_path, ["NVIDIA H100 Card,30000.0,29500.0,29999.0"])
    series = tmp_path / "series"
    out = sync_series(d, series, "2026-11-30", benchmarks=BENCH)   # data ends 260708
    assert any("stale" in w.lower() for w in out["warnings"])
    rows = [json.loads(l) for l in
            (series / "gpuSpotPrice.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(r["period"] != "2026-11" for r in rows)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/test_price_local.py -v`
Expected: new tests FAIL with `ImportError: cannot import name 'latest_generation'`

- [ ] **Step 3: Implement** (append to `price_local.py`; then the CLI verb)

```python
import datetime as _dt


def _yymmdd_date(yymmdd: str) -> _dt.date:
    return _dt.date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))


def latest_generation(benchmarks, hardware_points, as_of_yymmdd, max_age_days=90):
    cutoff = _yymmdd_date(as_of_yymmdd) - _dt.timedelta(days=max_age_days)
    for gen in benchmarks:                       # already rank-DESC
        pts = [p for p in hardware_points if p.generation == gen["id"]]
        if pts and _yymmdd_date(max(p.date for p in pts)) >= cutoff:
            return gen
    return None


def _month_of(yymmdd: str) -> str:
    return f"20{yymmdd[:2]}-{yymmdd[2:4]}"


def _read_jsonl(path: Path) -> list[dict]:
    try:
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
                if l.strip()]
    except OSError:
        return []


def _write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8", newline="\n")


def _upsert(path: Path, new_rows: list[dict], current_period: str):
    old = [r for r in _read_jsonl(path)
           if not (r.get("period") == current_period)]
    known = {r["period"] for r in old}
    merged = old + [r for r in new_rows
                    if r["period"] == current_period or r["period"] not in known]
    merged.sort(key=lambda r: r["period"])
    _write_jsonl(path, merged)


def _reading(indicator, period, value, unit, date_yymmdd, as_of, source_title,
             label, note):
    return {"indicatorId": indicator, "period": period, "value": round(value, 2),
            "unit": unit, "publishedAt": _yymmdd_date(date_yymmdd).isoformat(),
            "capturedAt": as_of, "source": {"url": "local:gpu_leasing_data",
                                            "title": source_title},
            "estimateGrade": True, "label": label, "note": note}


def sync_series(data_dir, series_dir, as_of, benchmarks=None):
    benchmarks = benchmarks or load_benchmarks()
    series_dir = Path(series_dir)
    as_of_yymmdd = as_of[2:4] + as_of[5:7] + as_of[8:10]
    current_period = as_of[:7]
    warnings = []

    hw = read_hardware_points(data_dir, benchmarks)
    written = {}

    newest = max((p.date for p in hw), default=None)
    stale = newest is None or \
        (_yymmdd_date(as_of_yymmdd) - _yymmdd_date(newest)).days > 45
    if stale:
        warnings.append(f"stale price folder: newest data {newest}, as_of {as_of}")

    # hardware series: per month, the latest point of the generation that was
    # 'latest' as of that month's end.
    months = sorted({_month_of(p.date) for p in hw})
    rows = []
    for m in months:
        if m == current_period and stale:
            continue
        m_end = f"{m[2:4]}{m[5:7]}31"
        gen = latest_generation(benchmarks, [p for p in hw if p.date <= m_end],
                                m_end)
        if gen is None:
            continue
        gpts = sorted([p for p in hw if p.generation == gen["id"]
                       and _month_of(p.date) == m], key=lambda p: p.date)
        if not gpts:
            continue
        top = gpts[-1]
        prior = [g for g in benchmarks if g["rank"] < gen["rank"]]
        note = f"generation={gen['id']}"
        if prior:
            pp = sorted([p for p in hw if p.generation == prior[0]["id"]
                         and p.date <= top.date], key=lambda p: p.date)
            if pp:
                note += (f"; prior gen {prior[0]['id']} "
                         f"{pp[-1].label} ${pp[-1].usd_per_gpu:,.0f}")
        rows.append(_reading("gpuSpotPrice", m, top.usd_per_gpu, "USD", top.date,
                             as_of, f"{top.source_file}: {top.row_name}",
                             top.label, note))
    _upsert(series_dir / "gpuSpotPrice.jsonl", rows, current_period)
    written["gpuSpotPrice"] = len(rows)

    # rental series: latest generation's models, one reading per month.
    gen_now = latest_generation(benchmarks, hw, as_of_yymmdd)
    models = set((gen_now or {}).get("rental", {}).get("models") or [])
    files = {"on_demand": "gpuRentalOnDemand.jsonl", "spot": "gpuRentalSpot.jsonl",
             "1yr": "gpuRental1yr.jsonl"}
    ids = {"on_demand": "gpuRentalOnDemand", "spot": "gpuRentalSpot",
           "1yr": "gpuRental1yr"}
    words = {"on_demand": "on-demand", "spot": "spot", "1yr": "1-year term"}
    if models:
        per_mod = {k: [] for k in files}
        for m in months:
            if m == current_period and stale:
                continue
            m_end = f"{m[2:4]}{m[5:7]}31"
            for rp in read_rental_points(data_dir, models, m_end):
                if _month_of(rp.date) != m:
                    continue
                per_mod[rp.modality].append(_reading(
                    ids[rp.modality], m, rp.usd_per_gpu_hour, "USD_per_hr",
                    rp.date, as_of, rp.source,
                    f"{rp.model} {words[rp.modality]} rent",
                    f"generation={(gen_now or {}).get('id', '')}"))
        for mod, fname in files.items():
            _upsert(series_dir / fname, per_mod[mod], current_period)
            written[ids[mod]] = len(per_mod[mod])

    return {"written": written, "warnings": warnings}
```

`gpu_agent/cli.py` (append-only, matching the `site` verb's pattern — handler near `_site`, parser near the `site` parser, dispatch near `if args.cmd == "site"`):

```python
def _price_sync(args):
    from gpu_agent.price_local import DEFAULT_LEASING_DIR, sync_series
    as_of = args.as_of
    if not as_of:
        import datetime
        as_of = datetime.date.today().isoformat()   # wall-clock isolated here only
    out = sync_series(args.data or DEFAULT_LEASING_DIR, args.series, as_of)
    for w in out["warnings"]:
        print(f"[price-sync] WARNING: {w}")
    print(f"[price-sync] written={out['written']} as_of={as_of}")
    return 0
```

```python
    ps = sub.add_parser("price-sync",
                        help="F98: local price folder -> store/series (renderer-side)")
    ps.add_argument("--data", default=None)
    ps.add_argument("--series", default="store/series")
    ps.add_argument("--as-of", dest="as_of", default=None)
```

```python
    if args.cmd == "price-sync":
        return _price_sync(args)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/test_price_local.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/price_local.py gpu_agent/cli.py tests/test_price_local.py
git commit -m "feat(f98): sync_series emission + price-sync CLI verb"
```

---

### Task 4: Agenda unit hygiene, labels, delta lines

**Files:**
- Modify: `gpu_agent/dashboard/agenda.py`, `gpu_agent/dashboard/brief_render.py`, `gpu_agent/dashboard/brief_model.py`
- Test: `tests/dashboard/test_agenda.py`, `tests/dashboard/test_brief_render.py` (append)

**Interfaces:**
- Consumes: shipped F97 `agenda.py` (`Candidate`, `_UNIT_FMT`, `format_value`, `_series_candidate`, `candidates_for_slot`), `brief_model.build_brief_model`, `brief_render` tile renderers.
- Produces (all additive; existing F97 tests must keep passing):
  - `_UNIT_ALIASES = {"USD billion": "USD_B", "USD_billion": "USD_B", "percent": "pct"}` applied at the top of `format_value`.
  - New `_UNIT_FMT` entries: `"USD": lambda n: f"${n:,.0f}"` (≥ 1e6 → `f"${n/1e6:.1f}M"`), `"flops_per_USD": lambda n: f"{n/1e9:,.0f} GFLOPS/$"`.
  - `WORD_UNITS = {"credit_condition_index": {1: "loosening", 0: "neutral", -1: "tightening"}, "revision_direction": {1: "raised", 0: "held", -1: "cut"}}` — `format_value` returns the WORD alone for these units (int(round(number)) lookup; out-of-range → `f"{n:g} {unit}"`).
  - `Candidate` gains `delta_line: str = ""` (default keeps F97 construction sites valid).
  - `_series_candidate`: `label` = `newest.get("label") or indicator_id`; `delta_line` computed vs the newest row ≥ 80 days older than the newest reading (money units → `f"{pct:+.0f}% vs {month_name}"`; word-unit/absent prior → `""`).
  - `candidates_for_slot(slot, findings, series_rows, labels=None)` — optional `labels: dict[str, str]`; finding-candidates get `label = labels.get(indicator_id, indicator_id)`.
  - `brief_model.build_brief_model`: builds `labels` from `IndicatorRegistry.load(REGISTRY_PATH)` entries' `label` field (lazy import, `try/except` → `{}`) and passes it through; occupant projection carries `delta_line`.
  - `brief_render`: tile renders `delta_line` in a `.meta` div when non-empty; tile-label lint — `lint_exec_copy` unchanged, but a NEW check `lint_tile_labels(model) -> list[str]` flags any agenda `metric_label` matching `\b[DSPX]\d{1,2}\b`; `site_build`'s existing gate extends to include it.

- [ ] **Step 1: Write the failing tests** (append; exact expectations)

```python
# tests/dashboard/test_agenda.py additions
def test_format_value_aliases_and_new_units():
    assert format_value(500.0, "USD billion") == "$500B"
    assert format_value(29999.0, "USD") == "$29,999"
    assert format_value(2.09e11, "flops_per_USD") == "209 GFLOPS/$"
    assert format_value(1.0, "credit_condition_index") == "loosening"
    assert format_value(-1.0, "revision_direction") == "cut"
    assert format_value(7.0, "credit_condition_index") == "7 credit_condition_index"


def test_series_candidate_label_and_delta(tmp_path):
    rows = [
        {"indicatorId": "gpuSpotPrice", "period": "2026-04", "value": 34000.0,
         "unit": "USD", "publishedAt": "2026-04-30", "label": "H100 NVL card"},
        {"indicatorId": "gpuSpotPrice", "period": "2026-07", "value": 29999.0,
         "unit": "USD", "publishedAt": "2026-07-08", "label": "H100 NVL card"},
    ]
    got = candidates_for_slot(
        {"id": "x", "label": "X", "question": "q", "indicators": ["gpuSpotPrice"]},
        [], {"gpuSpotPrice": rows})
    c = got[0]
    assert c.label == "H100 NVL card"
    assert c.delta_line == "-12% vs Apr"


def test_finding_candidate_plain_label():
    got = candidates_for_slot(SLOT, [F_MEASURED], {},
                              labels={"D2": "DC revenue structure"})
    assert got[0].label == "DC revenue structure"
```

```python
# tests/dashboard/test_brief_render.py additions
from gpu_agent.dashboard.brief_render import lint_tile_labels


def test_tile_renders_delta_line():
    m = dict(MODEL)
    m["agenda"] = [dict(MODEL["agenda"][0], delta_line="-12% vs Apr")] + \
        MODEL["agenda"][1:]
    assert "-12% vs Apr" in render_brief(m)


def test_lint_tile_labels_flags_raw_codes():
    assert lint_tile_labels({"agenda": [{"metric_label": "D2"}]})
    assert lint_tile_labels({"agenda": [{"metric_label": "DC revenue structure"}]}) == []
```

(Also update the `MODEL` fixture's agenda dicts to include `"delta_line": ""` so the renderer test data matches the projection.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_agenda.py tests/dashboard/test_brief_render.py -v`
Expected: new tests FAIL (`KeyError`/`AssertionError`/`ImportError: lint_tile_labels`).

- [ ] **Step 3: Implement**

In `agenda.py` — replace `format_value` and extend:

```python
_UNIT_ALIASES = {"USD billion": "USD_B", "USD_billion": "USD_B", "percent": "pct"}

WORD_UNITS = {
    "credit_condition_index": {1: "loosening", 0: "neutral", -1: "tightening"},
    "revision_direction": {1: "raised", 0: "held", -1: "cut"},
}

_UNIT_FMT.update({
    "USD": lambda n: f"${n/1e6:.1f}M" if abs(n) >= 1e6 else f"${n:,.0f}",
    "flops_per_USD": lambda n: f"{n/1e9:,.0f} GFLOPS/$",
})


def format_value(number: float, unit: str) -> str:
    unit = _UNIT_ALIASES.get(unit, unit)
    words = WORD_UNITS.get(unit)
    if words is not None:
        w = words.get(int(round(number)))
        if w is not None:
            return w
        return f"{number:g} {unit}"
    fmt = _UNIT_FMT.get(unit)
    if fmt is not None:
        return fmt(number)
    return f"{number:g} {unit}"   # unknown unit: value + unit verbatim, never bare
```

`Candidate` gains `delta_line: str = ""` (LAST field, keeping positional construction valid). `_series_candidate` additions:

```python
_MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
               "Sep", "Oct", "Nov", "Dec"]


def _delta_line(rows: list[dict]) -> str:
    if len(rows) < 2:
        return ""
    newest = rows[-1]
    unit = _UNIT_ALIASES.get(str(newest.get("unit") or ""), newest.get("unit"))
    if unit in WORD_UNITS or not isinstance(newest.get("value"), (int, float)):
        return ""
    nd = _days_key(newest)
    base = None
    for r in rows[-2::-1]:
        if isinstance(r.get("value"), (int, float)) and _days_key(r) is not None \
                and nd is not None and (nd - _days_key(r)).days >= 80:
            base = r
            break
    if base is None or not base["value"]:
        return ""
    pct = (newest["value"] - base["value"]) / abs(base["value"]) * 100
    month = _MONTH_ABBR[int((base.get("period") or "0000-01")[5:7])]
    return f"{pct:+.0f}% vs {month}"


def _days_key(row):
    s = row.get("publishedAt") or (row.get("period", "") + "-15")
    try:
        y, m, d = (int(x) for x in s[:10].split("-"))
        return _dt.date(y, m, d)
    except (ValueError, IndexError):
        return None
```

(`_series_candidate` sets `label=newest.get("label") or indicator_id`, `delta_line=_delta_line(rows)`. The test expects `-12% vs Apr`: `f"{pct:+.0f}"` renders negatives with a plain minus sign, matching directly.)

`candidates_for_slot(slot, findings, series_rows, labels=None)` passes `labels.get(f["indicatorId"], f["indicatorId"])` into `_finding_candidate` (add a `label` parameter to it). In `brief_model.build_brief_model`: build `labels` via

```python
def _indicator_labels():
    try:
        from gpu_agent.config import REGISTRY_PATH
        from gpu_agent.registry.indicators import IndicatorRegistry
        reg = IndicatorRegistry.load(REGISTRY_PATH)
        return {k: v.label for k, v in reg.indicators.items() if v.label}
    except Exception:
        return {}
```

(verify the registry object's attribute shape — `reg.indicators` dict of models with `.label`; adjust to the real API in `gpu_agent/registry/indicators.py` before writing) — pass into `select_occupants`→`_pick`→`candidates_for_slot`, and project `"delta": o.candidate.delta_line` into the agenda dicts (renderer key `delta_line`, match the render test).

In `brief_render.py`: tile adds `<div class="meta">{e(o["delta_line"])}</div>` when non-empty, plus:

```python
_TILE_CODE = re.compile(r"\b[DSPX]\d{1,2}\b")


def lint_tile_labels(model) -> list[str]:
    return [o["metric_label"] for o in (model.get("agenda") or [])
            if _TILE_CODE.search(o.get("metric_label") or "")]
```

In `site_build.py`, extend the existing lint gate: `lint = lint_exec_copy(brief_html) + lint_tile_labels(brief_model)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/ -v`
Expected: all pass including the untouched F97 suite.

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/ tests/dashboard/
git commit -m "feat(f98): unit aliases/word-maps, plain labels, tile delta lines, tile-label lint"
```

---

### Task 5: Slot-family config update

**Files:**
- Modify: `registry/agenda-slots.json`
- Test: `tests/dashboard/test_agenda.py` (append)

**Interfaces:** consumes `load_slots()`; produces the spec §3 table as data.

- [ ] **Step 1: Write the failing test** (append)

```python
def test_real_slot_families_match_f98_spec():
    fam = {s["id"]: set(s["indicators"]) for s in load_slots()}
    assert "S9" in fam["customer-mix"] and "S9" not in fam["binding-constraint"]
    assert "S10" in fam["binding-constraint"]
    assert {"gpuSpotPrice", "gpuRentalOnDemand", "gpuRentalSpot", "gpuRental1yr",
            "flopsPerDollar"} <= fam["end-market-economics"]
    assert "apiArr" in fam["demand-quality"]
    assert "releaseCadence" in fam["demand-durability"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_agenda.py::test_real_slot_families_match_f98_spec -v`
Expected: FAIL (S9 still in binding-constraint).

- [ ] **Step 3: Edit `registry/agenda-slots.json`**

Apply exactly: remove `"S9"` from binding-constraint; add `"S9"` to customer-mix; append `"gpuSpotPrice", "gpuRentalOnDemand", "gpuRentalSpot", "gpuRental1yr", "flopsPerDollar"` to end-market-economics; append `"apiArr"` to demand-quality; append `"releaseCadence"` to demand-durability. No other changes.

- [ ] **Step 4: Run tests**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/ -v` — all pass (if an F97 test pinned the old families, update it to the new table — the change IS the feature).

- [ ] **Step 5: Commit**

```bash
git add registry/agenda-slots.json tests/dashboard/test_agenda.py
git commit -m "feat(f98): slot-family fixes - S9 to customer-mix; price/apiArr/releaseCadence slotted"
```

---

### Task 6: Gather-manifest sources for apiArr + releaseCadence

**Files:**
- Modify: `manifests/chips.merchant-gpu.json`
- Test: `tests/test_manifest_f98.py` (create)

**Interfaces:** consumes `gpu_agent.manifest.load_manifest` (pydantic validation is the gate).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_manifest_f98.py
from gpu_agent.manifest import load_manifest


def test_manifest_covers_apiArr_and_releaseCadence():
    m = load_manifest("manifests/chips.merchant-gpu.json")
    listed = {i.indicatorId for i in m.expectedIndicators}
    assert {"apiArr", "releaseCadence"} <= listed
    covered = {ind for s in m.expectedSources for ind in s.indicators}
    assert {"apiArr", "releaseCadence"} <= covered
```

(Verify `ExpectedIndicator`/`ExpectedSource` field names against `gpu_agent/manifest.py` before finalizing — `indicatorId` and `indicators` per the schema read on 2026-07-17.)

- [ ] **Step 2: Run to verify it fails**, then **Step 3: Edit the manifest** — add to `expectedIndicators`: `{"indicatorId": "apiArr"}`-shaped entries matching existing ones (copy an existing entry's full shape); add two `expectedSources` entries matching the existing schema exactly (id/label/urlPatterns/accessMethod/tier/costUsd/license/refresh/indicators):
  - `ai-app-revenue` — hyperscaler AI run-rate + model-lab ARR disclosure coverage (urlPatterns e.g. `microsoft.com`, `blogs.microsoft.com`, `openai.com`, `anthropic.com`, plus reputable coverage domains already used elsewhere in the manifest), `tier: "secondary"`, `refresh: "quarterly"`, `indicators: ["apiArr"]`.
  - `frontier-release-funding` — frontier model release/funding trackers (company newsrooms + the industry-press domains already present in the manifest), `refresh: "event"` if that enum value exists in `ExpectedSource` (check the pydantic model; else use the closest allowed value), `indicators: ["releaseCadence"]`.
- [ ] **Step 4: Run** `../../.venv/Scripts/python -m pytest tests/test_manifest_f98.py tests/ -k manifest -v` — pass (pydantic accepts the entries).
- [ ] **Step 5: Commit**

```bash
git add manifests/chips.merchant-gpu.json tests/test_manifest_f98.py
git commit -m "feat(f98): manifest sources for apiArr and releaseCadence"
```

---

### Task 7: run-cycle step + F83 fingerprint lockstep

**Files:**
- Modify: `.claude/skills/run-cycle/SKILL.md`, `tests/test_run_cycle_conformance.py`

- [ ] **Step 1:** Read `tests/test_run_cycle_conformance.py` (EXPECTED_STEPS + how the fingerprint is computed) and the run-cycle SKILL Procedure list.
- [ ] **Step 2:** Add one Procedure step immediately BEFORE the site-rebuild step: `price-sync — refresh local price series: ../../.venv/Scripts/python -m gpu_agent.cli price-sync --as-of <cycle asOf>; warnings are logged, never fatal.` (match the surrounding steps' exact prose style).
- [ ] **Step 3:** Regenerate the fingerprint AND `EXPECTED_STEPS` in lockstep, exactly as the fingerprint comment in SKILL.md line ~52 instructs. Run `../../.venv/Scripts/python -m pytest tests/test_run_cycle_conformance.py -v` → pass. A red F83 conformance here means the two moved out of lockstep — fix, never skip.
- [ ] **Step 4: Commit**

```bash
git add .claude/skills/run-cycle/SKILL.md tests/test_run_cycle_conformance.py
git commit -m "feat(f98): run-cycle price-sync step + F83 fingerprint re-record"
```

---

### Task 8: Real-store smoke + full suite

- [ ] **Step 1:** From the worktree, run `../../.venv/Scripts/python -m gpu_agent.cli price-sync --as-of 2026-07-17` (real folder → real `store/series/`). Expected: `written` counts > 0 for gpuSpotPrice + at least on_demand; warnings empty. Inspect `store/series/gpuSpotPrice.jsonl` head/tail: backfill from 2025-02, latest month present, labels/notes sensible, no absurd values (the $3,498 row must be absent).
- [ ] **Step 2:** Rebuild the site: `../../.venv/Scripts/python -m gpu_agent.cli site --category chips.merchant-gpu --store store/chips.merchant-gpu --work work --out work/site-smoke`. Read `work/site-smoke/chips.merchant-gpu/index.html`: End-market-economics tile shows a real `$` price with benchmark label + delta line; no "USD billion", no "credit_condition_index", no raw indicator-id labels; `(was: …)` notes plausible.
- [ ] **Step 3:** Full suite `../../.venv/Scripts/python -m pytest -q` → green (skips ok); **F6 pin green untouched**; F83 conformance green.
- [ ] **Step 4:** Commit the store series artifacts (they are committed data, per repo rule "a cycle that isn't committed didn't happen"):

```bash
git add store/series/
git commit -m "data(f98): initial price-sync backfill - gpuSpotPrice + rental modality series"
```

---

### Task 9: Lane close-out

- [ ] Tick F98 Part A in `docs/fix-backlog.md` (Part B stays open); note any deviations.
- [ ] Write `.superpowers/handoffs/f98-agenda-data-DONE.md` (what shipped, decisions, test counts, branch; NOT merged — stop-before-merge).
- [ ] Update `docs/superpowers/HANDOFF.md` top line + session bullet + coordination entry.
- [ ] `git push -u origin f98-agenda-data`; report to the user with merge decision pending. Deploy note: the live page changes only after merge + a cycle rebuilds `site/`.

---

## Self-review notes (plan-time)

- **Spec coverage:** benchmark config + curation (T1), modalities incl. 1-year term (T2), series + backfill + staleness + CLI (T3), unit hygiene/aliases/word-maps/labels/delta/lint (T4), slot table (T5), manifest (T6), cycle integration + F83 lockstep (T7), acceptance criteria 1–10 land across T1–T8 (generation-roll = T3 test; curation = T1 test; "500 USD billion"/"credit_condition_index" = T4 tests; staleness = T3 test; F6/F83 = T7/T8).
- **Known verify-before-write points (explicit, not placeholders):** exact CSV row strings (T1 Step 3), pricefeed's `_aws_points` fixture expectations (T2 Step 4), `IndicatorRegistry` attribute shape (T4), manifest pydantic field names/enums (T6), fingerprint regeneration mechanics (T7). Each is a read-then-pin instruction against a file in the repo, with the authoritative source named.
- **Type consistency:** `Candidate.delta_line` added LAST with a default — F97 call sites and tests unaffected; `candidates_for_slot(labels=None)` optional — F97 signature compatible; series row `label` optional — existing six series files unaffected; `sync_series` returns `{"written", "warnings"}` used by both CLI and tests.
