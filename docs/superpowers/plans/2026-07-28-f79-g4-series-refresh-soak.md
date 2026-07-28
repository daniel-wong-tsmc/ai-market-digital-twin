# F79 G4 — Series Refresh + Shadow Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The question-stop rule (CLAUDE.md) applies verbatim: a design fork STOPS the lane — write questions + recommendation to `.superpowers/handoffs/f79-g4-refresh-QUESTIONS.md`, end turn. STOP before merge; only the user merges.

**Goal:** Keep the six v2 scoring series fed monthly (calendar-driven gap check + validated ingest) and stamp every daily cycle's scorecard with the v2 shadow, starting the G4 soak.

**Architecture:** New `gpu_agent/series_refresh.py` (pure gap-check + strict ingest boundary) + curated `registry/series-calendar.json` + a `series-refresh` CLI verb, mirroring the `price-sync` precedent (deterministic trust boundary, never blocks a cycle). The run-cycle skill gains steps 7b (refresh) and 7c (`v2-shadow` stamp — verb already exists from F79 Stage 6); that SKILL.md edit re-records the F83 fingerprint in lockstep, same commit.

**Tech Stack:** Python 3.13, pydantic v2, pytest. Venv: `../../.venv/Scripts/python` from the worktree root.

**Spec:** `docs/superpowers/specs/2026-07-28-f79-g4-series-refresh-soak-design.md` (user decisions D1–D5).

## Global Constraints

- Lane: worktree `.worktrees/f79-g4-refresh`, branch `f79-g4-refresh`. Never touch root `store/`.
- MUST-NOT-TOUCH: `gpu_agent/scoring.py` v1 paths, `gpu_agent/report.py`, brain prompts, `gpu_agent/evals/`, `fixtures/evals/`, `registry/indicators.json`, `gpu_agent/narrator/`, `fixtures/narrator/`.
- Pins: F6 (`tests/test_evals_baseline_pin.py`), scoring-v1 replay, narrator stay GREEN at every commit. F83 (`tests/test_run_cycle_conformance.py`) re-records ONLY in Task 4's commit (SKILL.md edit + `EXPECTED_STEPS` + fingerprint together).
- `store/series/` stays append-only: validation failures never write; no rewrites.
- Refresh and shadow stamping never block a cycle (price-sync precedent): CLI exits 0 on rejections; 2 only on operator error.
- Not a scored brain seam: no new `fixtures/evals` case, no eval gate.
- Forbidden-diff check before the close-out: `git diff main --stat -- fixtures/ registry/indicators.json gpu_agent/evals gpu_agent/narrator` must be EMPTY (the new `registry/series-calendar.json` is allowed; show it separately).
- **Flag for the user at close-out:** the seed calendar values in Task 1 (publication days/lags/tolerances) are assistant-proposed tunable defaults, editable by JSON edit — record as such in decision provenance, never as user-approved.

---

### Task 1: Calendar registry + gap check

**Files:**
- Create: `registry/series-calendar.json`
- Create: `gpu_agent/series_refresh.py`
- Test: `tests/test_series_refresh.py`

**Interfaces:**
- Consumes: `SeriesRegistry.load(path)` / `.specs: dict[str, SeriesIndicatorSpec]` (`gpu_agent/series_registry.py`); `latest_by_period(root, indicator_id, *, as_of)` (`gpu_agent/series_store.py`).
- Produces: `load_calendar(path) -> dict[str, CalendarEntry]`; `expected_period(entry: CalendarEntry, today: datetime.date) -> str`; `find_gaps(registry: SeriesRegistry, calendar: dict[str, CalendarEntry], series_root, today: datetime.date) -> list[SeriesGap]`. `SeriesGap` fields: `indicatorId: str`, `expectedPeriod: str`, `latestPeriod: Optional[str]`, `sourceHint: str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_series_refresh.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/test_series_refresh.py -q`
Expected: FAIL — `ModuleNotFoundError: gpu_agent.series_refresh` (and the calendar file missing).

- [ ] **Step 3: Create `registry/series-calendar.json`** (seed values = tunable defaults, see Global Constraints)

