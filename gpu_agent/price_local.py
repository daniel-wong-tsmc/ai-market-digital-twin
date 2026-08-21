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
    dates_models = []
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
        dates_models.append((d, model))
    if not per_gpu:
        return []
    # Task-2-review carry-in (correction #2, resolved in scope for Task 3): report
    # the NEWEST matched date (consistent with _spot_points/on-demand), not
    # whichever row happened to be iterated last -- otherwise sync_series's
    # per-month `_month_of(rp.date) != m` filter could drop a valid blended 1yr
    # reading because the reported date landed in the wrong month.
    used_date = max(d for d, _ in dates_models)
    model = sorted({mdl for d, mdl in dates_models if d == used_date})[0]
    return [RentalPoint("1yr", model, used_date,
                        statistics.median(per_gpu), "aws_price.csv")]


def _snapshot_rental(snapshot_dir, models, month_end_yymmdd, price_type, modality):
    """F122: one RentalPoint (median $/GPU-hr) for `modality` from the newest daily
    snapshot at/before the month end — on-demand/spot/reserved_1yr rows, US regions only."""
    from gpu_agent.pricefeed import (_is_us_region, _match_model, _money, _snapshot_date_yymmdd,
                                     _snapshot_file)
    path = _snapshot_file(_yymmdd_to_label(month_end_yymmdd), snapshot_dir)
    if path is None:
        return []
    vals, found = [], set()
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("price_type") or "") != price_type:
                continue
            if not _is_us_region(r.get("provider") or "", r.get("region") or ""):
                continue
            model = _match_model(r.get("gpu_model") or "")
            if model not in models:
                continue
            price = _money(r.get("usd_per_gpu_hr"))
            if price is None or price <= 0:
                continue
            vals.append(price)
            found.add(model)
    if not vals:
        return []
    return [RentalPoint(modality, sorted(found)[0], _snapshot_date_yymmdd(path),
                        statistics.median(vals), path.name)]


def read_rental_points(leasing_dir, models, month_end_yymmdd, snapshot_dir=None) -> list[RentalPoint]:
    """Rental readings for `models` at the month end. `snapshot_dir=None` -> legacy folders
    only (hermetic for tests); the CLI passes the real snapshot folder. When a snapshot
    exists it is the source for every modality; legacy files are the fallback per modality."""
    out: list[RentalPoint] = []
    label = _yymmdd_to_label(month_end_yymmdd)
    try:
        if snapshot_dir is not None:
            pts = load_points(label, data_dir=leasing_dir, snapshot_dir=snapshot_dir)
        else:
            pts = load_points(label, data_dir=leasing_dir, snapshot_dir=Path("__no_snapshots__"))
    except Exception:
        pts = []
    od = [p for p in pts if p.gpu_class == "gpu" and p.model in models]
    if od:
        med = statistics.median(p.usd_per_gpu_hour for p in od)
        used = max(p.price_date for p in od)
        model = sorted({p.model for p in od})[0]
        out.append(RentalPoint("on_demand", model, used, med, "pricefeed"))
    spot = _snapshot_rental(snapshot_dir, models, month_end_yymmdd, "spot", "spot") \
        if snapshot_dir is not None else []
    out += spot or _spot_points(leasing_dir, models, month_end_yymmdd)
    term = _snapshot_rental(snapshot_dir, models, month_end_yymmdd, "reserved_1yr", "1yr") \
        if snapshot_dir is not None else []
    out += term or _term_points(leasing_dir, models, month_end_yymmdd)
    return out


# --- Task 3: series emission + price-sync CLI verb ----------------------------------

import calendar
import datetime as _dt


def _yymmdd_date(yymmdd: str) -> _dt.date:
    return _dt.date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))


def latest_generation(benchmarks, hardware_points, as_of_yymmdd, max_age_days=90):
    """Highest-rank generation with a hardware point inside the freshness window.

    Sorts `benchmarks` by rank descending internally rather than trusting the
    caller's ordering -- `load_benchmarks()` already returns rank-DESC, but this
    keeps the contract ("highest-rank generation ... in window") correct even
    when callers (or tests) pass an unsorted list.
    """
    cutoff = _yymmdd_date(as_of_yymmdd) - _dt.timedelta(days=max_age_days)
    for gen in sorted(benchmarks, key=lambda g: -g["rank"]):
        pts = [p for p in hardware_points if p.generation == gen["id"]]
        if pts and _yymmdd_date(max(p.date for p in pts)) >= cutoff:
            return gen
    return None


def _month_of(yymmdd: str) -> str:
    return f"20{yymmdd[:2]}-{yymmdd[2:4]}"


def _month_end_yymmdd(period: str) -> str:
    """True calendar last day of `period` ("YYYY-MM") as a YYMMDD string.

    Correction (Task-3 orchestrator fix #1): the plan's reference code used a
    naive f"{m[2:4]}{m[5:7]}31", which raises ValueError via _yymmdd_date for
    any 30-day month or February (e.g. June -> "250631" is not a real date).
    calendar.monthrange gives the real last day for every month.
    """
    year, month = int(period[:4]), int(period[5:7])
    last_day = calendar.monthrange(year, month)[1]
    return f"{period[2:4]}{period[5:7]}{last_day:02d}"


def _read_jsonl(path: Path) -> list[dict]:
    try:
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
                if l.strip()]
    except (OSError, ValueError):
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
    if not merged:
        # No rows at all (no prior data, no new data): leave no file on disk
        # rather than committing an empty series (M2) -- a modality that never
        # surfaces data (e.g. no GPU spot listings) should have no series file.
        return
    merged.sort(key=lambda r: r["period"])
    _write_jsonl(path, merged)


