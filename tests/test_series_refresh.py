import datetime
import json
import pytest
from pydantic import ValidationError
from gpu_agent.series_refresh import (
    CalendarEntry, SeriesGap, expected_period, find_gaps, load_calendar)
from gpu_agent.series_refresh import CandidateEnvelope, IngestResult, ingest_candidates
from gpu_agent.series_registry import SeriesRegistry
from gpu_agent.series_store import SeriesPoint, SeriesSource, append_point, read_series

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


def _envelope(*points):
    return json.dumps({"candidates": [json.loads(p.model_dump_json()) for p in points]})

def _registry():
    return SeriesRegistry.load(REG)

def test_ingest_valid_candidate_appends_with_restamped_capture(tmp_path):
    reg = _registry()
    iid = sorted(reg.specs)[0]
    pt = _point(iid, "2026-07", unit=reg.specs[iid].unit)
    out = ingest_candidates(_envelope(pt), reg, tmp_path,
                            today=datetime.date(2026, 7, 28))
    assert out.written == [f"{iid} 2026-07"] and not out.rejected
    stored = read_series(tmp_path, iid)
    assert stored[-1].capturedAt == "2026-07-28"   # capture vintage is CODE-stamped

def test_ingest_missing_envelope_key_fails_loud(tmp_path):
    reg = _registry()
    iid = sorted(reg.specs)[0]
    bare = json.loads(_point(iid, "2026-07").model_dump_json())
    out = ingest_candidates(json.dumps(bare), reg, tmp_path,
                            today=datetime.date(2026, 7, 28))
    assert not out.written and len(out.rejected) == 1
    assert "envelope" in out.rejected[0]

def test_ingest_rejects_unknown_id_and_wrong_unit(tmp_path):
    reg = _registry()
    iid = sorted(reg.specs)[0]
    ghost = _point("noSuchSeries", "2026-07")
    wrong = _point(iid, "2026-07", unit="bananas_per_wafer")
    out = ingest_candidates(_envelope(ghost, wrong), reg, tmp_path,
                            today=datetime.date(2026, 7, 28))
    assert not out.written and len(out.rejected) == 2
    assert not list(tmp_path.iterdir())            # nothing written, append-only intact

def test_ingest_rejects_implausible_magnitude(tmp_path):
    reg = _registry()
    iid = sorted(reg.specs)[0]
    unit = reg.specs[iid].unit
    for m in ("2026-04", "2026-05", "2026-06"):
        append_point(tmp_path, _point(iid, m, value=5.0, unit=unit))
    wild = _point(iid, "2026-07", value=5000.0, unit=unit)
    out = ingest_candidates(_envelope(wild), reg, tmp_path,
                            today=datetime.date(2026, 7, 28))
    assert not out.written and "implausible" in out.rejected[0]

def test_ingest_duplicate_skips_but_revision_appends(tmp_path):
    reg = _registry()
    iid = sorted(reg.specs)[0]
    unit = reg.specs[iid].unit
    existing = _point(iid, "2026-06", unit=unit, published="2026-06-28")
    append_point(tmp_path, existing)
    dup = _point(iid, "2026-06", unit=unit, published="2026-06-28")
    rev = _point(iid, "2026-06", value=2.0, unit=unit, published="2026-07-20")
    out = ingest_candidates(_envelope(dup, rev), reg, tmp_path,
                            today=datetime.date(2026, 7, 28))
    assert out.alreadyPresent == [f"{iid} 2026-06"]
    assert out.written == [f"{iid} 2026-06"]       # later vintage = legitimate revision


# --- final-review regressions -------------------------------------------------

def _monthly_id(reg, calendar):
    return sorted(i for i in reg.specs if calendar[i].cadence == "monthly")[0]

def _quarterly_id(reg, calendar):
    return sorted(i for i in reg.specs if calendar[i].cadence == "quarterly")[0]

def test_ingest_rejects_future_period(tmp_path):
    """CRITICAL 1: a period after the cycle month is never written."""
    reg, cal = _registry(), load_calendar(CAL)
    iid = _monthly_id(reg, cal)
    far = _point(iid, "2099-12", unit=reg.specs[iid].unit, published="2026-07-28")
    out = ingest_candidates(_envelope(far), reg, tmp_path,
                            today=datetime.date(2026, 7, 28))
    assert not out.written and "future period" in out.rejected[0]
    assert not list(tmp_path.iterdir())

def test_find_gaps_ignores_a_pre_existing_future_period(tmp_path):
    """CRITICAL 1 second half: a bad row already in the store cannot hide the gap."""
    reg, cal = _registry(), load_calendar(CAL)
    iid = _monthly_id(reg, cal)
    append_point(tmp_path, _point(iid, "2099-12", unit=reg.specs[iid].unit,
                                  published="2026-07-28"))
    for when in (datetime.date(2026, 8, 15), datetime.date(2030, 8, 15)):
        flagged = [g for g in find_gaps(reg, cal, tmp_path, when) if g.indicatorId == iid]
        assert flagged, f"future row must not blind the gap check on {when}"
        assert flagged[0].latestPeriod is None

def test_ingest_rejects_malformed_and_future_published_at(tmp_path):
    """IMPORTANT 2: a point that would be written yet invisible to every read."""
    reg = _registry()
    iid = sorted(reg.specs)[0]
    unit = reg.specs[iid].unit
    prose = _point(iid, "2026-06", unit=unit, published="sometime last week")
    ahead = _point(iid, "2026-06", unit=unit, published="9999-01-01")
    out = ingest_candidates(_envelope(prose, ahead), reg, tmp_path,
                            today=datetime.date(2026, 7, 28))
    assert not out.written and len(out.rejected) == 2
    assert "malformed publishedAt" in out.rejected[0]
    assert "future publishedAt" in out.rejected[1]
    assert not list(tmp_path.iterdir())

