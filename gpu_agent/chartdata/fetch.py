"""F110 Task 4: chart-data fetch framework.

This module decides which chart series are due for a refresh and drives the
actual fetch + append. It runs inside the unattended daily pipeline, so the
single rule that matters more than any other: ``run_fetch`` NEVER raises. A
broken web page, a network error, an unparseable table, a link-discovery
step (fix round 2) that can't find the page it's looking for -- all of it
degrades to "no new data for this series" (reported under ``failed``),
never to a crashed daily run.

No wall-clock reads: ``as_of_date`` is always a parameter, exactly like
price_local.sync_series.
"""
from __future__ import annotations

import datetime as _dt
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Callable

from gpu_agent.chartdata.registry import ChartSeries
from gpu_agent.manifest import earnings_window

DEFAULT_STORE_DIR = "store/series"
# F131 (user ruling 2026-08-31): the earnings window is FORWARD-ONLY -- a
# quarterly series is due from its print day E through E+_EARNINGS_WINDOW_DAYS
# inclusive, and never before E.
#
# It used to be symmetric (+/-3 days), which was wrong twice over: the three
# days before a print are dead weight (the numbers do not exist yet), and the
# window shut four days after the print, in the exact week the source page is
# freshest. The daily cycle does not run every day, so a window with only ~4
# usable days could miss a print for an entire quarter. 14 days forward gives
# the run a fortnight of chances; a re-fetch that finds nothing new is already
# a no-op thanks to the idempotent append in _append_points.
_EARNINGS_WINDOW_DAYS = 14


class ParseFailed(Exception):
    """Raised by a fetcher's ``parse()`` when the saved/fetched HTML doesn't
    match the markup shape the parser expects. Caught by ``run_fetch`` and
    turned into a 'failed' entry -- never allowed to propagate."""


class StalenessViolation(Exception):
    """F112(a): raised inside run_fetch's per-series loop when the newest
    period a fetcher parsed is strictly OLDER than the newest period already
    stored for that series -- i.e. link discovery landed on an old release.
    Caught by the same per-series except as every other failure and turned
    into a loud 'failed' entry (user-approved 2026-08-20: log-and-skip);
    same-or-newer passes, and an empty/missing store file passes vacuously."""


def _parse_date(s: str) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def not_fetchable(series: dict[str, ChartSeries]) -> list[ChartSeries]:
    """Series this module OWNS but has no way to fetch: quarterly, and no
    fetcher wired up (F131 -- nvdaDataCenterRevenue is the live example).

    Reported separately from 'not due this week' so a permanently-unfetchable
    series can't hide inside a routine skip. It did exactly that for three
    consecutive cycles before F131 was filed.

    Deliberately excludes monthly series: gpuSpotPrice has no fetcher here
    either, but it is not broken -- price-sync (gpu_agent/price_local.py) owns
    it end to end. Only a series chart-fetch is supposed to be able to get,
    and can't, belongs in this bucket.
    """
    return [series[sid] for sid in sorted(series)
            if series[sid].cadence == "quarterly" and series[sid].fetcher is None]


def has_usable_calendar_entry(cs: ChartSeries, as_of: _dt.date,
                               earnings_dates: Mapping[str, str]) -> bool:
    """Can this series still be scheduled off the earnings calendar as of
    `as_of`? (F131 Q5, user ruling 2026-08-31.)

    False in three cases, all of which mean "a person has to update the
    manifest before this series can ever refresh again":

      - the calendar has no entry for the series' `earningsKey`;
      - it has one, but the date won't parse;
      - it has a valid date whose window has already closed (`as_of` is past
        E + _EARNINGS_WINDOW_DAYS) -- i.e. the calendar is STALE.

    True before and during the window: a series whose print simply hasn't
    happened yet is waiting on the calendar, not on a person, and reporting
    that would cry wolf for most of every quarter.

    Why this exists: the scheduler correctly asks "has THIS company reported
    recently?", but nothing keeps the calendar current -- it is hand-edited and
    nothing in the repo refreshes it. Once a series' store file exists, an
    unusable entry made it quietly never-due again forever, looking exactly
    like a routine skip. That is F131's own headline bug in a new place.
    """
    if cs.earningsKey is None:
        return False
    raw = earnings_dates.get(cs.earningsKey)
    earnings = _parse_date(raw) if isinstance(raw, str) else None
    if earnings is None:
        return False
    return (as_of - earnings).days <= _EARNINGS_WINDOW_DAYS