def _reading(indicator, period, value, unit, date_yymmdd, as_of, source_title,
             label, note):
    return {"indicatorId": indicator, "period": period, "value": round(value, 2),
            "unit": unit, "publishedAt": _yymmdd_date(date_yymmdd).isoformat(),
            "capturedAt": as_of, "source": {"url": "local:gpu_leasing_data",
                                            "title": source_title},
            "estimateGrade": True, "label": label, "note": note}


def _parse_as_of(as_of: str) -> str | None:
    """`as_of` -> YYMMDD, tolerant of month-grain input, never raising.

    `YYYY-MM-DD` is validated via a real `datetime.date` round-trip (not
    slicing) so malformed day-grain input (e.g. "2026-07-99") is rejected
    rather than silently truncated. `YYYY-MM` resolves to that month's true
    calendar last day via `_month_end_yymmdd`. Anything else -> None.
    """
    try:
        d = _dt.date.fromisoformat(as_of)
        return f"{d.year % 100:02d}{d.month:02d}{d.day:02d}"
    except ValueError:
        pass
    try:
        year_s, month_s = as_of.split("-")
        if len(year_s) == 4 and len(month_s) == 2:
            year, month = int(year_s), int(month_s)
            if 1 <= month <= 12:
                return _month_end_yymmdd(as_of)
    except ValueError:
        pass
    return None


def sync_series(data_dir, series_dir, as_of, benchmarks=None, snapshot_dir=None):
    benchmarks = benchmarks or load_benchmarks()
    series_dir = Path(series_dir)
    warnings = []
    as_of_yymmdd = _parse_as_of(as_of)
    if as_of_yymmdd is None:
        warnings.append(f"price-sync: unusable as-of {as_of!r} — skipped (no rows written)")
        return {"written": {}, "warnings": warnings}
    current_period = as_of[:7]

    hw = read_hardware_points(data_dir, benchmarks)
    written = {}

    newest = max((p.date for p in hw), default=None)
    stale = newest is None or \
        (_yymmdd_date(as_of_yymmdd) - _yymmdd_date(newest)).days > 45
    if stale:
        warnings.append(f"stale price folder: newest data {newest}, as_of {as_of}")

    # hardware series: per month, the latest point of the generation that was
    # 'latest' as of that month's end.
    # F122: rental months are no longer bounded by the hardware folder — the current
    # period is always considered so fresh rental snapshots can write even when the
    # hardware (purchase-price) folder is stale.
    months = sorted({_month_of(p.date) for p in hw} | {current_period})
    rows = []
    for m in months:
        if m == current_period and stale:
            continue
        m_end = _month_end_yymmdd(m)
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

    # Rental series: one reading per month, per modality. For each month, roll
    # down the rank ladder (the same pattern latest_generation uses for hardware)
    # until we find a generation whose OWN rental models actually surface CSV
    # data for that month -- never query more than one generation's models at
    # once, since blending two generations' models into a single median would
    # silently average together prices for physically different GPUs. Rolling
    # down also handles hardware/spot pricing for a new generation going live
    # before that generation is actually rentable anywhere: the freshest hw
    # generation is tried first, and we fall back to the next-highest-rank
    # generation only if it has no rental signal yet for that month.
    files = {"on_demand": "gpuRentalOnDemand.jsonl", "spot": "gpuRentalSpot.jsonl",
             "1yr": "gpuRental1yr.jsonl"}
    ids = {"on_demand": "gpuRentalOnDemand", "spot": "gpuRentalSpot",
           "1yr": "gpuRental1yr"}
    words = {"on_demand": "on-demand", "spot": "spot", "1yr": "1-year term"}
    ranked_gens = sorted(benchmarks, key=lambda g: -g["rank"])
    any_rental_configured = any((g.get("rental") or {}).get("models")
                                for g in ranked_gens)
    if any_rental_configured:
        per_mod = {k: [] for k in files}
        rental_cutoff = _yymmdd_date(as_of_yymmdd) - _dt.timedelta(days=45)
        current_month_fresh = False
        for m in months:
            m_end = _month_end_yymmdd(m)
            month_pts, used_gen = [], None
            for gen in ranked_gens:
                gmodels = set((gen.get("rental") or {}).get("models") or [])
                if not gmodels:
                    continue
                pts = [rp for rp in read_rental_points(data_dir, gmodels, m_end,
                                                       snapshot_dir=snapshot_dir)
                       if _month_of(rp.date) == m]
                if m == current_period:
                    # F122: the current month's rental rows are gated by RENTAL freshness,
                    # not by the hardware folder's staleness.
                    pts = [rp for rp in pts if _yymmdd_date(rp.date) >= rental_cutoff]
                if pts:
                    month_pts, used_gen = pts, gen
                    break
            if m == current_period and month_pts:
                current_month_fresh = True
            for rp in month_pts:
                per_mod[rp.modality].append(_reading(
                    ids[rp.modality], m, rp.usd_per_gpu_hour, "USD_per_hr",
                    rp.date, as_of, rp.source,
                    f"{rp.model} {words[rp.modality]} rent",
                    f"generation={used_gen['id']}"))
        if not current_month_fresh:
            warnings.append(f"stale rental data: no rental reading within 45 days of as_of {as_of}")
        for mod, fname in files.items():
            _upsert(series_dir / fname, per_mod[mod], current_period)
            written[ids[mod]] = len(per_mod[mod])

    return {"written": written, "warnings": warnings}
