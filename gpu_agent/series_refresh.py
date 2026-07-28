"""F79 G4 — series refresh: calendar-driven gap check + validated candidate ingest.

The daily cycle asks "should a newer monthly point exist by now?" per series
(registry/series-calendar.json, curated trust boundary) and only dispatches a reader
for flagged series. Candidates enter through ingest_candidates() — the deterministic
validation boundary (price-sync precedent): failures are reported, never written, and
never block the cycle. store/series stays append-only.
"""
from __future__ import annotations

import datetime
import json
import math
import pathlib
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, ValidationError

from gpu_agent.series_registry import SeriesRegistry
from gpu_agent.series_store import SeriesPoint, append_point, latest_by_period, read_series

CALENDAR_PATH = "registry/series-calendar.json"


class CalendarEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cadence: Literal["monthly", "quarterly"]
    availableDay: int = 15        # monthly: day of the FOLLOWING month the print lands
    availableLagDays: int = 45    # quarterly: days after quarter end
    toleranceMonths: int = 0
    sourceHint: str = ""


class SeriesGap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    indicatorId: str
    expectedPeriod: str           # YYYY-MM the store should hold by today
    latestPeriod: Optional[str]   # newest period in the store, None if the series is empty
    sourceHint: str = ""
    unit: str = ""                # registry unit the candidate MUST carry verbatim
    # the newest stored point, so a reader can reproduce the SAME construction
    # (these series are constructions, not raw published figures)
    latestNote: Optional[str] = None
    latestValue: Optional[float] = None


def load_calendar(path=CALENDAR_PATH) -> dict[str, CalendarEntry]:
    raw = json.loads(pathlib.Path(path).read_text("utf-8"))
    return {k: CalendarEntry.model_validate(v)
            for k, v in raw["seriesCalendar"].items()}