def test_gap_carries_unit_and_latest_construction(tmp_path):
    """IMPORTANT 3 + 4: the reader needs the unit verbatim and the prior construction."""
    reg, cal = _registry(), load_calendar(CAL)
    iid = _monthly_id(reg, cal)
    unit = reg.specs[iid].unit
    seeded = SeriesPoint(
        indicatorId=iid, period="2026-05", value=7.5, unit=unit,
        publishedAt="2026-06-10", capturedAt="2026-06-10",
        source=SeriesSource(url="https://example.com/x", title="t"),
        note="sum YoY of Quanta+Wistron+Wiwynn monthly rev")
    append_point(tmp_path, seeded)
    gaps = {g.indicatorId: g for g in
            find_gaps(reg, cal, tmp_path, datetime.date(2026, 7, 28))}
    assert gaps[iid].unit == unit
    assert gaps[iid].latestNote == "sum YoY of Quanta+Wistron+Wiwynn monthly rev"
    assert gaps[iid].latestValue == 7.5
    empty = {g.indicatorId: g for g in
             find_gaps(reg, cal, tmp_path / "nothing", datetime.date(2026, 7, 28))}
    assert empty[iid].latestNote is None and empty[iid].latestValue is None
    assert all(g.unit == reg.specs[g.indicatorId].unit for g in empty.values())

def test_ingest_flags_conflicting_same_vintage_value(tmp_path):
    """IMPORTANT 6: a same-day disagreement is a finding, not a duplicate."""
    reg = _registry()
    iid = sorted(reg.specs)[0]
    unit = reg.specs[iid].unit
    append_point(tmp_path, _point(iid, "2026-06", value=1.0, unit=unit,
                                  published="2026-07-28"))
    clash = _point(iid, "2026-06", value=1.5, unit=unit, published="2026-07-28")
    out = ingest_candidates(_envelope(clash), reg, tmp_path,
                            today=datetime.date(2026, 7, 28))
    assert not out.written and not out.alreadyPresent
    assert "conflicting same-vintage value" in out.rejected[0]
    assert "1.5" in out.rejected[0] and "1.0" in out.rejected[0]

def test_ingest_exact_same_vintage_repeat_is_already_present(tmp_path):
    reg = _registry()
    iid = sorted(reg.specs)[0]
    unit = reg.specs[iid].unit
    append_point(tmp_path, _point(iid, "2026-06", value=1.0, unit=unit,
                                  published="2026-07-28"))
    same = _point(iid, "2026-06", value=1.0, unit=unit, published="2026-07-28")
    out = ingest_candidates(_envelope(same), reg, tmp_path,
                            today=datetime.date(2026, 7, 28))
    assert out.alreadyPresent == [f"{iid} 2026-06"] and not out.rejected

def test_ingest_rejects_candidate_when_store_file_is_malformed(tmp_path):
    reg = _registry()
    iid = sorted(reg.specs)[0]
    (tmp_path / f"{iid}.jsonl").write_text('{"indicatorId": "junk"}\n', "utf-8")
    cand = _point(iid, "2026-06", unit=reg.specs[iid].unit, published="2026-07-01")
    out = ingest_candidates(_envelope(cand), reg, tmp_path,
                            today=datetime.date(2026, 7, 28))
    assert not out.written and "malformed" in out.rejected[0]

def test_ingest_rejects_quarterly_off_quarter_period(tmp_path):
    reg, cal = _registry(), load_calendar(CAL)
    iid = _quarterly_id(reg, cal)
    unit = reg.specs[iid].unit
    off = _point(iid, "2026-05", unit=unit, published="2026-07-01")
    on = _point(iid, "2026-03", unit=unit, published="2026-07-01")
    out = ingest_candidates(_envelope(off, on), reg, tmp_path,
                            today=datetime.date(2026, 7, 28), calendar=cal)
    assert out.written == [f"{iid} 2026-03"]
    assert len(out.rejected) == 1 and "quarter-end" in out.rejected[0]

def test_ingest_without_calendar_keeps_the_old_signature(tmp_path):
    """The calendar arg is optional: omitting it skips only the cadence check."""
    reg, cal = _registry(), load_calendar(CAL)
    iid = _quarterly_id(reg, cal)
    off = _point(iid, "2026-05", unit=reg.specs[iid].unit, published="2026-07-01")
    out = ingest_candidates(_envelope(off), reg, tmp_path,
                            today=datetime.date(2026, 7, 28))
    assert out.written == [f"{iid} 2026-05"]

def test_intra_envelope_duplicate_is_deduped(tmp_path):
    """Pins the per-candidate re-read of the store: two identical candidates in ONE
    envelope must land once. Do NOT hoist read_series out of the loop."""
    reg = _registry()
    iid = sorted(reg.specs)[0]
    unit = reg.specs[iid].unit
    twin = _point(iid, "2026-06", unit=unit, published="2026-07-01")
    out = ingest_candidates(_envelope(twin, twin), reg, tmp_path,
                            today=datetime.date(2026, 7, 28))
    assert out.written == [f"{iid} 2026-06"]
    assert out.alreadyPresent == [f"{iid} 2026-06"]
    assert len(read_series(tmp_path, iid)) == 1
