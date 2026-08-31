"""F110 Task 3: curated chart-series registry.

A "chart series" declares one data series that is allowed to appear as a
small supporting chart next to a dashboard bullet. The registry is the
only source of truth for two things a small chart cannot get wrong:

- where the numbers come from (``sourceName`` / ``sourceUrl``), and
- whether the series is a HARD FACT (a published figure) or an ESTIMATE.

A small chart reads as fact to a reader, so an ``estimate`` series must
never be drawn as one. ``ChartSeries.chartable`` encodes that gate as a
derived property -- it is never stored, so it can never drift out of
sync with ``quality``.

This module does no fetching and touches no network; it only loads and
validates the registry JSON file (see ``registry/chart-series.json``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REGISTRY_PATH = "registry/chart-series.json"

_CADENCES = {"quarterly", "monthly"}
_QUALITIES = {"hard-fact", "estimate"}
# Must stay inside web/schema/dashboard.schema.json's chart.form enum.
_FORMS = {"columns", "bars", "line"}

_REQUIRED_STRING_FIELDS = ("id", "name", "sourceName", "sourceUrl", "unit")


@dataclass(frozen=True)
class ChartSeries:
    id: str
    name: str
    sourceName: str
    sourceUrl: str
    cadence: str            # 'quarterly' | 'monthly'
    quality: str            # 'hard-fact' | 'estimate'
    topicTags: tuple[str, ...]   # matched against finding indicatorIds + entity
    form: str               # 'columns' | 'bars' | 'line'
    unit: str
    fetcher: str | None     # key into FETCHERS; None = maintained elsewhere
    # F131: which company's earnings calendar schedules this series. Matched
    # against a manifest's `earningsDates` keys ('amd', 'nvidia'). REQUIRED on
    # a quarterly series -- see _validate_entry for why that is enforced at
    # load time rather than defaulted. A monthly series is never scheduled off
    # an earnings date, so it simply has no key.
    earningsKey: str | None = None

    @property
    def chartable(self) -> bool:
        """A small chart may only be drawn from a hard fact, never an
        estimate -- a small chart reads as fact to the reader."""
        return self.quality == "hard-fact"


def _fail(entry_id: str, message: str) -> None:
    raise ValueError(f"registry/chart-series.json entry {entry_id!r}: {message}")


def _validate_entry(entry: dict) -> ChartSeries:
    entry_id = entry.get("id", "<missing id>")

    for field in _REQUIRED_STRING_FIELDS:
        if not isinstance(entry.get(field), str) or not entry[field]:
            _fail(entry_id, f"missing or non-string field {field!r}")

    cadence = entry.get("cadence")
    if cadence not in _CADENCES:
        _fail(entry_id, f"cadence must be one of {sorted(_CADENCES)}, got {cadence!r}")

    quality = entry.get("quality")
    if quality not in _QUALITIES:
        _fail(entry_id, f"quality must be one of {sorted(_QUALITIES)}, got {quality!r}")

    form = entry.get("form")
    if form not in _FORMS:
        _fail(entry_id, f"form must be one of {sorted(_FORMS)}, got {form!r}")

    topic_tags = entry.get("topicTags")
    if not isinstance(topic_tags, list) or not topic_tags \
            or not all(isinstance(t, str) and t for t in topic_tags):
        _fail(entry_id, "topicTags must be a non-empty list of non-empty strings")

    fetcher = entry.get("fetcher")
    if fetcher is not None and not isinstance(fetcher, str):
        _fail(entry_id, "fetcher must be a string or null")

    # F131: a quarterly series is scheduled off ONE company's print date, and
    # `earningsKey` names that company. It is required rather than defaulted
    # because a quarterly series with no key would match no print date at all
    # and go silently never-due -- exactly the failure F131 was filed for.
    # Failing at load time makes that impossible to ship unnoticed.
    earnings_key = entry.get("earningsKey")
    if earnings_key is not None and (not isinstance(earnings_key, str) or not earnings_key):
        _fail(entry_id, "earningsKey must be a non-empty string or null")
    if cadence == "quarterly" and earnings_key is None:
        _fail(entry_id, "earningsKey is required for a quarterly series (it names "
                        "the company whose earnings calendar schedules it)")

    return ChartSeries(
        id=entry["id"],
        name=entry["name"],
        sourceName=entry["sourceName"],
        sourceUrl=entry["sourceUrl"],
        cadence=cadence,
        quality=quality,
        topicTags=tuple(topic_tags),
        form=form,
        unit=entry["unit"],
        fetcher=fetcher,
        earningsKey=earnings_key,
    )


def load_chart_series(path: str = DEFAULT_REGISTRY_PATH) -> dict[str, ChartSeries]:
    """Load and validate registry/chart-series.json into id -> ChartSeries.

    Raises ValueError on any malformed entry (missing/bad field, unknown
    cadence/quality/form, duplicate id) rather than silently dropping it --
    a chart backed by a broken registry entry is worse than no chart."""
    with open(Path(path), encoding="utf-8") as fh:
        raw = json.load(fh)

    entries = raw.get("series")
    if not isinstance(entries, list):
        raise ValueError(f"{path}: expected top-level 'series' list")

    out: dict[str, ChartSeries] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: each series entry must be an object")
        series = _validate_entry(entry)
        if series.id in out:
            _fail(series.id, "duplicate id in registry")
        out[series.id] = series
    return out
