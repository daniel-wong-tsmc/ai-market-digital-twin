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


# --- Task 2: rental-modality readers (on-demand / spot / 1-year) --------------------

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