```json
{
  "version": "1.0",
  "note": "F79 G4 publication calendar for the six scoring series. Drives the daily gap check (gpu_agent/series_refresh.py). Curated trust boundary (price-benchmarks precedent): tune by JSON edit. availableDay = day of the FOLLOWING month a monthly print is expected; availableLagDays = days after quarter end; toleranceMonths relaxes the expectation for irregular series. NON-prompt-affecting: never read by any brain prompt or the F6 pin.",
  "seriesCalendar": {
    "odmMonthlyAiRevenue":      {"cadence": "monthly",   "availableDay": 12, "sourceHint": "TWSE monthly revenue releases (~10th): Hon Hai, Quanta, Wistron/Wiwynn AI-server revenue"},
    "tokenEconomics":           {"cadence": "monthly",   "availableDay": 15, "sourceHint": "public API price sheets + token-volume trackers (OpenRouter, Anthropic/OpenAI pricing pages); estimate-grade"},
    "pkgCapacityOrderSpread":   {"cadence": "monthly",   "availableDay": 15, "toleranceMonths": 2, "sourceHint": "CoWoS/packaging ramp-vs-order coverage (TrendForce summaries, supply-chain press); irregular"},
    "hbmSupplyCapex":           {"cadence": "quarterly", "availableLagDays": 45, "sourceHint": "Samsung / SK hynix / Micron quarterly results + capex commentary"},
    "hyperscalerCapexRevision": {"cadence": "quarterly", "availableLagDays": 45, "sourceHint": "MSFT/GOOG/AMZN/META quarterly results: capex guidance revisions"},
    "marginalBuyerFinancing":   {"cadence": "quarterly", "availableLagDays": 45, "sourceHint": "neocloud financing terms: CoreWeave/Lambda filings, debt-facility press"}
  }
}
```

- [ ] **Step 4: Write `gpu_agent/series_refresh.py` (gap-check half)**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/test_series_refresh.py -q`
Expected: PASS (all Task-1 tests).

- [ ] **Step 6: Commit**

```bash
git add registry/series-calendar.json gpu_agent/series_refresh.py tests/test_series_refresh.py
git commit -m "feat(f79-g4): series publication calendar + deterministic gap check"
```

---

### Task 2: Candidate ingest — strict validation + append

**Files:**
- Modify: `gpu_agent/series_refresh.py` (append to the file from Task 1)
- Test: `tests/test_series_refresh.py` (append)

**Interfaces:**
- Consumes: `SeriesPoint` / `SeriesSource` / `append_point(root, point)` / `read_series(root, iid)` (`gpu_agent/series_store.py`); `SeriesRegistry` from Task 1.
- Produces: `CandidateEnvelope` (strict: `{"candidates": [SeriesPoint...]}`, extras forbidden, key required — the F105 lesson applied from birth); `ingest_candidates(envelope_text: str, registry: SeriesRegistry, series_root, *, today: datetime.date) -> IngestResult`. `IngestResult` fields: `written: list[str]`, `rejected: list[str]`, `alreadyPresent: list[str]` (entries formatted `"<indicatorId> <period>"`, rejected entries `"<indicatorId> <period>: <reason>"`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_series_refresh.py`)

```python
from gpu_agent.series_refresh import CandidateEnvelope, IngestResult, ingest_candidates
from gpu_agent.series_store import read_series

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/test_series_refresh.py -q`
Expected: FAIL — `ImportError: cannot import name 'CandidateEnvelope'`.

- [ ] **Step 3: Implement ingest** (append to `gpu_agent/series_refresh.py`)

```python
import math

from pydantic import ValidationError

from gpu_agent.series_store import SeriesPoint, append_point, read_series

PLAUSIBILITY_FACTOR = 10.0   # reject |value| > 10 x max(1, historical max |value|)


class CandidateEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")   # F105: a wrong shape fails loud, never empty
    candidates: list[SeriesPoint]


class IngestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    written: list[str] = []
    rejected: list[str] = []
    alreadyPresent: list[str] = []


def ingest_candidates(envelope_text: str, registry: SeriesRegistry, series_root,
                      *, today: datetime.date) -> IngestResult:
    out = IngestResult()
    try:
        env = CandidateEnvelope.model_validate_json(envelope_text)
    except ValidationError as e:
        out.rejected.append(f"envelope: {e.error_count()} validation errors "
                            f"(candidates key required, extras forbidden): {e}")
        return out
    for cand in env.candidates:
        label = f"{cand.indicatorId} {cand.period}"
        spec = registry.specs.get(cand.indicatorId)
        if spec is None:
            out.rejected.append(f"{label}: unknown series id")
            continue
        if cand.unit != spec.unit:
            out.rejected.append(f"{label}: unit {cand.unit!r} != registry {spec.unit!r}")
            continue
        if not math.isfinite(cand.value):
            out.rejected.append(f"{label}: non-finite value")
            continue
        history = read_series(series_root, cand.indicatorId)
        bound = PLAUSIBILITY_FACTOR * max(
            [1.0] + [abs(p.value) for p in history])
        if history and abs(cand.value) > bound:
            out.rejected.append(f"{label}: implausible magnitude {cand.value} "
                                f"(bound {bound})")
            continue
        if any(p.period == cand.period and p.publishedAt == cand.publishedAt
               for p in history):
            out.alreadyPresent.append(label)
            continue
        stamped = cand.model_copy(update={"capturedAt": today.isoformat()})
        append_point(series_root, stamped)
        out.written.append(label)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/test_series_refresh.py -q`
