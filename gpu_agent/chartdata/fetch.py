"""F110 Task 4: chart-data fetch framework.

This module decides which chart series are due for a refresh and drives the
actual fetch + append. It runs inside the unattended daily pipeline, so the
single rule that matters more than any other: ``run_fetch`` NEVER raises. A
broken web page, a network error, an unparseable table -- all of it degrades
to "no new data for this series" (reported under ``failed``), never to a
crashed daily run.

No wall-clock reads: ``as_of_date`` is always a parameter, exactly like
price_local.sync_series.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Callable

from gpu_agent.chartdata.registry import ChartSeries

DEFAULT_STORE_DIR = "store/series"
# quarterly series are due when as_of is this many days (inclusive) from a
# known earnings date -- wide enough to survive a same-week re-run, narrow
# enough that a fetch attempt outside earnings season is never mistaken for
# "due".
_EARNINGS_WINDOW_DAYS = 3


class ParseFailed(Exception):
    """Raised by a fetcher's ``parse()`` when the saved/fetched HTML doesn't
    match the markup shape the parser expects. Caught by ``run_fetch`` and
    turned into a 'failed' entry -- never allowed to propagate."""


def _parse_date(s: str) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def due_series(
    series: dict[str, ChartSeries],
    as_of_date: str,
    earnings_dates: list[str],
    store_dir: str = DEFAULT_STORE_DIR,
) -> list[ChartSeries]:
    """Which chart series are due for a fetch attempt as of `as_of_date`.

    - fetcher is None (no fetcher wired up yet, e.g. nvdaDataCenterRevenue):
      never due -- there is nothing that could fetch it.
    - cadence == 'monthly': never due here -- price-sync (gpu_agent/price_local.py)
      owns those series end to end.
    - cadence == 'quarterly': due when `as_of_date` falls within
      +/-_EARNINGS_WINDOW_DAYS days of any of `earnings_dates`, OR the
      series' store file is missing entirely (first-ever fetch, or a file
      that was never written because the series has no history yet).

    Returns series sorted by id for deterministic output; `store_dir` scopes
    the missing-file check to a caller-chosen store root (tests pass a tmp
    dir; the CLI passes the real store).
    """
    as_of = _parse_date(as_of_date)
    if as_of is None:
        return []

    earnings = [d for d in (_parse_date(s) for s in earnings_dates) if d is not None]
    store_path = Path(store_dir)

    out = []
    for series_id in sorted(series):
        cs = series[series_id]
        if cs.fetcher is None:
            continue
        if cs.cadence != "quarterly":
            continue
        file_missing = not (store_path / f"{cs.id}.jsonl").exists()
        near_earnings = any(abs((as_of - e).days) <= _EARNINGS_WINDOW_DAYS
                             for e in earnings)
        if file_missing or near_earnings:
            out.append(cs)
    return out


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    except (OSError, ValueError):
        return []


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                     encoding="utf-8", newline="\n")


def _row(cs: ChartSeries, point: dict, as_of_date: str) -> dict:
    """One point (as returned by a fetcher's parse()) -> the on-disk series
    row shape, matched against store/series/hyperscalerCapexRevision.jsonl --
    the closest existing analog (quarterly, hard-fact, earnings-sourced)."""
    return {
        "indicatorId": cs.id,
        "period": point["period"],
        "value": round(float(point["value"]), 3),
        "unit": point.get("unit", cs.unit),
        "publishedAt": point["publishedAt"],
        "capturedAt": as_of_date,
        "source": {
            "url": point.get("sourceUrl", cs.sourceUrl),
            "title": point.get("title", cs.sourceName),
        },
        "estimateGrade": False,
        "note": f"{cs.sourceName}: {cs.name}, {point['period']}",
    }


def _append_points(store_dir: str, cs: ChartSeries, points: list[dict],
                    as_of_date: str) -> int:
    """Idempotent append: existing (indicatorId, period) rows are never
    rewritten; only genuinely new periods are added. Returns the count of
    newly-added rows (0 on a rerun with nothing new -- this is what makes
    running run_fetch twice a no-op on the file)."""
    path = Path(store_dir) / f"{cs.id}.jsonl"
    existing = _read_jsonl(path)
    known_periods = {r.get("period") for r in existing}
    new_rows = [_row(cs, p, as_of_date) for p in points
                if p.get("period") not in known_periods]
    if not new_rows:
        return 0
    # de-dup within the same fetch too (defensive: a parser that returns the
    # same period twice must not double-append it).
    seen = set()
    deduped = []
    for r in new_rows:
        key = (r["indicatorId"], r["period"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    merged = existing + deduped
    merged.sort(key=lambda r: r["period"])
    _write_jsonl(path, merged)
    return len(deduped)


def run_fetch(
    series: dict[str, ChartSeries],
    as_of_date: str,
    earnings_dates: list[str],
    store_dir: str,
    fetch_html: Callable[[str], str] | None = None,
) -> dict:
    """Fetch + append every due series. NEVER raises -- any failure (network,
    missing fetcher, unparseable markup, a bad point shape) is caught and
    reported under 'failed'; the series' file is left exactly as it was.

    Returns {'fetched': [{'id', 'newPoints'}], 'failed': [{'id', 'error'}],
    'skipped': [id, ...]} -- 'skipped' lists every registry series that
    wasn't due this call (wrong cadence, no fetcher, or outside the earnings
    window with an existing file).
    """
    # Local import: fetchers/amd_dc_revenue.py imports ParseFailed from this
    # module, so importing FETCHERS at module scope here would be circular.
    from gpu_agent.chartdata.fetchers import FETCHERS

    due = due_series(series, as_of_date, earnings_dates, store_dir=store_dir)
    due_ids = {cs.id for cs in due}
    fetched: list[dict] = []
    failed: list[dict] = []

    for cs in due:
        try:
            fetcher = FETCHERS.get(cs.fetcher)
            if fetcher is None:
                failed.append({"id": cs.id,
                                "error": f"no fetcher registered for {cs.fetcher!r}"})
                continue
            html_text = (fetch_html or _default_fetch_html)(cs.sourceUrl)
            points = fetcher(html_text)
            n_new = _append_points(store_dir, cs, points, as_of_date)
            fetched.append({"id": cs.id, "newPoints": n_new})
        except Exception as e:  # noqa: BLE001 -- deliberate: never let a
            # fetch failure escape into the unattended daily pipeline.
            failed.append({"id": cs.id, "error": f"{type(e).__name__}: {e}"})

    skipped = sorted(sid for sid in series if sid not in due_ids)
    return {"fetched": fetched, "failed": failed, "skipped": skipped}


def _default_fetch_html(url: str) -> str:  # pragma: no cover -- network path,
    # never exercised by tests; tests always inject fetch_html.
    import urllib.request
    with urllib.request.urlopen(url, timeout=20) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")
