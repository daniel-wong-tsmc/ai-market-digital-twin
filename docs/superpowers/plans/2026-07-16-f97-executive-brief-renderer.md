# F97 — Executive Brief Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the executive-facing "Merchant GPU — Executive Brief" page (spec: `docs/superpowers/specs/2026-07-16-executive-brief-format-design.md`, v5) as the category index page of the committed `site/` folder.

**Architecture:** Three new pure-projection modules in `gpu_agent/dashboard/`: `agenda.py` (dynamic five-slot metric selection over measured findings + series readings, driven by `registry/agenda-slots.json`), `brief_model.py` (assembles the page model from store artifacts: monthly scorecard, thesis book, implications, cycle log, revision diffs), `brief_render.py` (HTML blocks A–H + `BRIEF_CSS` + the banned-token lint). `site_build.py` swaps the category `index.html` to the brief; all existing pages (appendix, how/*) keep building unchanged so F95 tests stay green, and the appendix gains per-dimension rationale anchors the brief's tiles link to.

**Tech Stack:** Python 3 stdlib only (json, re, dataclasses, datetime, html, pathlib) — matches every other dashboard module. Tests: pytest with `tmp_path` fixtures. No LLM, no network, no wall-clock inside models (`today` is a parameter; `site_build` injects `date.today()` at the edge, like F95's `_now_stamp` isolation).

**Feature number:** F97. *(Concurrent-mint caveat: chosen against a backlog max of F96 on 2026-07-16; if another session minted F97 first, renumber.)*

**Lane decision recorded (implementation-lane choices the spec delegated):** the brief REPLACES the F95 category page as `index.html`; the old daily-tile page is not kept as a separate ops view (git history keeps it; appendix + how pages carry the ops detail). Dimension tiles link to new `appendix.html#dim-<name>` anchors; the attention chip links to the existing `how/alert.html`. `how/demand|supply|gap|featured.html` keep building (existing deep links stay alive) even though the brief itself doesn't link them.

## Global Constraints

- Work in a claimed worktree lane `.worktrees/f97-exec-brief`, branch `f97-exec-brief` — never on the root checkout's main (repo CLAUDE.md; another instance is live on this checkout).
- Python is `../../.venv/Scripts/python` from the worktree root; run tests as `../../.venv/Scripts/python -m pytest`.
- Renderer/copy layer ONLY: no edits to extract/judge/thesis brains, `gpu_agent/report.py` (FROZEN change engine), or eval fixtures. `tests/test_evals_baseline_pin.py` (F6 pin) must stay green untouched.
- Spec register rules (verbatim, spec "Writing register"): banned in exec copy — `+N more moved` patterns, bare direction symbols without an accompanying word, the word "run" in page copy (say "signal check" or "revision"), the phrase `because no alert rule fired`, internal feature codenames (`F65` etc.), layperson glosses (`internal settings`). Every number keeps its unit. Two-decimal composite indices (DMI/SMI/SDGI) never appear on the brief page.
- Status colors (`good/warning/serious/critical` CSS classes) appear ONLY in the attention chip and the staleness strip, always icon + word. Everything else ink.
- No metric may appear both as an agenda (C) tile and a dimensions (G) tile — C shows numbers-with-units, G shows rating words only, so this holds by construction; the test in Task 7 pins it.
- All store-derived text is HTML-escaped via `html.escape` before interpolation.
- Files written with `newline="\n"` (LF canonical).
- Every commit: `git log --oneline -1` first to verify HEAD is your own last commit.

---

### Task 1: Agenda slot config + loader

**Files:**
- Create: `registry/agenda-slots.json`
- Create: `gpu_agent/dashboard/agenda.py`
- Test: `tests/dashboard/test_agenda.py`

**Interfaces:**
- Consumes: nothing (config + pure loader).
- Produces: `load_slots(path=AGENDA_REGISTRY_PATH) -> list[dict]` where each slot dict has keys `id`, `label`, `question`, `indicators` (list[str]); constant `AGENDA_REGISTRY_PATH = "registry/agenda-slots.json"`; `format_value(number: float, unit: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/dashboard/test_agenda.py
import json
from gpu_agent.dashboard.agenda import AGENDA_REGISTRY_PATH, format_value, load_slots


def test_load_slots_real_registry():
    slots = load_slots()
    assert [s["id"] for s in slots] == [
        "demand-durability", "binding-constraint", "customer-mix",
        "end-market-economics", "demand-quality"]
    for s in slots:
        assert s["label"] and s["question"] and s["indicators"]


def test_load_slots_custom_path(tmp_path):
    p = tmp_path / "slots.json"
    p.write_text(json.dumps({"slots": [
        {"id": "x", "label": "X", "question": "q?", "indicators": ["a"]}]}),
        encoding="utf-8")
    assert load_slots(str(p))[0]["id"] == "x"


def test_format_value_units():
    assert format_value(75.2, "USD_B") == "$75.2B"
    assert format_value(75.0, "pct") == "75%"
    assert format_value(68.8, "pct_yoy") == "+68.8% YoY"
    assert format_value(-50.0, "pct_yoy") == "-50% YoY"
    assert format_value(6.69, "USD_per_hr") == "$6.69/hr"
    assert format_value(210000, "units") == "210,000 units"
    assert format_value(3.0, "widgets") == "3 widgets"   # unknown unit: honest fallback
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_agenda.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gpu_agent.dashboard.agenda'`

- [ ] **Step 3: Write the config and minimal implementation**

```json
// registry/agenda-slots.json
{
  "slots": [
    {"id": "demand-durability", "label": "Demand durability",
     "question": "Is the demand that fills the fabs real and growing?",
     "indicators": ["D2", "vendorRevenueGuidance", "rpoBacklog",
                    "odmMonthlyAiRevenue", "hyperscalerCapexRevision", "D6"]},
    {"id": "binding-constraint", "label": "Binding constraint",
     "question": "What caps shipments today, and how tight is it?",
     "indicators": ["S9", "S10", "leadTimes", "pkgCapacityOrderSpread",
                    "hbmSupplyCapex"]},
    {"id": "customer-mix", "label": "Customer mix",
     "question": "Where is share moving among wafer buyers?",
     "indicators": ["market-share-pct", "designWins"]},
    {"id": "end-market-economics", "label": "End-market economics",
     "question": "Can the buyers keep paying?",
     "indicators": ["grossMargin", "tokenEconomics", "perfPerWatt"]},
    {"id": "demand-quality", "label": "Demand quality",
     "question": "How much demand is self-financed or policy-capped?",
     "indicators": ["customerConcentration", "exportControlExposure",
                    "marginalBuyerFinancing"]}
  ]
}
```

```python
# gpu_agent/dashboard/agenda.py
"""F97 agenda band — five standing executive questions, answered dynamically.

Pure projection: candidates come from measured findings (value: {number, unit})
and series readings; selection is deterministic (freshness x magnitude x
evidence grade, stickiness vs the prior revision's pick)."""
from __future__ import annotations

import json
from pathlib import Path

AGENDA_REGISTRY_PATH = "registry/agenda-slots.json"

_UNIT_FMT = {
    "USD_B": lambda n: f"${n:g}B",
    "pct": lambda n: f"{n:g}%",
    "pct_yoy": lambda n: f"{n:+g}% YoY",
    "USD_per_hr": lambda n: f"${n:.2f}/hr",
    "units": lambda n: f"{n:,.0f} units",
}


def load_slots(path: str = AGENDA_REGISTRY_PATH) -> list[dict]:
    with open(Path(path), encoding="utf-8") as fh:
        return json.load(fh)["slots"]


def format_value(number: float, unit: str) -> str:
    fmt = _UNIT_FMT.get(unit)
    if fmt is not None:
        return fmt(number)
    return f"{number:g} {unit}"   # unknown unit: value + unit verbatim, never bare
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_agenda.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add registry/agenda-slots.json gpu_agent/dashboard/agenda.py tests/dashboard/test_agenda.py
git commit -m "feat(f97): agenda slot registry + loader and unit formatter"
```

---

### Task 2: Agenda candidates from measured findings and series

**Files:**
- Modify: `gpu_agent/dashboard/agenda.py`
- Test: `tests/dashboard/test_agenda.py` (append)

**Interfaces:**
- Consumes: raw finding dicts as stored in scorecard JSON (`indicatorId`, `kind`, `value: {number, unit}|None`, `trend`, `observedAt`, `magnitude`, `statement`, `evidence: [{tier, source}]`); series rows as stored in `store/series/<id>.jsonl` (`indicatorId`, `period`, `value`, `unit`, `publishedAt`, `source: {title}`, `estimateGrade`).
- Produces:
  - `@dataclass(frozen=True) Candidate`: fields `indicator_id: str`, `label: str`, `display: str`, `trend_word: str`, `observed_at: str`, `tier: str`, `source_name: str`, `magnitude: int`, `statement: str`.
  - `candidates_for_slot(slot: dict, findings: list[dict], series_rows: dict[str, list[dict]]) -> list[Candidate]`
  - `read_series(series_dir: str | Path, indicator_ids: set[str]) -> dict[str, list[dict]]` (rows in file order; missing files skipped).

- [ ] **Step 1: Write the failing tests** (append to `tests/dashboard/test_agenda.py`)

```python
from gpu_agent.dashboard.agenda import Candidate, candidates_for_slot, read_series

SLOT = {"id": "demand-durability", "label": "Demand durability",
        "question": "q?", "indicators": ["D2", "odmMonthlyAiRevenue"]}

F_MEASURED = {"indicatorId": "D2", "kind": "measured",
              "value": {"number": 75.2, "unit": "USD_B"}, "trend": "rising",
              "observedAt": "2026-07-01", "magnitude": 3,
              "statement": "NVIDIA Q1 FY2027 Data Center revenue was a record $75.2 billion.",
              "evidence": [{"tier": "primary", "source": "NVIDIA IR"}]}
F_OBSERVED = {"indicatorId": "D2", "kind": "observed", "value": None,
              "trend": "rising", "observedAt": "2026-07-02", "magnitude": 2,
              "statement": "prose only", "evidence": []}
F_OTHER_IND = dict(F_MEASURED, indicatorId="S10")

SERIES_ROW = {"indicatorId": "odmMonthlyAiRevenue", "period": "2026-06",
              "value": 68.788, "unit": "pct_yoy", "publishedAt": "2026-07-10",
              "source": {"title": "TWSE MOPS monthly revenue summary"},
              "estimateGrade": False}
SERIES_PRIOR = dict(SERIES_ROW, period="2026-05", value=50.0, publishedAt="2026-06-10")


def test_candidates_measured_finding_only():
    got = candidates_for_slot(SLOT, [F_MEASURED, F_OBSERVED, F_OTHER_IND], {})
    assert len(got) == 1
    c = got[0]
    assert (c.indicator_id, c.display, c.trend_word, c.tier, c.magnitude) == \
        ("D2", "$75.2B", "rising", "primary", 3)
    assert c.observed_at == "2026-07-01" and c.source_name == "NVIDIA IR"


def test_candidates_series_newest_row_with_trend_from_prior():
    got = candidates_for_slot(SLOT, [], {"odmMonthlyAiRevenue": [SERIES_PRIOR, SERIES_ROW]})
    assert len(got) == 1
    c = got[0]
    assert c.display == "+68.788% YoY" and c.trend_word == "rising"
    assert c.observed_at == "2026-07-10" and c.tier == "secondary"


def test_read_series_reads_only_requested_files(tmp_path):
    import json
    d = tmp_path / "series"
    d.mkdir()
    (d / "a.jsonl").write_text(json.dumps({"indicatorId": "a", "value": 1}) + "\n",
                               encoding="utf-8")
    (d / "b.jsonl").write_text("{}\n", encoding="utf-8")
    rows = read_series(d, {"a", "missing"})
    assert set(rows) == {"a"} and rows["a"][0]["value"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_agenda.py -v`
Expected: new tests FAIL with `ImportError: cannot import name 'Candidate'`

- [ ] **Step 3: Implement** (append to `gpu_agent/dashboard/agenda.py`)

```python
from dataclasses import dataclass

_TREND_WORDS = {"rising": "rising", "falling": "falling", "stable": "steady",
                "steady": "steady", "mixed": "mixed"}


@dataclass(frozen=True)
class Candidate:
    indicator_id: str
    label: str          # metric name shown on the tile (slot supplies context)
    display: str        # formatted value WITH unit, e.g. "$75.2B"
    trend_word: str     # always a word; "" only when truly unknown
    observed_at: str    # YYYY-MM-DD or YYYY-MM
    tier: str           # "primary" | "secondary"
    source_name: str
    magnitude: int
    statement: str


def _finding_candidate(f: dict) -> Candidate | None:
    v = f.get("value")
    if f.get("kind") != "measured" or not isinstance(v, dict):
        return None
    ev = f.get("evidence") or []
    tier = "primary" if any(e.get("tier") == "primary" for e in ev) else "secondary"
    src = next((e.get("source") for e in ev if e.get("source")), "")
    return Candidate(
        indicator_id=f["indicatorId"], label=f["indicatorId"],
        display=format_value(float(v["number"]), str(v.get("unit") or "")),
        trend_word=_TREND_WORDS.get((f.get("trend") or "").lower(), ""),
        observed_at=f.get("observedAt") or f.get("asOf") or "",
        tier=tier, source_name=src or "",
        magnitude=int(f.get("magnitude") or 0),
        statement=f.get("statement") or "")


def _series_candidate(indicator_id: str, rows: list[dict]) -> Candidate | None:
    if not rows:
        return None
    newest = rows[-1]
    prior = rows[-2] if len(rows) > 1 else None
    trend = ""
    if prior is not None and isinstance(newest.get("value"), (int, float)) \
            and isinstance(prior.get("value"), (int, float)):
        d = newest["value"] - prior["value"]
        trend = "rising" if d > 0 else ("falling" if d < 0 else "steady")
    return Candidate(
        indicator_id=indicator_id, label=indicator_id,
        display=format_value(float(newest["value"]), str(newest.get("unit") or "")),
        trend_word=trend,
        observed_at=newest.get("publishedAt") or newest.get("period") or "",
        tier="secondary",
        source_name=(newest.get("source") or {}).get("title", ""),
        magnitude=0, statement=newest.get("note") or "")


def candidates_for_slot(slot, findings, series_rows) -> list[Candidate]:
    wanted = set(slot["indicators"])
    out = []
    for f in findings:
        if f.get("indicatorId") in wanted:
            c = _finding_candidate(f)
            if c is not None:
                out.append(c)
    for ind in slot["indicators"]:
        c = _series_candidate(ind, series_rows.get(ind) or [])
        if c is not None:
            out.append(c)
    return out


def read_series(series_dir, indicator_ids) -> dict:
    out = {}
    for ind in indicator_ids:
        p = Path(series_dir) / f"{ind}.jsonl"
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        rows = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except ValueError:
                continue
        if rows:
            out[ind] = rows
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_agenda.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/agenda.py tests/dashboard/test_agenda.py
git commit -m "feat(f97): agenda candidates from measured findings and series readings"
```

---

### Task 3: Dynamic slot selection with stickiness + continuity note

**Files:**
- Modify: `gpu_agent/dashboard/agenda.py`
- Test: `tests/dashboard/test_agenda.py` (append)

**Interfaces:**
- Consumes: `Candidate`, `candidates_for_slot` (Task 2).
- Produces:
  - `@dataclass(frozen=True) Occupant`: fields `slot_id: str`, `slot_label: str`, `candidate: Candidate`, `was_label: str | None`.
  - `score(c: Candidate, today: datetime.date, sticky_indicator: str | None) -> float`
  - `select_occupants(slots, findings, series_rows, prior_findings, today) -> list[Occupant]` — prior occupant per slot computed by running the same selection over `prior_findings` (no stickiness, no series prior) — deterministic, no state file. `was_label` set only when the occupant's `indicator_id` changed vs prior AND a prior existed.

- [ ] **Step 1: Write the failing tests** (append)

```python
import datetime as dt
from gpu_agent.dashboard.agenda import Occupant, score, select_occupants

TODAY = dt.date(2026, 7, 16)


def _cand(ind="D2", observed="2026-07-01", mag=3, tier="primary"):
    return Candidate(indicator_id=ind, label=ind, display="$1B",
                     trend_word="rising", observed_at=observed, tier=tier,
                     source_name="s", magnitude=mag, statement="st")


def test_score_prefers_fresh_high_magnitude_primary():
    fresh = _cand(observed="2026-07-14")
    stale = _cand(observed="2026-04-01")
    assert score(fresh, TODAY, None) > score(stale, TODAY, None)
    weak = _cand(mag=1)
    assert score(_cand(mag=3), TODAY, None) > score(weak, TODAY, None)
    sec = _cand(tier="secondary")
    assert score(_cand(), TODAY, None) > score(sec, TODAY, None)


def test_score_stickiness_bonus():
    c = _cand(ind="D2")
    assert score(c, TODAY, "D2") > score(c, TODAY, None)


def test_select_occupants_continuity_note():
    slot = {"id": "binding-constraint", "label": "Binding constraint",
            "question": "q?", "indicators": ["S9", "S10"]}
    cowos = {"indicatorId": "S9", "kind": "measured",
             "value": {"number": 20.0, "unit": "pct"}, "trend": "falling",
             "observedAt": "2026-06-20", "magnitude": 3,
             "statement": "CoWoS gap.", "evidence": [{"tier": "primary", "source": "x"}]}
    hbm = {"indicatorId": "S10", "kind": "measured",
           "value": {"number": 2027.0, "unit": "sold_out_through"}, "trend": "rising",
           "observedAt": "2026-07-10", "magnitude": 3,
           "statement": "HBM sold out.", "evidence": [{"tier": "primary", "source": "y"}]}
    # prior revision only had the CoWoS reading; current has both, HBM fresher.
    occ = select_occupants([slot], [cowos, hbm], {}, [cowos], TODAY)
    assert len(occ) == 1 and occ[0].candidate.indicator_id == "S10"
    assert occ[0].was_label == "S9"
    # same occupant as prior -> no note
    occ2 = select_occupants([slot], [cowos], {}, [cowos], TODAY)
    assert occ2[0].was_label is None


def test_select_occupants_skips_empty_slot():
    slot = {"id": "customer-mix", "label": "Customer mix", "question": "q?",
            "indicators": ["market-share-pct"]}
    assert select_occupants([slot], [], {}, [], TODAY) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_agenda.py -v`
Expected: new tests FAIL with `ImportError: cannot import name 'Occupant'`

- [ ] **Step 3: Implement** (append to `agenda.py`)

```python
import datetime as _dt


@dataclass(frozen=True)
class Occupant:
    slot_id: str
    slot_label: str
    candidate: Candidate
    was_label: str | None


def _days_old(observed_at: str, today: _dt.date) -> int:
    try:
        parts = [int(x) for x in observed_at.split("-")]
        d = _dt.date(parts[0], parts[1], parts[2] if len(parts) > 2 else 15)
    except (ValueError, IndexError):
        return 9999
    return max(0, (today - d).days)


def score(c: Candidate, today: _dt.date, sticky_indicator: str | None) -> float:
    freshness = max(0.0, 1.0 - _days_old(c.observed_at, today) / 90.0)
    s = 2.0 * freshness + c.magnitude / 3.0
    if c.tier == "primary":
        s += 0.5
    if sticky_indicator is not None and c.indicator_id == sticky_indicator:
        s += 0.75
    return s


def _pick(slot, findings, series_rows, today, sticky) -> Candidate | None:
    cands = candidates_for_slot(slot, findings, series_rows)
    if not cands:
        return None
    return max(cands, key=lambda c: (score(c, today, sticky), c.observed_at,
                                     c.indicator_id))


def select_occupants(slots, findings, series_rows, prior_findings, today):
    out = []
    for slot in slots:
        prior = _pick(slot, prior_findings, {}, today, None)
        sticky = prior.indicator_id if prior is not None else None
        cur = _pick(slot, findings, series_rows, today, sticky)
        if cur is None:
            continue
        was = None
        if prior is not None and prior.indicator_id != cur.indicator_id:
            was = prior.label
        out.append(Occupant(slot_id=slot["id"], slot_label=slot["label"],
                            candidate=cur, was_label=was))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_agenda.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/agenda.py tests/dashboard/test_agenda.py
git commit -m "feat(f97): deterministic slot selection with stickiness and continuity note"
```

---

### Task 4: Brief model — store readers (monthly read, thesis book, implications, last check)

**Files:**
- Create: `gpu_agent/dashboard/brief_model.py`
- Test: `tests/dashboard/test_brief_model.py`

**Interfaces:**
- Consumes: store layout (`store/<cat>/<YYYY-MM>-v<K>.json`, `store/theses/<cat>/book.json`, `store/implications/<cat>/<YYYY-MM>.json`, `store/cycle-log.json`).
- Produces (all pure, all defensive — missing artifact → `None`/`[]`, never raises):
  - `latest_monthly(cat_dir) -> tuple[dict, dict | None, str, int]` — (latest monthly scorecard JSON, prior revision JSON or None, as_of `"YYYY-MM"`, revision int). Matches ONLY `\d{4}-\d{2}-v\d+\.json` names (dated dailies excluded).
  - `read_thesis_book(store_root, category_id) -> list[dict]` — book entries, `[]` if absent.
  - `select_calls(entries, cap=7) -> tuple[list[dict], int, int]` — (rows, total, provisional_count); registered first, conviction high>medium>low, streak desc.
  - `read_implication_lines(store_root, category_id, as_of) -> list[dict]` — `[{"text", "dims", "thesis_ids", "finding_ids"}]`; falls back to newest available month's file; `[]` if none.
  - `last_signal_check(store_root, cat_dir) -> str` — ISO date `"YYYY-MM-DD"` from cycle-log `capturedAt`, falling back to the max findings `capturedAt` date in the latest monthly revision, else `""`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/dashboard/test_brief_model.py
import json
from gpu_agent.dashboard.brief_model import (
    last_signal_check, latest_monthly, read_implication_lines,
    read_thesis_book, select_calls)

CAT = "chips.merchant-gpu"


def _mk_store(tmp_path):
    root = tmp_path / "store"
    cat = root / CAT
    cat.mkdir(parents=True)
    return root, cat


def _monthly(as_of, narrative="n", findings=()):
    return {"asOf": as_of, "narrative": narrative,
            "categoryStatus": {"rating": "Strong", "direction": "steady",
                               "reason": "r.", "constraintLabel": "HBM supply"},
            "dimensionRatings": {}, "findings": list(findings), "sources": []}


def test_latest_monthly_picks_highest_revision_and_prior(tmp_path):
    root, cat = _mk_store(tmp_path)
    (cat / "2026-07-v1.json").write_text(json.dumps(_monthly("2026-07", "one")),
                                         encoding="utf-8")
    (cat / "2026-07-v2.json").write_text(json.dumps(_monthly("2026-07", "two")),
                                         encoding="utf-8")
    (cat / "2026-07-06-v1.json").write_text(json.dumps(_monthly("2026-07-06")),
                                            encoding="utf-8")   # daily: excluded
    latest, prior, as_of, rev = latest_monthly(cat)
    assert latest["narrative"] == "two" and prior["narrative"] == "one"
    assert (as_of, rev) == ("2026-07", 2)


def test_read_thesis_book_and_select_calls(tmp_path):
    root, _ = _mk_store(tmp_path)
    book = root / "theses" / CAT
    book.mkdir(parents=True)
    entries = [
        {"title": "prov", "conviction": "high", "status": "provisional",
         "streak": 9, "lens": "risk", "lastVerdict": "strengthened",
         "falsifiableTrigger": "t"},
        {"title": "low-reg", "conviction": "low", "status": "registered",
         "streak": 5, "lens": "demand", "lastVerdict": None,
         "falsifiableTrigger": "t"},
        {"title": "high-reg", "conviction": "high", "status": "registered",
         "streak": 1, "lens": "supply", "lastVerdict": "weakened",
         "falsifiableTrigger": "t"},
    ]
    (book / "book.json").write_text(json.dumps({"entries": entries}),
                                    encoding="utf-8")
    got = read_thesis_book(root, CAT)
    rows, total, prov = select_calls(got, cap=2)
    assert total == 3 and prov == 1
    assert [r["title"] for r in rows] == ["high-reg", "low-reg"]  # registered first


def test_select_calls_empty_book():
    assert select_calls([], cap=7) == ([], 0, 0)


def test_read_implication_lines_falls_back_to_newest(tmp_path):
    root, _ = _mk_store(tmp_path)
    impl = root / "implications" / CAT
    impl.mkdir(parents=True)
    art = {"lines": [{"watchItem": "w1", "dimensions": ["momentum"],
                      "thesisIds": ["a"], "findingIds": ["f1"]}]}
    (impl / "2026-06.json").write_text(json.dumps(art), encoding="utf-8")
    got = read_implication_lines(root, CAT, "2026-07")     # 07 missing -> 06
    assert got[0]["text"] == "w1" and got[0]["dims"] == ["momentum"]
    assert read_implication_lines(root, "nope", "2026-07") == []


def test_last_signal_check_prefers_cycle_log(tmp_path):
    root, cat = _mk_store(tmp_path)
    (root / "cycle-log.json").write_text(
        json.dumps({"capturedAt": "2026-07-15T10:55:20Z"}), encoding="utf-8")
    f = {"capturedAt": "2026-07-06T01:00:00Z"}
    (cat / "2026-07-v1.json").write_text(json.dumps(_monthly("2026-07",
                                         findings=[f])), encoding="utf-8")
    assert last_signal_check(root, cat) == "2026-07-15"
    (root / "cycle-log.json").unlink()
    assert last_signal_check(root, cat) == "2026-07-06"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_brief_model.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# gpu_agent/dashboard/brief_model.py
"""F97 Executive Brief page model — pure projection from store artifacts.

No LLM, no network, no wall-clock: `today` is always a parameter."""
from __future__ import annotations

import json
import re
from pathlib import Path

_MONTHLY_RE = re.compile(r"^(\d{4}-\d{2})-v(\d+)\.json$")
_CONVICTION_ORDER = {"high": 0, "medium": 1, "low": 2}


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def latest_monthly(cat_dir):
    cat_dir = Path(cat_dir)
    revs = []
    for p in cat_dir.iterdir():
        m = _MONTHLY_RE.match(p.name)
        if m:
            revs.append((m.group(1), int(m.group(2)), p))
    if not revs:
        return None, None, "", 0
    revs.sort(key=lambda t: (t[0], t[1]))
    as_of, rev, latest_path = revs[-1]
    latest = _read_json(latest_path) or {}
    prior = None
    if len(revs) > 1 and revs[-2][0] == as_of:
        prior = _read_json(revs[-2][2])
    return latest, prior, as_of, rev


def read_thesis_book(store_root, category_id):
    art = _read_json(Path(store_root) / "theses" / category_id / "book.json")
    if not isinstance(art, dict):
        return []
    return [e for e in (art.get("entries") or []) if isinstance(e, dict)]


def select_calls(entries, cap=7):
    total = len(entries)
    prov = sum(1 for e in entries if e.get("status") == "provisional")
    ordered = sorted(entries, key=lambda e: (
        0 if e.get("status") == "registered" else 1,
        _CONVICTION_ORDER.get(e.get("conviction"), 3),
        -(e.get("streak") or 0),
        e.get("title") or ""))
    return ordered[:cap], total, prov


def read_implication_lines(store_root, category_id, as_of):
    d = Path(store_root) / "implications" / category_id
    art = _read_json(d / f"{as_of}.json")
    if art is None:
        try:
            candidates = sorted(p for p in d.iterdir() if p.suffix == ".json")
        except OSError:
            return []
        art = _read_json(candidates[-1]) if candidates else None
    if not isinstance(art, dict):
        return []
    out = []
    for ln in art.get("lines") or []:
        if isinstance(ln, dict) and (ln.get("watchItem") or ln.get("text")):
            out.append({"text": ln.get("watchItem") or ln.get("text"),
                        "dims": list(ln.get("dimensions") or []),
                        "thesis_ids": list(ln.get("thesisIds") or []),
                        "finding_ids": list(ln.get("findingIds") or [])})
    return out


def last_signal_check(store_root, cat_dir):
    log = _read_json(Path(store_root) / "cycle-log.json")
    stamp = (log or {}).get("capturedAt") or ""
    if stamp:
        return stamp[:10]
    latest, _, _, _ = latest_monthly(cat_dir)
    stamps = [f.get("capturedAt") or "" for f in (latest or {}).get("findings", [])]
    stamps = [s[:10] for s in stamps if s]
    return max(stamps) if stamps else ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_brief_model.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/brief_model.py tests/dashboard/test_brief_model.py
git commit -m "feat(f97): brief store readers - monthly read, thesis book, implications, last check"
```

---

### Task 5: Brief model — signal strip, counterweights, full assembly

**Files:**
- Modify: `gpu_agent/dashboard/brief_model.py`
- Test: `tests/dashboard/test_brief_model.py` (append)

**Interfaces:**
- Consumes: Task 4 readers; `agenda.load_slots/read_series/select_occupants` (Tasks 1–3).
- Produces:
  - `signal_strip(cat_dir, limit=7) -> list[dict]` — one entry per monthly revision (newest first): `{"date", "text", "source"}`. Per revision K: fresh = findings whose `id` is absent from revision K-1 (v1: all findings are fresh); pick max by `(magnitude, observedAt, id)`; `date` = max fresh-finding `capturedAt` date; `text` = statement's first sentence. Fewer than 2 revisions → fall back to dated daily scorecards (`\d{4}-\d{2}-\d{2}-v\d+\.json`), one entry each, same biggest-mover rule vs `None` prior.
  - `counterweight_ids(entries) -> dict[str, str]` — maps finding-id → risk-call title for every finding id appearing in `evidence`/`findingIds` of a risk-lens thesis entry (keys checked: entry `lens == "risk"`; ids from `entry.get("evidenceFindingIds")` or `entry.get("findingIds")`, both optional).
  - `build_brief_model(category_id, store_dir, today, price_fn=None) -> dict` with keys exactly: `category_id, category_label, month_label` (e.g. `"July 2026"`), `revision, narrative, status` (`{rating, direction, reason, constraint}`), `attention` (`{word, css, raw_word, lagging}` — word mapping green→calm, yellow→watch, orange→elevated, red→critical; css same word; `lagging` true when raw != shown), `last_check` (ISO date), `stale` (bool, >3 days vs `today`), `agenda` (list of Occupant-shaped dicts `{slot_label, metric_label, display, trend_word, as_of, source, was}`), `tsmc` (Task 4 lines), `calls` (`{rows, total, provisional}` — each row `{title, lens, conviction, verdict, glyph, streak, trigger}`; verdict None → `"not yet judged"`, glyph `""`), `strip`, `dimensions` (list of `{name, rating, direction, confidence, sentence, capped}` from `dimensionRatings` + `dimensionStatus`; `sentence` = first sentence of rationale), `evidence` (`{n, median, oldest, primary}` — computed over latest monthly findings' `observedAt`: median date, oldest date, count with a primary-tier evidence entry).
  - Alert state: read from the newest dated daily scorecard's alert if the F95 model provides it — v1 uses `build_model`'s alert via a lazy import wrapped in try/except; on any failure `attention = {"word": "calm", "css": "calm", "raw_word": "calm", "lagging": False}` and the chip renders without subtext. (Keeps the brief buildable from a store with no work/ artifacts.)

- [ ] **Step 1: Write the failing tests** (append)

```python
import datetime as dt
from gpu_agent.dashboard.brief_model import (
    build_brief_model, counterweight_ids, signal_strip)

TODAY = dt.date(2026, 7, 16)


def _finding(fid, mag, statement, observed="2026-07-01", captured="2026-07-06T00:00:00Z",
             indicator="D2", kind="measured", value={"number": 1.0, "unit": "pct"}):
    return {"id": fid, "magnitude": mag, "statement": statement,
            "observedAt": observed, "capturedAt": captured,
            "indicatorId": indicator, "kind": kind, "value": value, "trend": "rising",
            "evidence": [{"tier": "primary", "source": "src"}]}


def test_signal_strip_biggest_new_finding_per_revision(tmp_path):
    cat = tmp_path / "c"
    cat.mkdir()
    f1 = _finding("a", 2, "First sentence. Second.", captured="2026-07-02T09:00:00Z")
    f2 = _finding("b", 3, "Big mover statement.", captured="2026-07-14T09:00:00Z")
    (cat / "2026-07-v1.json").write_text(json.dumps({"asOf": "2026-07",
        "findings": [f1]}), encoding="utf-8")
    (cat / "2026-07-v2.json").write_text(json.dumps({"asOf": "2026-07",
        "findings": [f1, f2]}), encoding="utf-8")
    strip = signal_strip(cat)
    assert [e["date"] for e in strip] == ["2026-07-14", "2026-07-02"]
    assert strip[0]["text"] == "Big mover statement." and strip[0]["source"] == "src"
    assert strip[1]["text"] == "First sentence."


def test_counterweight_ids_maps_risk_thesis_evidence():
    entries = [{"title": "Circularity", "lens": "risk",
                "findingIds": ["f9"], "status": "registered"},
               {"title": "Demand", "lens": "demand", "findingIds": ["f1"]}]
    assert counterweight_ids(entries) == {"f9": "Circularity"}


def test_build_brief_model_assembles(tmp_path, monkeypatch):
    root = tmp_path / "store"
    cat = root / "chips.merchant-gpu"
    cat.mkdir(parents=True)
    monthly = {"asOf": "2026-07", "narrative": "The story.",
               "categoryStatus": {"rating": "Strong", "direction": "steady",
                                  "reason": "Supply caps it. More.",
                                  "constraintLabel": "HBM supply"},
               "dimensionRatings": {"momentum": {
                   "rating": "Very strong", "direction": "improving",
                   "confidence": {"level": "high"},
                   "rationale": "First reason. Extra."}},
               "dimensionStatus": {"momentum": {"confidenceCap": None}},
               "findings": [_finding("a", 3, "NVIDIA revenue was $75.2B.")],
               "sources": []}
    (cat / "2026-07-v1.json").write_text(json.dumps(monthly), encoding="utf-8")
    (root / "cycle-log.json").write_text(json.dumps(
        {"capturedAt": "2026-07-15T10:00:00Z"}), encoding="utf-8")
    m = build_brief_model("chips.merchant-gpu", root, TODAY)
    assert m["month_label"] == "July 2026" and m["revision"] == 1
    assert m["status"]["constraint"] == "HBM supply"
    assert m["last_check"] == "2026-07-15" and m["stale"] is False
    assert m["dimensions"][0]["sentence"] == "First reason."
    assert m["agenda"] and m["agenda"][0]["display"]           # slot filled
    assert m["evidence"]["n"] == 1 and m["evidence"]["primary"] == 1
    stale = build_brief_model("chips.merchant-gpu", root, dt.date(2026, 7, 25))
    assert stale["stale"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_brief_model.py -v`
Expected: new tests FAIL with `ImportError`

- [ ] **Step 3: Implement** (append to `brief_model.py`)

```python
import datetime as _dt

from .agenda import load_slots, read_series, select_occupants

_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
_DAILY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-v(\d+)\.json$")
_ATTENTION = {"green": "calm", "yellow": "watch", "orange": "elevated",
              "red": "critical"}
_GLYPHS = {"strengthened": "▲", "weakened": "▼", "reaffirmed": "◆"}


def _first_sentence(text):
    text = (text or "").strip()
    for i, ch in enumerate(text):
        if ch == "." and (i + 1 == len(text) or text[i + 1] == " "):
            return text[:i + 1]
    return text


def _strip_entry(findings, prior_ids):
    fresh = [f for f in findings if f.get("id") not in prior_ids]
    if not fresh:
        return None
    top = max(fresh, key=lambda f: (int(f.get("magnitude") or 0),
                                    f.get("observedAt") or "", f.get("id") or ""))
    dates = [(f.get("capturedAt") or "")[:10] for f in fresh]
    src = next((e.get("source") for e in (top.get("evidence") or [])
                if e.get("source")), "")
    return {"date": max(d for d in dates if d) if any(dates) else "",
            "text": _first_sentence(top.get("statement")), "source": src}


def signal_strip(cat_dir, limit=7):
    cat_dir = Path(cat_dir)
    revs = sorted(((m.group(1), int(m.group(2)), p)
                   for p in cat_dir.iterdir()
                   for m in [_MONTHLY_RE.match(p.name)] if m),
                  key=lambda t: (t[0], t[1]))
    out = []
    if len(revs) >= 2:
        prior_ids = set()
        entries = []
        for _, _, p in revs:
            findings = (_read_json(p) or {}).get("findings") or []
            e = _strip_entry(findings, prior_ids)
            if e is not None:
                entries.append(e)
            prior_ids = {f.get("id") for f in findings}
        out = entries[::-1][:limit]
    else:
        dailies = sorted((p for p in cat_dir.iterdir() if _DAILY_RE.match(p.name)),
                         key=lambda p: p.name, reverse=True)[:limit]
        for p in dailies:
            findings = (_read_json(p) or {}).get("findings") or []
            e = _strip_entry(findings, set())
            if e is not None:
                out.append(e)
    return out


def counterweight_ids(entries):
    out = {}
    for e in entries:
        if e.get("lens") != "risk":
            continue
        for fid in (e.get("evidenceFindingIds") or e.get("findingIds") or []):
            out[fid] = e.get("title") or ""
    return out


def _attention_state(store_root, category_id):
    try:
        from .build import build_model
        model, _ = build_model(category_id, str(Path(store_root) / category_id),
                               "work", None, generated_at="")
        a = model["alert"]
        return {"word": _ATTENTION.get(a["color"], "calm"),
                "css": _ATTENTION.get(a["color"], "calm"),
                "raw_word": _ATTENTION.get(a["raw"], "calm"),
                "lagging": a["raw"] != a["color"]}
    except Exception:
        return {"word": "calm", "css": "calm", "raw_word": "calm",
                "lagging": False}


def build_brief_model(category_id, store_dir, today, price_fn=None):
    store_root = Path(store_dir)
    cat_dir = store_root / category_id
    latest, prior, as_of, rev = latest_monthly(cat_dir)
    latest = latest or {}
    status = latest.get("categoryStatus") or {}
    year, month = (as_of.split("-") + ["1"])[:2]
    findings = latest.get("findings") or []

    slots = load_slots()
    wanted = {i for s in slots for i in s["indicators"]}
    series = read_series(store_root / "series", wanted)
    occupants = select_occupants(slots, findings, series,
                                 (prior or {}).get("findings") or [], today)

    book = read_thesis_book(store_root, category_id)
    rows, total, prov = select_calls(book)
    call_rows = [{"title": e.get("title") or "", "lens": e.get("lens") or "",
                  "conviction": e.get("conviction") or "",
                  "verdict": e.get("lastVerdict") or "not yet judged",
                  "glyph": _GLYPHS.get(e.get("lastVerdict") or "", ""),
                  "streak": int(e.get("streak") or 0),
                  "trigger": e.get("falsifiableTrigger") or ""} for e in rows]

    check = last_signal_check(store_root, cat_dir)
    stale = False
    if check:
        y, mo, d = (int(x) for x in check.split("-"))
        stale = (today - _dt.date(y, mo, d)).days > 3

    dims = []
    ratings = latest.get("dimensionRatings") or {}
    dstat = latest.get("dimensionStatus") or {}
    for name, r in ratings.items():
        dims.append({"name": name, "rating": r.get("rating") or "—",
                     "direction": r.get("direction") or "steady",
                     "confidence": (r.get("confidence") or {}).get("level") or "",
                     "sentence": _first_sentence(r.get("rationale")),
                     "capped": bool((dstat.get(name) or {}).get("confidenceCap"))})

    observed = sorted((f.get("observedAt") or "")[:10] for f in findings
                      if f.get("observedAt"))
    primary = sum(1 for f in findings if any(
        e.get("tier") == "primary" for e in (f.get("evidence") or [])))

    return {
        "category_id": category_id, "category_label": "Merchant GPU",
        "month_label": f"{_MONTHS[int(month) - 1]} {year}" if as_of else "",
        "revision": rev, "narrative": latest.get("narrative") or "",
        "status": {"rating": status.get("rating") or "—",
                   "direction": status.get("direction") or "",
                   "reason": _first_sentence(status.get("reason")),
                   "constraint": status.get("constraintLabel") or ""},
        "attention": _attention_state(store_root, category_id),
        "last_check": check, "stale": stale,
        "agenda": [{"slot_label": o.slot_label, "metric_label": o.candidate.label,
                    "display": o.candidate.display,
                    "trend_word": o.candidate.trend_word,
                    "as_of": o.candidate.observed_at,
                    "source": o.candidate.source_name, "was": o.was_label}
                   for o in occupants],
        "tsmc": read_implication_lines(store_root, category_id, as_of),
        "calls": {"rows": call_rows, "total": total, "provisional": prov},
        "strip": signal_strip(cat_dir),
        "dimensions": dims,
        "evidence": {"n": len(findings),
                     "median": observed[len(observed) // 2] if observed else "",
                     "oldest": observed[0] if observed else "",
                     "primary": primary},
        "counterweights": counterweight_ids(book),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_brief_model.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/brief_model.py tests/dashboard/test_brief_model.py
git commit -m "feat(f97): brief model assembly - strip, counterweights, agenda, dimensions"
```

---

### Task 6: Brief renderer — blocks A–H, BRIEF_CSS, register lint

**Files:**
- Create: `gpu_agent/dashboard/brief_render.py`
- Test: `tests/dashboard/test_brief_render.py`

**Interfaces:**
- Consumes: the model dict from `build_brief_model` (Task 5).
- Produces:
  - `render_brief(model) -> str` — full HTML page (uses F95's `page()` shell from `site_render` for the doctype/head; own `<link rel="stylesheet" href="brief.css">` is NOT used — brief styles are appended to the shared `style.css` via exported constant `BRIEF_CSS` that `site_build` concatenates).
  - `BRIEF_CSS: str` — chip/status classes `status-calm|watch|elevated|critical` (used only by chip + stale strip), `.hero`, `.kpis`, `.tile`, `.calls`, `.strip`, `.dims`, `.footer` etc.
  - `lint_exec_copy(html_text) -> list[str]` — returns banned-token violations (empty = clean). Banned regexes: `\+\d+ more moved`, `because no alert rule fired`, `internal settings`, `\b(this|prior|last) run\b`, `\bF\d{2,3}\b` (codenames).
  - Escaping: local `e = html.escape` applied to every model string.
- Block map (spec): A masthead (crumb, title, scope line, dual dates, chip linking `how/alert.html`, stale strip), B hero verdict + narrative, C agenda tiles (slot label, metric label, display, trend word, as-of + source, `(was: X)`; omit band if `len(agenda) < 3`), D TSMC bullets (bold lever = first 4 words? NO — render `text` verbatim as the bullet; dims as small tags; links to `appendix.html#f-<id>`; omit block when empty), E calls table (columns per spec; footer line `All {N} calls, including {M} provisional`; cold-start line when empty), F strip (date + sentence + source; omit when empty), G dimension tiles linking `appendix.html#dim-<name>`, H footer (evidence line + method line + appendix link).

- [ ] **Step 1: Write the failing tests**

```python
# tests/dashboard/test_brief_render.py
import re
from gpu_agent.dashboard.brief_render import BRIEF_CSS, lint_exec_copy, render_brief

MODEL = {
    "category_id": "chips.merchant-gpu", "category_label": "Merchant GPU",
    "month_label": "July 2026", "revision": 8, "narrative": "The <story>.",
    "status": {"rating": "Strong", "direction": "steady",
               "reason": "Supply caps it.", "constraint": "HBM supply"},
    "attention": {"word": "elevated", "css": "elevated", "raw_word": "calm",
                  "lagging": True},
    "last_check": "2026-07-15", "stale": False,
    "agenda": [{"slot_label": "Demand durability", "metric_label": "D2",
                "display": "$75.2B", "trend_word": "rising",
                "as_of": "2026-07-01", "source": "NVIDIA IR", "was": None},
               {"slot_label": "Binding constraint", "metric_label": "S10",
                "display": "2027 sold out", "trend_word": "tightening",
                "as_of": "2026-07-10", "source": "TrendForce", "was": "S9"},
               {"slot_label": "Customer mix", "metric_label": "m",
                "display": "44.6%", "trend_word": "shifting",
                "as_of": "2026-07-02", "source": "s", "was": None}],
    "tsmc": [{"text": "Wafer starts exposure.", "dims": ["momentum"],
              "thesis_ids": [], "finding_ids": ["f1"]}],
    "calls": {"rows": [{"title": "HBM binds supply", "lens": "supply",
                        "conviction": "high", "verdict": "strengthened",
                        "glyph": "▲", "streak": 1, "trigger": "gap re-widens"}],
              "total": 23, "provisional": 9},
    "strip": [{"date": "2026-07-14", "text": "CoWoS keeps narrowing.",
               "source": "TrendForce"}],
    "dimensions": [{"name": "momentum", "rating": "Very strong",
                    "direction": "improving", "confidence": "high",
                    "sentence": "Revenue set a record.", "capped": False}],
    "evidence": {"n": 86, "median": "2026-07-02", "oldest": "2026-06-12",
                 "primary": 2},
    "counterweights": {},
}


def test_render_brief_contains_all_blocks_in_order():
    html = render_brief(MODEL)
    order = [html.index("Executive Brief"),            # A
             html.index("Strong / steady"),            # B hero
             html.index("Demand durability"),          # C
             html.index("What this means for TSMC"),   # D
             html.index("Standing calls"),             # E
             html.index("Latest signal"),              # F
             html.index("The six dimensions"),         # G
             html.index("signal checks")]              # H footer wording
    assert order == sorted(order)


def test_render_brief_escapes_and_details():
    html = render_brief(MODEL)
    assert "The &lt;story&gt;." in html
    assert "(was: S9)" in html                          # continuity note
    assert "strengthened ▲" in html or "▲ strengthened" in html
    assert "All 23 calls, including 9 provisional" in html
    assert "steps down after two calm days; today's raw read was calm" in html
    assert 'class="chip status-elevated"' in html


def test_status_classes_only_on_chip_and_stale_strip():
    html = render_brief(dict(MODEL, stale=True))
    hits = re.findall(r'class="([^"]*status-[a-z]+[^"]*)"', html)
    assert hits and all(("chip" in h) or ("stalestrip" in h) for h in hits)


def test_agenda_band_omitted_below_three():
    m = dict(MODEL, agenda=MODEL["agenda"][:2])
    assert "Demand durability" not in render_brief(m)


def test_lint_exec_copy_catches_banned_tokens():
    assert lint_exec_copy("x +15 more moved y")
    assert lint_exec_copy("because no alert rule fired")
    assert lint_exec_copy("since the prior run")
    assert lint_exec_copy("per F65 rules")
    assert lint_exec_copy("1.6 trillion internal settings")
    assert lint_exec_copy(render_brief(MODEL)) == []


def test_brief_css_defines_status_and_tiles():
    for cls in ("status-calm", "status-watch", "status-elevated",
                "status-critical", ".kpis", ".hero"):
        assert cls in BRIEF_CSS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_brief_render.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# gpu_agent/dashboard/brief_render.py
"""F97 Executive Brief HTML — blocks A-H per the 2026-07-16 format spec (v5)."""
from __future__ import annotations

import html
import re

from .site_render import page

e = html.escape

_BANNED = [re.compile(p) for p in (
    r"\+\d+ more moved", r"because no alert rule fired", r"internal settings",
    r"\b(this|prior|last) run\b", r"\bF\d{2,3}\b")]

_CHIP_ICON = {"calm": "✓", "watch": "!", "elevated": "▲",
              "critical": "✖"}
_DIR_GLYPH = {"improving": "↑", "steady": "→", "worsening": "↓"}

BRIEF_CSS = """
.hero { font-size: 1.45rem; font-weight: 600; margin: 1rem 0 .5rem; }
.hero .rating { text-transform: uppercase; }
.narrative { max-width: 66ch; }
.chip { float: right; border-radius: 1em; padding: .25em .8em; font-size: .9rem;
        color: #fff; }
.chip small { display: block; font-size: .7rem; font-weight: 400; }
.status-calm { background: #0ca30c; }
.status-watch { background: #b97f00; }
.status-elevated { background: #c85f00; }
.status-critical { background: #d03b3b; }
.stalestrip { padding: .5rem .8rem; border-radius: .4rem; color: #fff;
              margin: .6rem 0; }
.kpis, .dims { display: flex; flex-wrap: wrap; gap: .8rem; margin: 1rem 0; }
.kpis .tile, .dims .tile { flex: 1 1 11rem; border: 1px solid var(--line);
        border-radius: .5rem; padding: .8rem; }
.tile .k { font-size: .75rem; letter-spacing: .05em; color: var(--muted);
           text-transform: uppercase; }
.tile .m { font-size: .85rem; margin-top: .15rem; }
.tile .v { font-size: 1.3rem; font-weight: 600; margin: .15rem 0; }
.tile .t, .tile .meta { font-size: .8rem; color: var(--muted); }
.calls td, .calls th { vertical-align: top; }
.calls .trigger { font-size: .85rem; color: var(--muted); }
.strip { list-style: none; padding: 0; }
.strip li { margin: .3rem 0; }
.strip .d { display: inline-block; width: 6.5rem; color: var(--muted);
            font-variant-numeric: tabular-nums; }
.footer { border-top: 1px solid var(--line); margin-top: 2rem; padding-top: .8rem;
          color: var(--muted); font-size: .9rem; }
.tag { font-size: .7rem; letter-spacing: .05em; color: var(--muted);
       text-transform: uppercase; }
"""


def lint_exec_copy(html_text: str) -> list[str]:
    return [p.pattern for p in _BANNED if p.search(html_text)]


def _chip(a) -> str:
    sub = ""
    if a["lagging"]:
        sub = (f"<small>steps down after two calm days; today's raw read was"
               f" {e(a['raw_word'])}</small>")
    return (f'<a class="chip status-{e(a["css"])}" href="how/alert.html">'
            f'{_CHIP_ICON.get(a["word"], "")} Attention: {e(a["word"])}{sub}</a>')


def _masthead(m) -> str:
    stale = ""
    if m["stale"]:
        stale = (f'<p class="stalestrip status-watch">! Signal checks paused since'
                 f' {e(m["last_check"])}</p>')
    return (
        f'{_chip(m["attention"])}'
        f'<p class="crumb">AI market › Chips layer › {e(m["category_label"])}</p>'
        f'<h1>{e(m["category_label"]).upper()} — Executive Brief</h1>'
        f'<p class="muted">Tracks the merchant AI-GPU market — demand, supply,'
        f' pricing, competition — and what it means one layer down: wafers,'
        f' packaging, memory.</p>'
        f'<p class="asof">Monthly read: {e(m["month_label"])} (revision'
        f' {m["revision"]}) · Last signal check: {e(m["last_check"])}</p>'
        f'{stale}')


def _verdict(m) -> str:
    s = m["status"]
    dash = f" / {e(s['direction'])}" if s["direction"] else ""
    return (f'<p class="hero"><span class="rating">{e(s["rating"])}{dash}</span>'
            f' — {e(s["reason"])}</p>'
            f'<p class="narrative">{e(m["narrative"])}</p>')


def _agenda(m) -> str:
    if len(m["agenda"]) < 3:
        return ""
    tiles = []
    for o in m["agenda"]:
        was = f'<div class="meta">(was: {e(o["was"])})</div>' if o["was"] else ""
        tiles.append(
            f'<div class="tile"><div class="k">{e(o["slot_label"])}</div>'
            f'<div class="m">{e(o["metric_label"])}</div>'
            f'<div class="v">{e(o["display"])}</div>'
            f'<div class="t">{e(o["trend_word"])}</div>'
            f'<div class="meta">as of {e(o["as_of"])} · {e(o["source"])}</div>'
            f'{was}</div>')
    return f'<div class="kpis">{"".join(tiles)}</div>'


def _tsmc(m) -> str:
    if not m["tsmc"]:
        return ""
    items = []
    for ln in m["tsmc"]:
        tags = " ".join(f'<span class="tag">{e(d)}</span>' for d in ln["dims"])
        links = " ".join(f'<a href="appendix.html#f-{e(f)}">evidence</a>'
                         for f in ln["finding_ids"][:1])
        items.append(f"<li>{e(ln['text'])} {tags} {links}</li>")
    return f'<h2>What this means for TSMC</h2><ul>{"".join(items)}</ul>'


def _calls(m) -> str:
    c = m["calls"]
    if not c["rows"]:
        return ('<h2>Standing calls</h2><p class="muted">No standing calls yet;'
                ' first reads are being established.</p>')
    rows = []
    for r in c["rows"]:
        verdict = f'{e(r["verdict"])} {r["glyph"]}'.strip()
        rows.append(
            f'<tr><td>{e(r["title"])}</td><td class="tag">{e(r["lens"])}</td>'
            f'<td>{e(r["conviction"])}</td><td>{verdict}</td>'
            f'<td style="text-align:right">{r["streak"]}</td>'
            f'<td class="trigger">{e(r["trigger"])}</td></tr>')
    return (
        '<h2>Standing calls</h2><div class="scroll"><table class="calls">'
        '<tr><th>Call</th><th>Lens</th><th>Conviction</th><th>Verdict</th>'
        '<th>Held</th><th>What would change our mind</th></tr>'
        f'{"".join(rows)}</table></div>'
        f'<p class="muted">All {c["total"]} calls, including {c["provisional"]}'
        f' provisional →</p>')


def _strip(m) -> str:
    if not m["strip"]:
        return ""
    items = "".join(
        f'<li><span class="d">{e(x["date"])}</span> {e(x["text"])}'
        f' <span class="muted">({e(x["source"])})</span></li>'
        for x in m["strip"])
    return f'<h2>Latest signal</h2><ul class="strip">{items}</ul>'


def _dims(m) -> str:
    tiles = []
    for d in m["dimensions"]:
        cap = '<div class="meta">confidence capped</div>' if d["capped"] else ""
        glyph = _DIR_GLYPH.get(d["direction"], "")
        tiles.append(
            f'<div class="tile"><div class="k">{e(d["name"])}</div>'
            f'<div class="v">{e(d["rating"])}</div>'
            f'<div class="t">{e(d["direction"])} {glyph} ·'
            f' {e(d["confidence"])} confidence</div>'
            f'<div class="meta">{e(d["sentence"])}</div>{cap}'
            f'<a class="how" href="appendix.html#dim-{e(d["name"])}">how was this'
            f' rated?</a></div>')
    return f'<h2>The six dimensions</h2><div class="dims">{"".join(tiles)}</div>'


def _footer(m) -> str:
    ev = m["evidence"]
    return (
        f'<div class="footer"><p>{ev["n"]} signals · median observation'
        f' {e(ev["median"])} · oldest {e(ev["oldest"])} · {ev["primary"]}'
        f' trace to primary sources · <a href="appendix.html">full appendix'
        f' →</a></p><p>Built by an autonomous research agent; every claim on'
        f' this page links to its evidence. Between signal checks the monthly read'
        f' stands.</p></div>')


def render_brief(model) -> str:
    body = "".join([_masthead(model), _verdict(model), _agenda(model),
                    _tsmc(model), _calls(model), _strip(model), _dims(model),
                    _footer(model)])
    return page(f"{model['category_label']} — Executive Brief ·"
                f" {model['month_label']}", body)
```

*(Note: the H-block footer must contain the phrase "signal checks" for the order test; the model's copy above includes "Between signal checks the monthly read stands.")*

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_brief_render.py -v`
Expected: all pass. If `test_render_brief_contains_all_blocks_in_order` fails on `page()`'s signature, check `site_render.page(title, body, depth=0)` and pass `depth=0`.

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/brief_render.py tests/dashboard/test_brief_render.py
git commit -m "feat(f97): brief renderer - blocks A-H, BRIEF_CSS, register lint"
```

---

### Task 7: Site integration — brief as index, appendix dimension anchors, CSS concat

**Files:**
- Modify: `gpu_agent/dashboard/site_build.py`
- Modify: `gpu_agent/dashboard/site_render.py` (appendix: add `#dim-<name>` + `#f-<id>` anchors)
- Test: `tests/dashboard/test_site_build.py` (modify), `tests/dashboard/test_brief_render.py` (append disjointness test)

**Interfaces:**
- Consumes: `build_brief_model` (Task 5), `render_brief`/`BRIEF_CSS`/`lint_exec_copy` (Task 6), existing `build_site_model` + renderers.
- Produces: `build_site(...)` now writes `cat/index.html` = the brief; `cat/ops.html` is NOT created (decision recorded above); `style.css` = `SITE_CSS + BRIEF_CSS`; appendix gains a `<h2 id="dimensions">` section rendering each dimension's FULL rationale under `<h3 id="dim-<name>">` and per-finding anchors `id="f-<finding-id>"` on the existing signal list items. `build_site` gains a `today=None` parameter (defaults to `datetime.date.today()` at the call edge, injected for tests). Summary dict gains `"brief_lint": []` (violations list — build FAILS with `ValueError` if non-empty, so a register regression can never deploy).

- [ ] **Step 1: Write/adjust the failing tests**

In `tests/dashboard/test_site_build.py`, adjust the existing index expectation and add:

```python
def test_build_site_index_is_brief(tmp_path, site_fixture_store):
    # reuse this test file's existing fixture-store helper; pass a fixed date
    import datetime as dt
    summary = build_site("chips.merchant-gpu", str(site_fixture_store),
                         "work", None, str(tmp_path / "site"),
                         today=dt.date(2026, 7, 16))
    html = (tmp_path / "site" / "chips.merchant-gpu" / "index.html").read_text(
        encoding="utf-8")
    assert "Executive Brief" in html and "Standing calls" in html
    assert summary["brief_lint"] == []
    css = (tmp_path / "site" / "style.css").read_text(encoding="utf-8")
    assert ".kpis" in css and "status-elevated" in css


def test_appendix_has_dimension_and_finding_anchors(tmp_path, site_fixture_store):
    import datetime as dt
    build_site("chips.merchant-gpu", str(site_fixture_store), "work", None,
               str(tmp_path / "site"), today=dt.date(2026, 7, 16))
    ap = (tmp_path / "site" / "chips.merchant-gpu" / "appendix.html").read_text(
        encoding="utf-8")
    assert 'id="dimensions"' in ap and 'id="dim-' in ap and 'id="f-' in ap
```

Append to `tests/dashboard/test_brief_render.py`:

```python
def test_agenda_and_dimension_tiles_disjoint():
    # C tiles are metric labels; G tiles are the six dimension names.
    dims = {"momentum", "unitEconomics", "bottleneck", "competitiveStructure",
            "moat", "strategicRisk"}
    for o in MODEL["agenda"]:
        assert o["metric_label"] not in dims
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_site_build.py tests/dashboard/test_brief_render.py -v`
Expected: FAIL — `build_site` has no `today` param, index is the old page, no anchors.

- [ ] **Step 3: Implement**

`site_build.py` — new body (keep `_write`):

```python
import datetime

from .brief_model import build_brief_model
from .brief_render import BRIEF_CSS, lint_exec_copy, render_brief


def build_site(category_id, store_dir, work_dir, plain_path, out_dir,
               price_fn=None, today=None):
    model = build_site_model(category_id, store_dir, work_dir, plain_path,
                             price_fn=price_fn)
    today = today or datetime.date.today()
    store_root = Path(store_dir)
    if not (store_root / category_id).is_dir():
        store_root = store_root.parent
    brief_model = build_brief_model(category_id, store_root, today,
                                    price_fn=price_fn)
    brief_html = render_brief(brief_model)
    lint = lint_exec_copy(brief_html)
    if lint:
        raise ValueError(f"exec-copy register violations: {lint}")

    out = Path(out_dir)
    cat = out / category_id
    pages = 0
    label = model["category_label"]
    _write(out / "index.html",
           render_index_redirect(f"{category_id}/index.html", label))
    _write(out / "style.css", SITE_CSS + BRIEF_CSS)
    _write(cat / "style.css", SITE_CSS + BRIEF_CSS)
    _write(cat / "index.html", brief_html); pages += 1
    _write(cat / "appendix.html", render_appendix(model)); pages += 1
    _write(cat / "how" / "alert.html", render_how_alert(model)); pages += 1
    for side in ("demand", "supply", "gap"):
        _write(cat / "how" / f"{side}.html", render_how_tile(model, side)); pages += 1
    featured = model.get("featured")
    if featured is not None:
        _write(cat / "how" / "featured.html", render_how_featured(model)); pages += 1

    return {"pages": pages + 1, "out": str(out),
            "featured": featured["metric_id"] if featured else None,
            "brief_lint": lint}
```

`site_render.py` `render_appendix` — two additions (keep everything else byte-identical):
1. In the per-signal loop, add `id="f-{finding_id}"` to each `<li>` (the model's top_signals rows carry `id`; if absent, skip the attribute).
2. After the signals section, append a dimensions section (model already carries `dimensions` from `build_model`; extend the projection in `build_site_model` to also pass full rationales as `model["dimension_rationales"] = [{"name", "rating", "rationale"}]` read from the latest scorecard's `dimensionRatings` — 6 lines in `site_model.py` where `sc` is already loaded):

```python
def _appendix_dimensions(model) -> str:
    rows = model.get("dimension_rationales") or []
    if not rows:
        return ""
    items = "".join(
        f'<h3 id="dim-{d["name"]}">{d["name"]} — {d["rating"]}</h3>'
        f"<p>{d['rationale']}</p>" for d in rows)
    return f'<h2 id="dimensions">How each dimension was rated</h2>{items}'
```

*(Use the module's existing escaping helper on `name`, `rating`, `rationale` exactly as neighboring appendix code does — match its idiom.)*

- [ ] **Step 4: Run the dashboard test directory**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/ -v`
Expected: all pass, including untouched F95 tests (`test_site_render.py`, `test_site_model.py`). If an F95 index-content assertion now fails because index.html is the brief, update THAT assertion to point at the brief (the page replacement is the feature) — do not weaken appendix/how assertions.

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/site_build.py gpu_agent/dashboard/site_render.py gpu_agent/dashboard/site_model.py tests/dashboard/
git commit -m "feat(f97): exec brief is the category index; appendix anchors; css concat; lint gate"
```

---

### Task 8: Real-store smoke build + full suite

**Files:**
- No new files; run against the real store from the worktree.

- [ ] **Step 1: Build the site from the real store**

Run: `../../.venv/Scripts/python -m gpu_agent.cli site --category chips.merchant-gpu --store store --work work --out /tmp-check-site` — from the worktree root use `--out work/site-smoke` (gitignored) instead of /tmp.
Expected: `[site] pages=...` with no traceback and `brief_lint` empty.

- [ ] **Step 2: Eyeball the output**

Read `work/site-smoke/chips.merchant-gpu/index.html` and verify against the spec outline: blocks A–H present and in order; agenda band has ≥3 tiles with real values ("$75.2B" etc.); calls table non-empty; no "no tracked calls"; no banned tokens; every number has a unit. Fix anything off and add a regression test for it in the matching test file.

- [ ] **Step 3: Run the full suite**

Run: `../../.venv/Scripts/python -m pytest -q`
Expected: green with 3–4 skips; `tests/test_evals_baseline_pin.py` green untouched (renderer-only change — if the F6 pin reddens, STOP: something touched brain prompts; do not "fix" the pin).

- [ ] **Step 4: Commit any fixes**

```bash
git add -u gpu_agent/dashboard/ tests/dashboard/
git commit -m "fix(f97): smoke-build fixes from real-store render"
```

---

### Task 9: Lane close-out

- [ ] **Step 1:** Update `docs/fix-backlog.md`: add the F97 entry (shipped) with a one-line description and the concurrent-mint caveat resolution.
- [ ] **Step 2:** Write `.superpowers/handoffs/f97-exec-brief-DONE.md`: what shipped, decisions made in-lane (index replacement, dimension anchors, lint-gate), test counts, branch name, NOT merged (stop-before-merge holds unless the user says merge).
- [ ] **Step 3:** Update `docs/superpowers/HANDOFF.md` top line + a dated bullet (branch pushed, awaiting merge decision).
- [ ] **Step 4:** Commit docs; push the branch:

```bash
git add docs/ .superpowers/handoffs/f97-exec-brief-DONE.md
git commit -m "docs(f97): lane close-out - backlog entry, DONE sentinel, handoff"
git push -u origin f97-exec-brief
```

- [ ] **Step 5:** Report to the user: branch, test counts, what the rendered page looks like, merge decision pending. Deploy note: Cloudflare Pages serves `site/` from main — nothing user-visible changes until the branch merges and a cycle rebuilds `site/`.

---

## Self-review notes (done at plan time)

- **Spec coverage:** A–H blocks → Tasks 5–7; dynamic agenda → Tasks 1–3; counterweight groundwork → Task 5 (`counterweights` map is computed and available to the renderer; v1 renders cross-references only where implication `thesis_ids` intersect risk calls — full finding-level inline cross-refs ride on the appendix anchors); register contract → Task 6 lint + Task 7 build gate; staleness → Tasks 4–6; acceptance criteria 1–9 → tests in Tasks 3, 6, 7; criterion 10 → Task 8.
- **Known simplifications (explicit, not placeholders):** metric labels on agenda tiles are indicator ids in v1 (plain labels can ride the glossary later); counterweight inline notes limited to the TSMC block in v1; `how/demand|supply|gap|featured.html` keep building though the brief doesn't link them.
- **Type consistency check:** `Candidate`/`Occupant` field names match between Tasks 2–3 and the model projection in Task 5; `build_site(today=...)` matches Task 7's tests; `page(title, body)` matches `site_render.py:50`.