Expected: PASS (all tests so far).

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/series_refresh.py tests/test_series_refresh.py
git commit -m "feat(f79-g4): strict candidate ingest - validated, code-stamped, append-only"
```

---

### Task 3: `series-refresh` CLI verb

**Files:**
- Modify: `gpu_agent/cli.py` (parser block near the `price-sync` parser ~line 1571; handler near `_price_sync` ~line 1355; dispatch near line 1692)
- Test: `tests/test_cli_series_refresh.py`

**Interfaces:**
- Consumes: Task 1/2 functions (`load_calendar`, `find_gaps`, `ingest_candidates`), `SeriesRegistry.load`.
- Produces: `gpu-agent series-refresh --check --as-of YYYY-MM-DD [--out FILE]` → prints/writes `{"gaps": [SeriesGap...]}`, exit 0. `gpu-agent series-refresh --ingest FILE --as-of YYYY-MM-DD` → prints `IngestResult` JSON, exit 0 even with rejections. Exit 2 on operator error (both/neither of `--check`/`--ingest`, missing file, malformed `--as-of`). Flags: `--series-root` (default `store/series`), `--calendar` (default `registry/series-calendar.json`), `--series-registry` (default `registry/series-indicators.json`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_series_refresh.py
# NOTE: tests/ is not a package in this repo — never import from another test module;
# each test file carries its own helpers.
import datetime
import json
from gpu_agent.cli import main
from gpu_agent.series_registry import SeriesRegistry
from gpu_agent.series_store import SeriesPoint, SeriesSource, read_series

REG = "registry/series-indicators.json"

def _point(iid, period, value=1.0, unit="pct_yoy", published=None):
    return SeriesPoint(
        indicatorId=iid, period=period, value=value, unit=unit,
        publishedAt=published or f"{period}-28", capturedAt="2026-07-28",
        source=SeriesSource(url="https://example.com/x", title="t"))

def test_check_writes_gap_report(tmp_path, capsys):
    out_file = tmp_path / "gaps.json"
    rc = main(["series-refresh", "--check", "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series"), "--out", str(out_file)])
    assert rc == 0
    gaps = json.loads(out_file.read_text("utf-8"))["gaps"]
    assert gaps and all(g["latestPeriod"] is None for g in gaps)  # empty store: all gap

def test_ingest_exit_0_even_with_rejections(tmp_path, capsys):
    reg = SeriesRegistry.load(REG)
    iid = sorted(reg.specs)[0]
    good = _point(iid, "2026-07", unit=reg.specs[iid].unit)
    bad = _point(iid, "2026-07", unit="bananas_per_wafer")
    cand = tmp_path / "candidates.json"
    cand.write_text(json.dumps({"candidates": [
        json.loads(good.model_dump_json()), json.loads(bad.model_dump_json())]}), "utf-8")
    rc = main(["series-refresh", "--ingest", str(cand), "--as-of", "2026-07-28",
               "--series-root", str(tmp_path / "series")])
    assert rc == 0                                   # rejections never block the cycle
    result = json.loads(capsys.readouterr().out)
    assert len(result["written"]) == 1 and len(result["rejected"]) == 1
    assert read_series(tmp_path / "series", iid)[-1].capturedAt == "2026-07-28"

def test_operator_errors_exit_2(tmp_path, capsys):
    assert main(["series-refresh", "--as-of", "2026-07-28"]) == 2          # neither flag
    assert main(["series-refresh", "--check", "--ingest", "x",
                 "--as-of", "2026-07-28"]) == 2                            # both flags
    assert main(["series-refresh", "--ingest", str(tmp_path / "absent.json"),
                 "--as-of", "2026-07-28"]) == 2                            # missing file
    assert main(["series-refresh", "--check", "--as-of", "2026-13-99"]) == 2  # bad as-of
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/test_cli_series_refresh.py -q`
Expected: FAIL — argparse error (unknown verb `series-refresh`), surfacing as SystemExit/2 mismatch on the first test.

