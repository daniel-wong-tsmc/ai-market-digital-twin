"""F95 featured metric — library loader + deterministic selector (spec §4).

Pure projection: no LLM, no wall-clock, replayable. The library is DATA
(registry/featured-metrics.json); selection is first-match-wins:
(1) alert-rule tag hit -> (2) biggest normalized move -> (3) static priority.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

FEATURED_REGISTRY_PATH = "registry/featured-metrics.json"


@dataclass(frozen=True)
class MetricReading:
    metric_id: str
    label: str
    plain_label: str
    unit: str
    value: float
    prior: float | None          # None = no prior cycle value available
    scale: float                 # library denominator: a move this big is headline-worthy
    static_priority: int         # lower = shown first on fallback
    alert_rule_tags: tuple
    how_to_read: str
    honesty_note: str | None
    display: str                 # preformatted value, e.g. "$2.31/GPU-hr" or "+0.76"


@dataclass(frozen=True)
class Selection:
    reading: MetricReading
    reason_code: str             # "alert-rule" | "biggest-move" | "priority"
    reason_text: str             # plain sentence rendered on the page (spec §4)


def load_library(path: str = FEATURED_REGISTRY_PATH) -> list[dict]:
    with open(Path(path), encoding="utf-8") as fh:
        return json.load(fh)["metrics"]


def normalized_change(reading: MetricReading) -> float | None:
    if reading.prior is None:
        return None
    return abs(reading.value - reading.prior) / reading.scale


def select_featured(readings: list[MetricReading], triggers: list[str]) -> Selection | None:
    if not readings:
        return None
    trig = set(triggers or [])
    tagged = [r for r in readings if set(r.alert_rule_tags) & trig]
    if tagged:
        r = min(tagged, key=lambda r: r.static_priority)
        return Selection(r, "alert-rule",
                         "Shown because it tracks what set off today's alert.")
    moved = [(normalized_change(r), r) for r in readings]
    moved = [(c, r) for c, r in moved if c is not None and c > 0]
    if moved:
        _, r = max(moved, key=lambda cr: (cr[0], -cr[1].static_priority))
        return Selection(r, "biggest-move",
                         "Shown because it moved the most since the last run.")
    r = min(readings, key=lambda r: r.static_priority)
    return Selection(r, "priority",
                     "Shown as the standing headline metric; nothing moved more.")


def _default_price_fn(as_of: str) -> dict:
    """Real price feed; scrape_data is gitignored so absence is normal — degrade to {}."""
    from gpu_agent import pricefeed
    try:
        return pricefeed.headline_prices(as_of)
    except (FileNotFoundError, OSError, ValueError):
        return {}


def _reading(entry: dict, value: float, prior: float | None, display: str) -> MetricReading:
    return MetricReading(
        metric_id=entry["id"], label=entry["label"], plain_label=entry["plainLabel"],
        unit=entry["unit"], value=value, prior=prior, scale=float(entry["scale"]),
        static_priority=int(entry["staticPriority"]),
        alert_rule_tags=tuple(entry.get("alertRuleTags") or []),
        how_to_read=entry["howToRead"], honesty_note=entry.get("honestyNote"),
        display=display)


def assemble_readings(library, latest, prev, as_of, price_fn=None):
    """One MetricReading per library entry whose source has data; honest skips otherwise."""
    from gpu_agent.pricefeed import lookback_label
    price_fn = price_fn or _default_price_fn
    cur_prices = None   # fetched lazily, once
    out = []
    for entry in library:
        src = entry.get("source") or {}
        kind = src.get("kind")
        if kind == "index":
            field = src.get("field")
            if field not in ("dmi", "smi", "sdgi"):
                continue
            value = float(latest[field])
            prior = float(prev[field]) if prev else None
            out.append(_reading(entry, value, prior, f"{value:+.2f}"))
        elif kind == "pricefeed":
            if cur_prices is None:
                cur_prices = price_fn(as_of)
            model = src.get("model")
            if not cur_prices or model not in cur_prices:
                continue
            value = float(cur_prices[model])
            prior_prices = price_fn(lookback_label(as_of, 30))
            prior = float(prior_prices[model]) if model in (prior_prices or {}) else None
            out.append(_reading(entry, value, prior, f"${value:.2f}/GPU-hr"))
        # unknown kinds: forward-compatible skip (spec §8)
    return out
