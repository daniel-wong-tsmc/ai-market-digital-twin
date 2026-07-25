"""Evidence freshness decay engine (F103).

Defines:
  FreshnessConfig    — validated registry/freshness.json model
  load_freshness()   — trust-boundary loader (raises FreshnessLoadError)
  classify()         — url/indicator -> "filings" | "structural" | "news"
  parse_date()        — lenient date-string parser
  weight()           — half-life decay weight for a piece of evidence

The complaint that started this feature: a late-May earnings filing was still
being weighted as if it were fresh in late July. Filings decay fast (5-day
half life), news even faster (3 days), and structural indicators (lead times,
capex) decay slowly (45 days) because they change on a much longer cadence.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, model_validator

AGING_THRESHOLD = 0.25
_DEFAULT_AGE_DAYS = 30

_REQUIRED_HALF_LIFE_KINDS = {"news", "filings", "structural"}


class FreshnessConfig(BaseModel, extra="forbid"):
    schemaVersion: Literal[1]
    halfLivesDays: dict[str, float]
    filingsDomains: list[str]
    structuralIndicators: list[str]

    @model_validator(mode="after")
    def _require_exact_half_life_kinds(self) -> "FreshnessConfig":
        got = set(self.halfLivesDays.keys())
        if got != _REQUIRED_HALF_LIFE_KINDS:
            raise ValueError(
                f"halfLivesDays must have exactly the keys "
                f"{sorted(_REQUIRED_HALF_LIFE_KINDS)}, got {sorted(got)}"
            )
        return self


class FreshnessLoadError(Exception):
    pass


def load_freshness(path: str | Path = "registry/freshness.json") -> FreshnessConfig:
    """Load and validate the freshness registry from a JSON file.

    Raises FreshnessLoadError with a plain-language message on:
      - file not found
      - invalid JSON
      - schema validation failure
    """
    p = Path(path)
    if not p.exists():
        raise FreshnessLoadError(f"Freshness registry file not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FreshnessLoadError(f"Freshness registry at {p} contains invalid JSON: {exc}") from exc
    try:
        return FreshnessConfig(**raw)
    except Exception as exc:
        raise FreshnessLoadError(f"Freshness registry at {p} failed schema validation: {exc}") from exc


def classify(url: str, indicator_id: str | None, cfg: FreshnessConfig) -> str:
    """Classify a piece of evidence into a decay bucket.

    Precedence: a filingsDomain substring match on the URL's netloc+path wins
    ("filings"); otherwise an indicator_id listed in structuralIndicators wins
    ("structural"); otherwise it's plain "news".
    """
    parsed = urlparse(url)
    haystack = parsed.netloc + parsed.path
    if any(domain in haystack for domain in cfg.filingsDomains):
        return "filings"
    if indicator_id is not None and indicator_id in cfg.structuralIndicators:
        return "structural"
    return "news"


def parse_date(raw: str | None) -> dt.date | None:
    """Parse 'YYYY-MM-DD' or 'YYYY-MM' (day defaults to 1). Anything else -> None."""
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        pass
    try:
        year, month = raw.split("-")
        return dt.date(int(year), int(month), 1)
    except (ValueError, TypeError):
        return None


def _round4(x: float) -> float:
    """Round to 4 significant figures (not 4 decimal places) — weights range
    from 1.0 down to fractions of a permille, and decimal-place rounding
    would zero out the small-but-meaningful tail values.
    """
    if x == 0:
        return 0.0
    digits = 3 - int(math.floor(math.log10(abs(x))))
    return round(x, digits)


def weight(published: str | None, today: dt.date, kind: str, cfg: FreshnessConfig) -> float:
    """Half-life decay weight in [0, 1] for a piece of evidence.

    Missing/unparseable dates are treated as _DEFAULT_AGE_DAYS old. Future
    dates clamp to age 0 (full weight). Result is rounded to 4 significant
    figures and clamped to [0, 1].
    """
    published_date = parse_date(published)
    if published_date is None:
        age_days = _DEFAULT_AGE_DAYS
    else:
        age_days = max(0, (today - published_date).days)

    half_life = cfg.halfLivesDays[kind]
    raw_weight = 0.5 ** (age_days / half_life)
    return min(1.0, max(0.0, _round4(raw_weight)))
