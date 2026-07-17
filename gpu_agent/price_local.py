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