def _in_earnings_window(cs: ChartSeries, as_of: _dt.date,
                         earnings_dates: Mapping[str, str]) -> bool:
    """Is `as_of` inside the forward-only window after THIS series' company's
    print? (F131 defect C.)

    The calendar is keyed by company -- 'amd', 'nvidia' -- and the series says
    which key is its own via `earningsKey`. It used to arrive as a bare list of
    dates with the names stripped off, so every quarterly series was tested
    against every company's print date and AMD's chart woke up during NVIDIA's
    earnings week.

    Delegates to the shared `manifest.earnings_window` helper, which the
    gather side calls too (with its own +/-7 shape). A missing key, a key the
    calendar has no date for, or a date that won't parse all mean "no window"
    rather than an exception: this runs inside the unattended daily pipeline.
    """
    return earnings_window(earnings_dates, cs.earningsKey, as_of,
                            days_before=0, days_after=_EARNINGS_WINDOW_DAYS)


def due_series(
    series: dict[str, ChartSeries],
    as_of_date: str,
    earnings_dates: dict[str, str],
    store_dir: str = DEFAULT_STORE_DIR,
) -> list[ChartSeries]:
    """Which chart series are due for a fetch attempt as of `as_of_date`.

    - fetcher is None (no fetcher wired up yet, e.g. nvdaDataCenterRevenue):
      never due -- there is nothing that could fetch it. See `not_fetchable`,
      which reports these so they can't pass for a routine skip.
    - cadence == 'monthly': never due here -- price-sync (gpu_agent/price_local.py)
      owns those series end to end.
    - cadence == 'quarterly': due when `as_of_date` falls in the forward-only
      window E .. E+_EARNINGS_WINDOW_DAYS after ITS OWN company's print date
      (`earnings_dates[cs.earningsKey]`), OR the series' store file is missing
      entirely (first-ever fetch, or a file that was never written because the
      series has no history yet).

    `earnings_dates` maps a company key to an ISO print date, exactly as a
    manifest's `earningsDates` field stores it -- pass the mapping, never
    `.values()`.

    Returns series in a stable order for deterministic output; `store_dir` scopes
    the missing-file check to a caller-chosen store root (tests pass a tmp
    dir; the CLI passes the real store).
    """
    # Checked up front, and loudly: run_fetch turns this into its synthetic
    # '*' failure. Two reasons it must raise rather than degrade to "no
    # window". A caller handing over a broken calendar has a config bug that
    # silence would bury. And the pre-F131 call shape was a bare LIST of
    # dates -- a list would otherwise match nothing here and every quarterly
    # series would quietly stop being due, resurrecting F131 in a new form.
    if not isinstance(earnings_dates, Mapping):
        raise TypeError(
            "earnings_dates must be a mapping of company key -> ISO date "
            f"(e.g. manifest.earningsDates), got {type(earnings_dates).__name__}")

    # F131 Q6 (user ruling 2026-08-31): an unparseable as_of is an OPERATOR
    # error, not a data condition, so it fails loudly for the same reason the
    # calendar guard above does. It used to return [] with nothing recorded,
    # which meant a cycle that did nothing at all printed a clean-looking
    # summary of routine skips.
    as_of = _parse_date(as_of_date)
    if as_of is None:
        raise ValueError(
            f"as_of_date must be an ISO date (YYYY-MM-DD), got {as_of_date!r}")

    store_path = Path(store_dir)

    out = []
    for series_id in sorted(series):
        cs = series[series_id]
        if cs.fetcher is None:
            continue
        if cs.cadence != "quarterly":
            continue
        file_missing = not (store_path / f"{cs.id}.jsonl").exists()
        if file_missing or _in_earnings_window(cs, as_of, earnings_dates):
            out.append(cs)
    return out