- [ ] **Step 3: Implement the verb** — handler next to `_price_sync`:

```python
def _series_refresh(args) -> int:
    import datetime as _dt
    from gpu_agent.series_refresh import find_gaps, ingest_candidates, load_calendar
    from gpu_agent.series_registry import SeriesRegistry
    if bool(args.check) == bool(args.ingest):
        print("[series-refresh] exactly one of --check / --ingest required",
              file=sys.stderr)
        return 2
    try:
        today = _dt.date.fromisoformat(args.as_of)
    except ValueError:
        print(f"[series-refresh] malformed --as-of {args.as_of!r} "
              "(need YYYY-MM-DD)", file=sys.stderr)
        return 2
    registry = SeriesRegistry.load(args.series_registry)
    if args.check:
        calendar = load_calendar(args.calendar)
        gaps = find_gaps(registry, calendar, args.series_root, today)
        payload = json.dumps(
            {"gaps": [g.model_dump() for g in gaps]}, indent=1)
        if args.out:
            pathlib.Path(args.out).write_text(payload, "utf-8")
        print(payload)
        return 0
    cand_path = pathlib.Path(args.ingest)
    if not cand_path.is_file():
        print(f"[series-refresh] candidates file not found: {cand_path}",
              file=sys.stderr)
        return 2
    result = ingest_candidates(cand_path.read_text("utf-8"), registry,
                               args.series_root, today=today)
    print(result.model_dump_json(indent=1))
    return 0
```

