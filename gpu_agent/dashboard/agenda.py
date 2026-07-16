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