def _read_jsonl(path: Path) -> list[dict]:
    """Read an existing series file. Deliberately does NOT swallow a corrupt
    line: an unparseable row must surface as an exception so the caller's
    try/except turns it into a 'failed' entry and leaves the file untouched
    (review finding #1) -- silently returning [] here would make one
    truncated line look like "no history yet", and the next successful
    append would then overwrite the file, destroying every prior period."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _newest_stored_period(store_dir: str, cs: ChartSeries) -> str | None:
    """Newest 'period' already on disk for this series, or None when the
    file is missing/empty (first-ever fetch -- staleness check is vacuous).
    Period labels are 'YYYY-Qn' strings, so max()/< compare correctly."""
    rows = _read_jsonl(Path(store_dir) / f"{cs.id}.jsonl")
    periods = [str(r["period"]) for r in rows if r.get("period")]
    return max(periods) if periods else None


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
    earnings_dates: Mapping[str, str],
    store_dir: str,
    fetch_html: Callable[[str], str] | None = None,
) -> dict:
    """Fetch + append every due series. NEVER raises -- any failure (network,
    missing fetcher, unparseable markup, a bad point shape, or even a bad
    argument from the caller) is caught and reported under 'failed'; a
    per-series failure leaves that series' file exactly as it was.

    Returns {'fetched': [{'id', 'newPoints'}], 'failed': [{'id', 'error'}],
    'skipped': [id, ...], 'notFetchable': [id, ...], 'staleCalendar': [id, ...]}.

    'skipped' is the routine bucket: not due this call, but nothing is wrong --
    wrong cadence, or the earnings window simply hasn't opened yet.

    The other two both mean "this will never refresh on its own until a person
    acts", and they are separate because the ACTION differs. 'notFetchable'
    (F131 Q4) lists quarterly series with no fetcher wired up -- somebody must
    build one. 'staleCalendar' (F131 Q5) lists quarterly series that have a
    fetcher but no usable earnings date -- somebody must update the manifest.
    Both used to hide inside 'skipped', where three consecutive cycles read
    the first as a routine skip.

    Every registry series lands in exactly one of the five buckets. On a failure so broad it couldn't even
    get as far as computing which series are due (e.g. `series=None`,
    `earnings_dates=None`, a non-ChartSeries value in `series`) the whole
    call reports one synthetic {'id': '*', ...} failure with empty
    fetched/skipped, rather than letting the exception escape (review
    finding #2 -- everything inside the per-series loop was already
    bulletproof; the prologue/epilogue around it was not)."""
    try:
        # Local import: fetchers/amd_dc_revenue.py imports ParseFailed from
        # this module, so importing FETCHERS at module scope would be circular.
        from gpu_agent.chartdata.fetchers import DISCOVERERS, FETCHERS

        due = due_series(series, as_of_date, earnings_dates, store_dir=store_dir)
        due_ids = {cs.id for cs in due}
        unfetchable_ids = {cs.id for cs in not_fetchable(series)}
        fetched: list[dict] = []
        failed: list[dict] = []
        html_fetcher = fetch_html or _default_fetch_html

        for cs in due:
            try:
                fetcher = FETCHERS.get(cs.fetcher)
                if fetcher is None:
                    failed.append({"id": cs.id,
                                    "error": f"no fetcher registered for {cs.fetcher!r}"})
                    continue
                discoverer = DISCOVERERS.get(cs.fetcher)
                if discoverer is not None:
                    # cs.sourceUrl is a durable LANDING page (fix round 2,
                    # user decision): fetch it, find this quarter's detail
                    # page on it, then fetch+parse THAT -- any of the three
                    # steps failing (landing page unreachable, no matching
                    # link found, a relative href that won't resolve, or the
                    # discovered URL itself failing to fetch/parse) is caught
                    # by the same per-series except below, same as a
                    # one-step fetcher's failure always was.
                    landing_html = html_fetcher(cs.sourceUrl)
                    detail_url = discoverer(landing_html, cs.sourceUrl)
                    html_text = html_fetcher(detail_url)
                else:
                    html_text = html_fetcher(cs.sourceUrl)
                points = fetcher(html_text)
                # F112(a) staleness guard: if the newest quarter we just
                # parsed is strictly older than the newest quarter already
                # stored, link discovery found an OLD release -- appending
                # nothing new would otherwise look like a quiet success.
                newest_stored = _newest_stored_period(store_dir, cs)
                if newest_stored is not None:
                    # Points without a 'period' are excluded from the max so a
                    # malformed batch fails later with the truthful KeyError in
                    # _row, not a misleading empty-label staleness message
                    # (review finding, minor #1).
                    newest_parsed = max(
                        (str(p["period"]) for p in points if p.get("period")),
                        default=None)
                    if newest_parsed is not None and newest_parsed < newest_stored:
                        raise StalenessViolation(
                            f"discovered newest quarter {newest_parsed} is older "
                            f"than newest stored {newest_stored} -- refusing "
                            "stale data (link discovery may have found an old "
                            "release)")
                n_new = _append_points(store_dir, cs, points, as_of_date)
                fetched.append({"id": cs.id, "newPoints": n_new})
            except Exception as e:  # noqa: BLE001 -- deliberate: never let a
                # fetch failure escape into the unattended daily pipeline.
                failed.append({"id": cs.id, "error": f"{type(e).__name__}: {e}"})

        # Every bucket is expressed in the SAME id space -- each series' own
        # cs.id, never the dict key that happens to point at it. load_chart_series
        # keys by id so the two coincide today, but a caller that built the dict
        # by hand with a mismatched key would otherwise put one series in two
        # buckets at once (review finding: the four-bucket partition must not
        # rest on an unstated precondition).
        all_ids = {series[sid].id for sid in series}
        # F131 Q5: a quarterly series that COULD be fetched but has no usable
        # calendar entry is reported, not quietly skipped. Precedence is
        # deliberate: a series already due is being handled right now, and one
        # with no fetcher needs a fetcher built before its calendar matters --
        # so both of those win over this bucket, keeping every series in
        # exactly one place.
        as_of = _parse_date(as_of_date)
        stale_ids = {
            cs.id for cs in (series[sid] for sid in series)
            if cs.cadence == "quarterly" and cs.fetcher is not None
            and cs.id not in due_ids and cs.id not in unfetchable_ids
            and not has_usable_calendar_entry(cs, as_of, earnings_dates)
        }
        skipped = sorted(sid for sid in all_ids
                          if sid not in due_ids and sid not in unfetchable_ids
                          and sid not in stale_ids)
        return {"fetched": fetched, "failed": failed, "skipped": skipped,
                "notFetchable": sorted(unfetchable_ids),
                "staleCalendar": sorted(stale_ids)}
    except Exception as e:  # noqa: BLE001 -- deliberate, see docstring above.
        return {"fetched": [],
                "failed": [{"id": "*", "error": f"{type(e).__name__}: {e}"}],
                "skipped": [], "notFetchable": [], "staleCalendar": []}


# F134 Q1 (user ruling 2026-09-01): both investor.nvidia.com and
# nvidianews.nvidia.com answer HTTP 403 Forbidden to a request that sends no
# User-Agent -- which is exactly what urllib sends by default. With an
# ordinary browser User-Agent both serve the page immediately, so this is an
# "identify yourself" rejection rather than a bot wall, and no mirror or cache
# service is involved. AMD's pages are indifferent to the header, so one
# shared value covers every fetcher rather than adding per-fetcher header
# plumbing for the sake of one site.
_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _build_request(url: str):
    """Build the HTTP request _default_fetch_html sends.

    Split out from the network call on purpose: the 403 that made this
    necessary was invisible to every existing test precisely because the
    request itself was never inspectable. This half is pure and covered;
    the urlopen half below is not."""
    import urllib.request
    return urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})


def _default_fetch_html(url: str) -> str:  # pragma: no cover -- network path,
    # never exercised by tests; tests always inject fetch_html.
    import urllib.request
    with urllib.request.urlopen(_build_request(url), timeout=20) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")