Parser block (beside the `price-sync` parser) and dispatch (beside `price-sync`'s):

```python
    srf = sub.add_parser("series-refresh",
                         help="F79 G4: calendar gap-check the scoring series / "
                              "ingest validated candidate points (never blocks a cycle)")
    srf.add_argument("--check", action="store_true")
    srf.add_argument("--ingest", help="path to a {'candidates':[...]} envelope JSON")
    srf.add_argument("--as-of", required=True, help="YYYY-MM-DD (the cycle day)")
    srf.add_argument("--series-root", default="store/series")
    srf.add_argument("--calendar", default="registry/series-calendar.json")
    srf.add_argument("--series-registry", default="registry/series-indicators.json")
    srf.add_argument("--out", help="also write the --check gap report here")
```

```python
    if args.cmd == "series-refresh":
        return _series_refresh(args)
```

Match `cli.py`'s existing import style (`sys`, `json`, `pathlib` are already imported at module top — verify before adding).

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/test_cli_series_refresh.py tests/test_series_refresh.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/cli.py tests/test_cli_series_refresh.py
git commit -m "feat(f79-g4): series-refresh CLI verb (--check / --ingest, exit-0 never blocks)"
```

---

### Task 4: Run-cycle steps 7b/7c + F83 lockstep re-record (ONE commit)

**Files:**
- Modify: `.claude/skills/run-cycle/SKILL.md` (Procedure step list + the `run-cycle-step-fingerprint` comment at line ~52)
- Modify: `tests/test_run_cycle_conformance.py` (`EXPECTED_STEPS`, line ~159)

**Interfaces:**
- Consumes: the fingerprint contract — `sha256(repr(EXPECTED_STEPS))` must equal the SKILL.md comment (`test_skill_fingerprint_in_sync`); the SKILL.md step-line format parsed by the conformance test (read `_steps`/parser around line 142 BEFORE editing and mirror the existing step-line syntax exactly).
- Produces: the pinned step list gains, after `("7", "price-sync")`: `("7b", "series-refresh")`, `("7c", "v2 shadow stamp")`.

- [ ] **Step 1: Edit `EXPECTED_STEPS`** in `tests/test_run_cycle_conformance.py`:

```python
    ("7", "price-sync"),
    ("7b", "series-refresh"),
    ("7c", "v2 shadow stamp"),
    ("8", "report"),
```

- [ ] **Step 2: Run the conformance test to watch it fail** (proves the pin has teeth)

Run: `../../.venv/Scripts/python -m pytest tests/test_run_cycle_conformance.py -q`
Expected: FAIL — fingerprint out of sync AND step-list parse mismatch.

- [ ] **Step 3: Edit SKILL.md** — add two steps after the price-sync step, in the exact step-line format the parser expects:

Step **7b — series-refresh** prose (adapt wording to the file's voice; content requirements):
- Run `gpu-agent series-refresh --check --as-of <cycle day> --out work/<cycle>/series-gaps.json`.
- If `gaps` is empty: log `seriesRefresh: no-gap` in the cycle log and move on.
- Per gapped series: dispatch ONE reader subagent with the gap's `sourceHint`; the reader writes `work/<cycle>/series-candidates-<indicatorId>.json` as a `{"candidates": [...]}` envelope (SeriesPoint shape: indicatorId, period YYYY-MM, value, unit per registry, publishedAt, capturedAt, source{url,title}, estimateGrade, note). Readers follow the same no-Bash wall as gatherers.
- Ingest each file via `gpu-agent series-refresh --ingest <file> --as-of <cycle day>`; record written/rejected/alreadyPresent counts in the cycle log (`seriesRefresh` key).
- Any failure (fetch, validation, tool error) is logged and NEVER blocks the cycle (price-sync precedent).

Step **7c — v2 shadow stamp** prose:
- Run `gpu-agent v2-shadow --scorecard store/<category>/<asOf>-v<N>.json` against the scorecard THIS cycle just wrote, BEFORE the cycle commit (the stamped file is what the cycle commits).
- Log `v2Shadow: stamped` (or `skipped-empty-store`) in the cycle log. Never blocks; failure is logged non-fatal.
- Reminder line: v2 renders NOWHERE until the user signs G4 (render tripwire pins this).

- [ ] **Step 4: Regenerate the fingerprint** and paste into the SKILL.md comment:

```bash
../../.venv/Scripts/python -c "import sys, hashlib; sys.path.insert(0, 'tests'); from test_run_cycle_conformance import EXPECTED_STEPS; print(hashlib.sha256(repr(EXPECTED_STEPS).encode()).hexdigest())"
```

(`tests/` is not a package — insert it on `sys.path` and import the module bare, as above.)

- [ ] **Step 5: Run the conformance test to verify it passes**

Run: `../../.venv/Scripts/python -m pytest tests/test_run_cycle_conformance.py -q`
Expected: PASS.

- [ ] **Step 6: Commit (SKILL.md + EXPECTED_STEPS + fingerprint together — the lockstep rule)**

```bash
git add .claude/skills/run-cycle/SKILL.md tests/test_run_cycle_conformance.py
git commit -m "feat(f79-g4): run-cycle steps 7b series-refresh + 7c v2-shadow; F83 pin re-recorded in lockstep"
```

---

### Task 5: Close-out — full suite, forbidden-diff, backlog, sentinel

**Files:**
- Modify: `docs/fix-backlog.md` (F79 entry: append a dated G4-stage note)
- Create: `.superpowers/handoffs/f79-g4-refresh-DONE.md`

- [ ] **Step 1: Full suite from the worktree root**

Run: `../../.venv/Scripts/python -m pytest -q`
Expected: green (baseline 1987+new passed / ~6 skipped). F6 pin, scoring-v1 replay pin, narrator pin GREEN; F83 green at its new fingerprint.

- [ ] **Step 2: Forbidden-diff check**

Run: `git diff main --stat -- fixtures/ registry/indicators.json gpu_agent/evals gpu_agent/narrator gpu_agent/scoring.py gpu_agent/report.py`
Expected: EMPTY. (`git diff main --stat -- registry/` shows ONLY `registry/series-calendar.json`, a new file.)

- [ ] **Step 3: Backlog note** — append to the F79 entry in `docs/fix-backlog.md`, dated 2026-07-28: G4 stage built per spec `2026-07-28-f79-g4-series-refresh-soak-design.md` (series refresh + shadow hook); soak starts on the next scheduled cycle; pass terms pre-committed in the spec; **seed calendar values are assistant-proposed tunable defaults (JSON-edit to change), not user-approved numbers**.

- [ ] **Step 4: DONE sentinel** — `.superpowers/handoffs/f79-g4-refresh-DONE.md`: date, branch, commits, suite count, the F83 re-record note, deferred items, "soak now accumulating — G4 package after ≥5 qualifying cycles (≥2 post-refresh)". STOP — do not merge; only the user merges.

- [ ] **Step 5: Commit**

```bash
git add docs/fix-backlog.md .superpowers/handoffs/f79-g4-refresh-DONE.md
git commit -m "docs(f79-g4): close-out - backlog G4-stage note + DONE sentinel"
```
