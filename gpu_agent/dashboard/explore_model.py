"""F101 Phase C / Task 2: Explore layer data assembly -- pure reads only.

Every function here takes a `store_root: Path` (or, for `verdict_timeline`,
a `cat_dir: Path`) and returns plain dict/list data. No writes, no
wall-clock reads, no network. These are the shared data-assembly primitives
every later Explore-layer page renderer builds on top of.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from gpu_agent.dashboard.gap_chart import (_MONTHLY, _monthly_records,
                                            build_gap_data)
from gpu_agent.dashboard.render import esc
from gpu_agent.dashboard.story_model import _gap_word, _HEADLINES
from gpu_agent.narrator.store import StoryStore
from gpu_agent.wiki.page import WikiFormatError, load_page

# Entity name/ticker aliasing, folding e.g. "NVDA" findings onto the same
# entity slug as "nvidia" wiki pages.
_ALIAS = {"nvda": "nvidia", "intc": "intel"}


def load_findings(store_root: Path) -> list[dict]:
    """Every store/findings/*.json, skipping unparseable files, sorted
    newest-first by observedAt (falling back to asOf). Each returned dict
    gains an `entitySlug` key derived from its `entity` field via `_ALIAS`
    (casefolded)."""
    store_root = Path(store_root)
    try:
        paths = sorted((store_root / "findings").glob("*.json"))
    except OSError:
        paths = []
    out = []
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        entity = str(data.get("entity") or "").casefold()
        data["entitySlug"] = _ALIAS.get(entity, entity)
        out.append(data)
    out.sort(key=lambda f: f.get("observedAt") or f.get("asOf") or "", reverse=True)
    return out


def split_by_side(findings: list[dict]) -> dict[str, list[dict]]:
    """Bucket findings by their `side` field into demand/supply/other; a
    missing or unrecognized side falls into `other`."""
    out: dict[str, list[dict]] = {"demand": [], "supply": [], "other": []}
    for f in findings:
        side = f.get("side")
        bucket = side if side in ("demand", "supply") else "other"
        out[bucket].append(f)
    return out


def entity_roles(findings: list[dict]) -> dict[str, str]:
    """Per entity slug, a one-line role description driven by which side
    (demand/supply/other) most of its findings fall on."""
    counts: dict[str, dict[str, int]] = {}
    neg_supply: dict[str, bool] = {}
    for f in findings:
        slug = f.get("entitySlug")
        if not slug:
            continue
        side = f.get("side")
        bucket = side if side in ("demand", "supply") else "other"
        c = counts.setdefault(slug, {"demand": 0, "supply": 0, "other": 0})
        c[bucket] += 1
        if bucket == "supply" and (f.get("polaritySupply") or 0) < 0:
            neg_supply[slug] = True

    roles: dict[str, str] = {}
    for slug, c in counts.items():
        top = max(c.values())
        leaders = [side for side, n in c.items() if n == top]
        if len(leaders) > 1:
            roles[slug] = "a market participant"
            continue
        majority = leaders[0]
        if majority == "supply":
            roles[slug] = ("where the supply bottleneck lives"
                            if neg_supply.get(slug) else "a supply-side player")
        elif majority == "demand":
            roles[slug] = "a demand driver"
        else:
            roles[slug] = "a market participant"
    return roles


def load_entities(store_root: Path) -> list[dict]:
    """Every store/wiki/entity/*.md, parsed via the wiki module's own
    front-matter loader (never re-implemented here). Skips files that fail
    to parse."""
    store_root = Path(store_root)
    try:
        paths = sorted((store_root / "wiki" / "entity").glob("*.md"))
    except OSError:
        paths = []
    out = []
    for p in paths:
        try:
            page, body = load_page(p.read_text(encoding="utf-8"))
        except (OSError, WikiFormatError):
            continue
        out.append({"slug": p.stem, "title": page.title,
                    "front": page.model_dump(), "body_md": body})
    return out


def series_groups() -> list[dict]:
    """The fixed KPI-framework grouping used to lay out the Explore
    series page."""
    return [
        {"key": "gap-price", "label": "The price of the gap",
         "indicatorIds": ["gpuRentalOnDemand", "gpuRental1yr", "gpuSpotPrice"]},
        {"key": "demand", "label": "Demand gauges",
         "indicatorIds": ["hyperscalerCapexRevision", "tokenEconomics",
                          "marginalBuyerFinancing"]},
        {"key": "supply", "label": "Supply arriving",
         "indicatorIds": ["odmMonthlyAiRevenue", "pkgCapacityOrderSpread"]},
        {"key": "relief", "label": "Relief ahead",
         "indicatorIds": ["hbmSupplyCapex"]},
    ]


SERIES_MEANING = {
    "gpuRentalOnDemand": "falls when supply catches up with demand",
    "gpuRental1yr": "the going rate for locking in a GPU for a year",
    "gpuSpotPrice": "what one GPU costs to buy outright, right now",
    "hyperscalerCapexRevision": "whether big buyers raised or cut spending plans",
    "tokenEconomics": "what it costs to run a unit of AI work",
    "marginalBuyerFinancing": "how easy it is for smaller buyers to get financing",
    "odmMonthlyAiRevenue": "how much AI server capacity is actually shipping",
    "pkgCapacityOrderSpread": "the gap between packaging orders and open capacity",
    "hbmSupplyCapex": "memory factory spending that eases the shortage over time",
}

ENTITY_SERIES = {"tsmc": ["pkgCapacityOrderSpread"]}


def _monthly_best_files(cat_dir: Path) -> dict[str, Path]:
    """The same "highest revision wins" file selection `_monthly_records`
    uses, but returning the winning path per month key instead of its
    parsed demand/supply contribution -- so callers that need the rest of
    that month's snapshot (categoryStatus, dimensionRatings, ...) can read
    the exact same file without re-implementing the selection rule."""
    best: dict[str, tuple[int, Path]] = {}
    for p in Path(cat_dir).glob("*.json"):
        m = _MONTHLY.match(p.name)
        if not m:
            continue
        key, rev = m.group(1), int(m.group(2))
        if key not in best or rev > best[key][0]:
            best[key] = (rev, p)
    return {k: v[1] for k, v in best.items()}


def verdict_timeline(cat_dir: Path) -> dict:
    """The full demand/supply gap chart (over ALL months) plus a per-month
    verdict: headline (via the Phase A `_HEADLINES` gap-word logic, computed
    month-over-month), and that month's rating/direction/constraint/dims
    pulled from its own committed snapshot."""
    cat_dir = Path(cat_dir)
    gap = build_gap_data(cat_dir, limit=120)
    recs = _monthly_records(cat_dir)
    files = _monthly_best_files(cat_dir)

    months = []
    for r in recs:
        # Same-month gap-word derivation, reused verbatim from story_model
        # (build_gap_data's gap level is a running sum, so the change in gap
        # from one month to the next collapses to this same-month scaled
        # quantity -- see _gap_word's own docstring).
        word = _gap_word(r["dmi"], r["smi"])
        headline = _HEADLINES.get(word, "")
        label = dt.date(int(r["key"][:4]), int(r["key"][5:7]), 1).strftime("%B %Y")

        raw: dict = {}
        p = files.get(r["key"])
        if p is not None:
            try:
                loaded = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                loaded = None
            if isinstance(loaded, dict):
                raw = loaded
        status = raw.get("categoryStatus") or {}
        dims_raw = raw.get("dimensionRatings") or {}
        dims = {name: {"rating": d.get("rating"), "direction": d.get("direction")}
                for name, d in dims_raw.items() if isinstance(d, dict)}

        months.append({"key": r["key"], "label": label, "headline": headline,
                       "rating": status.get("rating") or "",
                       "direction": status.get("direction") or "",
                       "constraint": status.get("constraintLabel") or "",
                       "dims": dims})

    return {"gap": gap, "months": months}


def story_index(store_root: Path, category_id: str) -> list[dict]:
    """Every story artifact for the category, newest first, via
    `StoryStore.recent_headlines` (the "before" date is set far in the
    future and the limit high so nothing already written is excluded)."""
    return StoryStore(store_root).recent_headlines(
        category_id, before="9999-12-31", limit=10_000)


_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\((https://[^)\s]+)\)")


def _inline(text: str) -> str:
    text = _LINK.sub(r'<a href="\2">\1</a>', text)
    text = _BOLD.sub(r"<b>\1</b>", text)
    return text


def markdown_to_html(md: str) -> str:
    """A minimal, safe markdown subset: HTML is escaped FIRST (so no raw
    HTML -- e.g. a stray `<script>` -- ever survives), then `## `/`### `
    headings, `**bold**`, `- ` list blocks, blank-line paragraph breaks, and
    `[text](https://url)` links (https only) are applied on top. Nothing
    else is supported."""
    text = esc(md or "")
    blocks = re.split(r"\n\s*\n", text.strip())
    out = []
    for block in blocks:
        block = block.strip("\n")
        if not block:
            continue
        lines = block.split("\n")
        if all(ln.startswith("- ") for ln in lines):
            items = "".join(f"<li>{_inline(ln[2:])}</li>" for ln in lines)
            out.append(f"<ul>{items}</ul>")
        elif block.startswith("### "):
            out.append(f"<h3>{_inline(block[4:])}</h3>")
        elif block.startswith("## "):
            out.append(f"<h2>{_inline(block[3:])}</h2>")
        else:
            out.append(f"<p>{_inline(' '.join(lines))}</p>")
    return "".join(out)
