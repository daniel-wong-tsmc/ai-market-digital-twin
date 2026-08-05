import json
from pathlib import Path
from .glossary import term_swap

STATE_OF_MARKET_KEY = "stateOfMarket"

# F110 Task 6: plain-English row labels for the six scorecard dimensions
# (gpu_agent/schema/scorecard.py's DIMENSIONS list), used by the dashboard.json
# exporter. This file is copy, not frozen core, so this mapping is the place to
# extend when a new dimension key needs a reader-facing name -- never invent
# an ad hoc label at the export call site. Wording matches the approved mock
# (docs/superpowers/specs/assets/2026-08-05-dashboard-mock.html) verbatim.
DIMENSION_PLAIN_NAMES = {
    "bottleneck": "What is holding shipments back",
    "momentum": "How hard buyers are buying",
    "competitiveStructure": "Whether buyers have a second choice",
    "moat": "How safe NVIDIA's lead looks",
    "unitEconomics": "How profitable the sellers are",
    "strategicRisk": "What could go wrong",
}


def dimension_plain_name(name):
    """Plain-English label for a dimension key. Falls back to the raw key
    (visibly wrong, never silently blank) so a missing mapping is easy to spot
    the moment a new dimension is added upstream."""
    return DIMENSION_PLAIN_NAMES.get(name, name)


def dimension_key(name):
    return f"dimension.{name}.rationale"


def claim_key(slug):
    return f"claim.{slug}.statement"


def finding_key(fid):
    return f"finding.{fid}.statement"


def load_plain_language(path):
    if not path or not Path(path).exists():
        return {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return {}
    return data.get("rewrites", {}) or {}


def _norm(s):
    return " ".join((s or "").split())


def resolve_text(key, original, plain_map, glossary):
    entry = plain_map.get(key)
    if entry and _norm(entry.get("original")) == _norm(original) and entry.get("plain"):
        return entry["plain"], False
    return term_swap(original, glossary), True
