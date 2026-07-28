import datetime
import json
import pytest
from pydantic import ValidationError
from gpu_agent.series_refresh import (
    CalendarEntry, SeriesGap, expected_period, find_gaps, load_calendar)
from gpu_agent.series_registry import SeriesRegistry
from gpu_agent.series_store import SeriesPoint, SeriesSource, append_point

CAL = "registry/series-calendar.json"
REG = "registry/series-indicators.json"

def _point(iid, period, value=1.0, unit="pct_yoy", published=None):
    return SeriesPoint(
        indicatorId=iid, period=period, value=value, unit=unit,
        publishedAt=published or f"{period}-28", capturedAt="2026-07-28",
        source=SeriesSource(url="https://example.com/x", title="t"))

def test_committed_calendar_covers_every_scoring_series():
    registry = SeriesRegistry.load(REG)
    calendar = load_calendar(CAL)
    assert set(calendar) == set(registry.specs), (
        "series-calendar.json must cover exactly the scoring series registry")

def test_calendar_entry_forbids_extras():
    with pytest.raises(ValidationError):
        CalendarEntry.model_validate({"cadence": "monthly", "publishDay": 12})

def test_expected_period_monthly_before_and_after_available_day():
    e = CalendarEntry(cadence="monthly", availableDay=12)
    # before the 12th the previous month is not yet expected
    assert expected_period(e, datetime.date(2026, 7, 5)) == "2026-05"
    assert expected_period(e, datetime.date(2026, 7, 12)) == "2026-06"

def test_expected_period_monthly_tolerance_relaxes():
    e = CalendarEntry(cadence="monthly", availableDay=12, toleranceMonths=2)
    assert expected_period(e, datetime.date(2026, 7, 12)) == "2026-04"

def test_expected_period_quarterly_lag():
    e = CalendarEntry(cadence="quarterly", availableLagDays=45)
    # Q2 ends 06-30; +45d = 08-14, so on 07-28 only Q1 is expected
    assert expected_period(e, datetime.date(2026, 7, 28)) == "2026-03"
    assert expected_period(e, datetime.date(2026, 8, 14)) == "2026-06"

def test_find_gaps_flags_only_stale_series(tmp_path):
    registry = SeriesRegistry.load(REG)
    calendar = load_calendar(CAL)
    for iid, spec in registry.specs.items():
        append_point(tmp_path, _point(iid, "2026-06", unit=spec.unit))
    fresh = find_gaps(registry, calendar, tmp_path, datetime.date(2026, 7, 5))
    assert fresh == []          # everything current on 07-05
    stale = find_gaps(registry, calendar, tmp_path, datetime.date(2026, 9, 20))
    assert stale, "by late September a 2026-06 latest point must gap"
    g = stale[0]
    assert g.latestPeriod == "2026-06" and g.expectedPeriod > "2026-06"
    assert g.sourceHint    # calendar carries a dispatch hint

def test_find_gaps_empty_store_flags_everything(tmp_path):
    registry = SeriesRegistry.load(REG)
    calendar = load_calendar(CAL)
    gaps = find_gaps(registry, calendar, tmp_path, datetime.date(2026, 7, 28))
    assert {g.indicatorId for g in gaps} == set(registry.specs)
    assert all(g.latestPeriod is None for g in gaps)

def test_find_gaps_raises_on_uncovered_series(tmp_path):
    registry = SeriesRegistry.load(REG)
    calendar = dict(load_calendar(CAL))
    calendar.popitem()
    with pytest.raises(ValueError, match="calendar"):
        find_gaps(registry, calendar, tmp_path, datetime.date(2026, 7, 28))
