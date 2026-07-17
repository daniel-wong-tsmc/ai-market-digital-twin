"""F97 agenda band — five standing executive questions, answered dynamically.

Pure projection: candidates come from measured findings (value: {number, unit})
and series readings; selection is deterministic (freshness x magnitude x
evidence grade, stickiness vs the prior revision's pick)."""
from __future__ import annotations

import json
from dataclasses import dataclass
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
    if not isinstance(newest.get("value"), (int, float)):
        return None
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
