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
import pathlib
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from gpu_agent.series_registry import SeriesRegistry
from gpu_agent.series_store import latest_by_period

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
        latest = max(by_period) if by_period else None
        if latest is None or latest < expected:
            gaps.append(SeriesGap(indicatorId=iid, expectedPeriod=expected,
                                  latestPeriod=latest, sourceHint=entry.sourceHint))
    return gaps
