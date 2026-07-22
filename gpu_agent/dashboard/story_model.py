"""F101 Phase A: assemble the narrative-page model from committed store data.

The returned dict's shape doubles as the Phase-B narrator artifact
contract: Phase B replaces this assembler with a reader of
store/<cat>/story/<date>.json, and the renderer must not notice.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from gpu_agent.dashboard.agenda import read_series
from gpu_agent.dashboard.brief_model import (first_n_sentences,
                                             latest_monthly,
                                             read_implication_lines)
from gpu_agent.dashboard.gap_chart import build_gap_data
from gpu_agent.dashboard.glossary import load_glossary, term_swap

_SERIES_IDS = ["gpuRentalOnDemand", "hyperscalerCapexRevision",
               "odmMonthlyAiRevenue", "hbmSupplyCapex", "gpuSpotPrice"]

_CHIP_DEFS = {
    "gpuRentalOnDemand": {
        "label": "What a GPU rents for",
        "fmt": lambda v: f"${v:,.2f}/hr",
        "tip": ("The hourly price to rent a top GPU in the cloud, on demand. "
                "When supply catches up to demand, this number falls."),
    },
    "hyperscalerCapexRevision": {
        "label": "Big buyers' spending plans",
        "fmt": lambda v: "raised again" if v > 0 else ("trimmed" if v < 0 else "holding"),
        "tip": ("Whether the largest data-center builders raised or cut their "
                "spending plans most recently. Rising plans mean demand keeps growing."),
    },
    "odmMonthlyAiRevenue": {
        "label": "Servers actually shipped",
        "fmt": lambda v: f"+{v:.0f}% vs last year",
        "tip": ("Monthly revenue growth of the Taiwanese builders who assemble "
                "AI servers. This is supply actually arriving, not promises."),
    },
    "hbmSupplyCapex": {
        "label": "Memory factory spending",
        "fmt": lambda v: f"+{v:.0f}% vs last year",
        "tip": ("How fast memory makers are growing spending on new factories. "
                "Relief for the shortage — but new lines take about a year."),
    },
    "gpuSpotPrice": {
        "label": "Street price per GPU",
        "fmt": lambda v: f"${v:,.0f}",
        "tip": ("What one top GPU costs to buy outright today. "
                "Scarcity shows up here first."),
    },
}

_HEADLINES = {"widened": "The GPU shortage got worse this month.",
              "narrowed": "Supply gained ground on demand this month.",
              "held": "The GPU shortage held steady this month."}


def _arrow(rows: list[dict]) -> str:
    if len(rows) < 2:
        return "→"
    a, b = rows[-2]["value"], rows[-1]["value"]
    return "▲" if b > a else ("▼" if b < a else "→")


def _chip(ind: str, rows: list[dict]) -> dict | None:
    if not rows:
        return None
    d = _CHIP_DEFS[ind]
    return {"claim": f"kpi:{ind}", "label": d["label"],
            "value": d["fmt"](rows[-1]["value"]), "arrow": _arrow(rows),
            "spark": [r["value"] for r in rows[-8:]],
            "caption": "", "tip": d["tip"], "scene": None}


def _series_evidence(ind: str, rows: list[dict]) -> list[dict]:
    out, seen = [], set()
    for r in reversed(rows):
        src = r.get("source") or {}
        key = src.get("url", "")
        if not key or key in seen:
            continue
        seen.add(key)
        take = (r.get("note") or r.get("label") or "latest reading")[:90]
        out.append({"source": src.get("title", "source"),
                    "date": r.get("publishedAt", ""), "take": take,
                    "url": key})
        if len(out) == 3:
            break
    return out


def build_story_model(category_id: str, store_dir: str | Path,
                      today: dt.date) -> dict:
    store_root = Path(store_dir)
    cat_dir = store_root / category_id
    latest, _prior, as_of, rev = latest_monthly(cat_dir)
    latest = latest or {}
    gl = load_glossary()
    gap = build_gap_data(cat_dir)
    status = latest.get("categoryStatus") or {}

    headline = _HEADLINES.get((gap or {}).get("gap_word"),
                              "The state of the GPU market.")
    label = status.get("constraintLabel") or "supply of key components"
    reason = first_n_sentences(term_swap(status.get("reason") or "", gl), 1)
    deck = f"The main chokepoint is {label}. {reason}".strip()
    dateline = (today.strftime("%A, %B %d, %Y").replace(" 0", " ")
                + " · updated with each run")

    series = read_series(store_root / "series", _SERIES_IDS)
    evidence: dict[str, dict] = {}
    anchored = _chip("gpuRentalOnDemand", series.get("gpuRentalOnDemand", []))
    picks = []
    for ind in _SERIES_IDS[1:]:
        c = _chip(ind, series.get(ind, []))
        if c:
            picks.append(c)
    if anchored:
        anchored["caption"] = "always shown — the market's price of scarcity"
    for c in filter(None, [anchored, *picks]):
        ind = c["claim"].split(":", 1)[1]
        evidence[c["claim"]] = {
            "title": f"{c['label']}: {c['value']} — says who?",
            "claim_text": c["tip"].split(". ")[0] + ".",
            "findings": _series_evidence(ind, series.get(ind, [])),
            "series": c["spark"], "explore": "appendix.html"}

    model = {"category_id": category_id, "as_of": as_of, "revision": rev,
             "headline": headline, "deck": deck, "dateline": dateline,
             "gap": gap, "callouts": [], "kpis": {"anchored": anchored,
                                                  "picks": picks},
             "evidence": evidence, "scenes": [], "archive": [],
             "explore": {}}
    _add_scenes(model, latest, store_root, cat_dir, series, gl)
    return model


def _add_scenes(model, latest, store_root, cat_dir, series, gl):
    """Filled in by Task 4."""
    return None