def _shift_months(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def expected_period(entry: CalendarEntry, today: datetime.date) -> str:
    if entry.cadence == "monthly":
        # the previous month once availableDay is reached, else the month before
        back = 1 if today.day >= entry.availableDay else 2
        y, m = _shift_months(today.year, today.month, -back)
    else:  # quarterly: last quarter whose end + lag has passed
        y, m = today.year, today.month
        while True:
            q_end_y, q_end_m = y, ((m - 1) // 3) * 3 + 3   # this quarter's last month
            if (q_end_y, q_end_m) >= (today.year, today.month):
                y, m = _shift_months(q_end_y, q_end_m, -3)  # quarter not over: step back
                continue
            next_y, next_m = _shift_months(q_end_y, q_end_m, 1)
            q_end = datetime.date(next_y, next_m, 1) - datetime.timedelta(days=1)
            if q_end + datetime.timedelta(days=entry.availableLagDays) <= today:
                y, m = q_end_y, q_end_m
                break
            y, m = _shift_months(q_end_y, q_end_m, -3)
    y, m = _shift_months(y, m, -entry.toleranceMonths)
    return f"{y:04d}-{m:02d}"


def find_gaps(registry: SeriesRegistry, calendar: dict[str, CalendarEntry],
              series_root, today: datetime.date) -> list[SeriesGap]:
    missing = set(registry.specs) - set(calendar)
    if missing:
        raise ValueError(f"series-calendar has no entry for: {sorted(missing)}")
    gaps: list[SeriesGap] = []
    for iid in sorted(registry.specs):
        spec = registry.specs[iid]
        if spec.lifecycle == "retired":
            continue
        entry = calendar[iid]
        expected = expected_period(entry, today)
        by_period = latest_by_period(series_root, iid, as_of=today.isoformat())
        # a period AFTER the cycle month cannot be evidence of freshness: ignore it,
        # so a pre-existing bad row can never hide this gap forever (CRITICAL 1)
        cycle_month = today.strftime("%Y-%m")
        usable = {p: pt for p, pt in by_period.items() if p <= cycle_month}
        latest = max(usable) if usable else None
        if latest is None or latest < expected:
            newest = usable[latest] if latest is not None else None
            gaps.append(SeriesGap(
                indicatorId=iid, expectedPeriod=expected, latestPeriod=latest,
                sourceHint=entry.sourceHint, unit=spec.unit,
                latestNote=newest.note if newest is not None else None,
                latestValue=newest.value if newest is not None else None))
    return gaps


PLAUSIBILITY_FACTOR = 10.0   # reject |value| > 10 x max(1, historical max |value|)


class CandidateEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")   # F105: a wrong shape fails loud, never empty
    candidates: list[SeriesPoint]


class IngestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    written: list[str] = []
    rejected: list[str] = []
    alreadyPresent: list[str] = []


_QUARTER_END_MONTHS = {"03", "06", "09", "12"}


def ingest_candidates(envelope_text: str, registry: SeriesRegistry, series_root,
                      *, today: datetime.date,
                      calendar: Optional[dict[str, CalendarEntry]] = None) -> IngestResult:
    """Validate candidates and append the survivors. `calendar` is optional: when given,
    a quarterly series' candidate must sit on a quarter-end month."""
    out = IngestResult()
    try:
        env = CandidateEnvelope.model_validate_json(envelope_text)
    except ValidationError as e:
        out.rejected.append(f"envelope: {e.error_count()} validation errors "
                            f"(candidates key required, extras forbidden): {e}")
        return out
    cycle_month = today.strftime("%Y-%m")
    for cand in env.candidates:
        label = f"{cand.indicatorId} {cand.period}"
        spec = registry.specs.get(cand.indicatorId)
        if spec is None:
            out.rejected.append(f"{label}: unknown series id")
            continue
        if cand.unit != spec.unit:
            out.rejected.append(f"{label}: unit {cand.unit!r} != registry {spec.unit!r}")
            continue
        # CRITICAL 1: a period after the cycle month would be written forever and
        # (before the find_gaps guard) blind the gap check. The store has no undo.
        if cand.period > cycle_month:
            out.rejected.append(f"{label}: future period (cycle month {cycle_month})")
            continue
        # IMPORTANT 2: an unparseable or future publishedAt is written yet invisible
        # to every vintage-aware read, so the gap never closes.
        try:
            datetime.date.fromisoformat(cand.publishedAt)
        except ValueError:
            out.rejected.append(f"{label}: malformed publishedAt "
                                f"{cand.publishedAt!r} (need YYYY-MM-DD)")
            continue
        if cand.publishedAt > today.isoformat():
            out.rejected.append(f"{label}: future publishedAt {cand.publishedAt!r} "
                                f"(cycle day {today.isoformat()})")
            continue
        entry = calendar.get(cand.indicatorId) if calendar else None
        if (entry is not None and entry.cadence == "quarterly"
                and cand.period[5:7] not in _QUARTER_END_MONTHS):
            out.rejected.append(f"{label}: quarterly series needs a quarter-end "
                                "period month (03/06/09/12)")
            continue
        if not math.isfinite(cand.value):
            out.rejected.append(f"{label}: non-finite value")
            continue
        try:
            history = read_series(series_root, cand.indicatorId)
        except ValidationError as e:
            out.rejected.append(
                f"{label}: existing store file is malformed "
                f"({e.error_count()} validation errors) — cannot validate "
                "against history, fix the store file first")
            continue
        bound = PLAUSIBILITY_FACTOR * max(
            [1.0] + [abs(p.value) for p in history])
        if history and abs(cand.value) > bound:
            out.rejected.append(f"{label}: implausible magnitude {cand.value} "
                                f"(bound {bound})")
            continue
        same_vintage = [p for p in history
                        if p.period == cand.period and p.publishedAt == cand.publishedAt]
        if same_vintage:
            # IMPORTANT 6: a same-vintage correction that disagrees is a real finding,
            # not a duplicate — only an exact value match is alreadyPresent.
            if any(p.value == cand.value for p in same_vintage):
                out.alreadyPresent.append(label)
            else:
                out.rejected.append(
                    f"{label}: conflicting same-vintage value {cand.value} vs stored "
                    f"{same_vintage[-1].value} at publishedAt {cand.publishedAt}")
            continue
        stamped = cand.model_copy(update={"capturedAt": today.isoformat()})
        append_point(series_root, stamped)
        out.written.append(label)
    return out
