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

# F98: unit-string aliases (registry/series data may spell units in ways that
# don't match the formatter table keys above) applied at the top of
# format_value, before any lookup.
_UNIT_ALIASES = {"USD billion": "USD_B", "USD_billion": "USD_B", "percent": "pct"}

# F98: units whose "value" is really a coded direction/state — render the word,
# never the bare number.
WORD_UNITS = {
    "credit_condition_index": {1: "loosening", 0: "neutral", -1: "tightening"},
    "revision_direction": {1: "raised", 0: "held", -1: "cut"},
}

_UNIT_FMT.update({
    "USD": lambda n: f"${n/1e6:.1f}M" if abs(n) >= 1e6 else f"${n:,.0f}",
    "flops_per_USD": lambda n: f"{n/1e9:,.0f} GFLOPS/$",
})


def load_slots(path: str = AGENDA_REGISTRY_PATH) -> list[dict]:
    with open(Path(path), encoding="utf-8") as fh:
        return json.load(fh)["slots"]


def format_value(number: float, unit: str) -> str:
    unit = _UNIT_ALIASES.get(unit, unit)
    words = WORD_UNITS.get(unit)
    if words is not None:
        w = words.get(int(round(number)))
        if w is not None:
            return w
        return f"{number:g} {unit}"
    fmt = _UNIT_FMT.get(unit)
    if fmt is not None:
        return fmt(number)
    return f"{number:g} {unit}"   # unknown unit: value + unit verbatim, never bare


_TREND_WORDS = {"rising": "rising", "falling": "falling", "stable": "steady",
                "steady": "steady", "mixed": "mixed"}

# F98 review fix: a percentage delta ("+13% vs Apr") is only meaningful for
# money/price units. Applying it to an already-percentage unit (e.g. market
# share 40% -> 45%) yields a confusing "percent-of-a-percent" figure, and it's
# meaningless for raw counts. Restrict to money + $-denominated efficiency —
# the end-market-economics price/efficiency units per spec §4.
_DELTA_PCT_UNITS = {"USD", "USD_B", "USD_per_hr", "flops_per_USD"}


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
    delta_line: str = ""   # F98: change vs a reading ~90 days back, e.g. "-12% vs Apr"


def _finding_candidate(f: dict, label: str | None = None) -> Candidate | None:
    v = f.get("value")
    if f.get("kind") != "measured" or not isinstance(v, dict):
        return None
    ev = f.get("evidence") or []
    tier = "primary" if any(e.get("tier") == "primary" for e in ev) else "secondary"
    src = next((e.get("source") for e in ev if e.get("source")), "")
    return Candidate(
        indicator_id=f["indicatorId"], label=label or f["indicatorId"],
        display=format_value(float(v["number"]), str(v.get("unit") or "")),
        trend_word=_TREND_WORDS.get((f.get("trend") or "").lower(), ""),
        observed_at=f.get("observedAt") or f.get("asOf") or "",
        tier=tier, source_name=src or "",
        magnitude=int(f.get("magnitude") or 0),
        statement=f.get("statement") or "")


_MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
               "Sep", "Oct", "Nov", "Dec"]


def _days_key(row):
    s = row.get("publishedAt") or (row.get("period", "") + "-15")
    try:
        y, m, d = (int(x) for x in s[:10].split("-"))
        return _dt.date(y, m, d)
    except (ValueError, IndexError):
        return None


def _delta_line(rows: list[dict]) -> str:
    if len(rows) < 2:
        return ""
    newest = rows[-1]
    unit = _UNIT_ALIASES.get(str(newest.get("unit") or ""), newest.get("unit"))
    if unit in WORD_UNITS or not isinstance(newest.get("value"), (int, float)):
        return ""
    if unit not in _DELTA_PCT_UNITS:
        return ""
    nd = _days_key(newest)
    base = None
    for r in rows[-2::-1]:
        if isinstance(r.get("value"), (int, float)) and _days_key(r) is not None \
                and nd is not None and (nd - _days_key(r)).days >= 80:
            base = r
            break
    if base is None or not base["value"]:
        return ""
    pct = (newest["value"] - base["value"]) / abs(base["value"]) * 100
    month = _MONTH_ABBR[int((base.get("period") or "0000-01")[5:7])]
    return f"{pct:+.0f}% vs {month}"


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
        indicator_id=indicator_id, label=newest.get("label") or indicator_id,
        display=format_value(float(newest["value"]), str(newest.get("unit") or "")),
        trend_word=trend,
        observed_at=newest.get("publishedAt") or newest.get("period") or "",
        tier="secondary",
        source_name=(newest.get("source") or {}).get("title", ""),
        magnitude=0, statement=newest.get("note") or "",
        delta_line=_delta_line(rows))


def candidates_for_slot(slot, findings, series_rows, labels=None) -> list[Candidate]:
    labels = labels or {}
    wanted = set(slot["indicators"])
    out = []
    for f in findings:
        ind = f.get("indicatorId")
        if ind in wanted:
            c = _finding_candidate(f, labels.get(ind, ind))
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


def _pick(slot, findings, series_rows, today, sticky, labels=None) -> Candidate | None:
    cands = candidates_for_slot(slot, findings, series_rows, labels)
    if not cands:
        return None
    return max(cands, key=lambda c: (score(c, today, sticky), c.observed_at,
                                     c.indicator_id))


def select_occupants(slots, findings, series_rows, prior_findings, today, labels=None):
    out = []
    for slot in slots:
        prior = _pick(slot, prior_findings, {}, today, None, labels)
        sticky = prior.indicator_id if prior is not None else None
        cur = _pick(slot, findings, series_rows, today, sticky, labels)
        if cur is None:
            continue
        was = None
        if prior is not None and prior.indicator_id != cur.indicator_id:
            was = prior.label
        out.append(Occupant(slot_id=slot["id"], slot_label=slot["label"],
                            candidate=cur, was_label=was))
    return out
