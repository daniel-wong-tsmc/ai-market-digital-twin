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

# F101 Phase A / Task 8 Decision B: plain-English replacements for the analyst
# words lint_story_copy's _BANNED_STORY bans from rendered prose. These are
# story-page-LOCAL (not added to glossary.json's shared prose_terms) because
# glossary.json is also read by the appendix/"how" pages' plain-language guide
# table, which lists every prose_terms key verbatim — adding these there made
# "leverage" and "robust" literally appear in that table's raw-term column and
# tripped test_build_e2e.py::test_generated_html_has_no_slop_or_raw_cowos (a
# test outside Task 8's reconciliation list). None of the replacements below
# contain any of the banned words themselves.
_STORY_TERMS = {
    "strengthening": "getting stronger",
    "tightening": "getting scarcer",
    "accelerating": "speeding up",
    "allocation": "how supply is split",
    "leverage": "negotiating power",
    "doctrine": "standard practice",
    "robust": "solid",
    "momentum": "pace",
    "DMI": "demand pace",
    "SMI": "supply pace",
}


def _story_glossary(gl: dict) -> dict:
    """The shared glossary, extended with the story-local translation table
    above. Callers pass this (not the raw `gl`) into every term_swap() call
    that touches text destined for the story page, so stored-text jargon is
    translated before it ever reaches lint_story_copy's banned-word gate."""
    return {**gl, "prose_terms": {**gl.get("prose_terms", {}), **_STORY_TERMS}}

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


def _series_evidence(ind: str, rows: list[dict], gl: dict) -> list[dict]:
    out, seen = [], set()
    for r in reversed(rows):
        src = r.get("source") or {}
        key = src.get("url", "")
        if not key or key in seen:
            continue
        seen.add(key)
        take = (r.get("note") or r.get("label") or "latest reading")[:90]
        out.append({"source": term_swap(src.get("title", "source"), gl),
                    "date": r.get("publishedAt", ""),
                    "take": term_swap(take, gl), "url": key})
        if len(out) == 3:
            break
    return out


def build_story_model(category_id: str, store_dir: str | Path,
                      today: dt.date) -> dict:
    store_root = Path(store_dir)
    cat_dir = store_root / category_id
    latest, _prior, as_of, rev = latest_monthly(cat_dir)
    latest = latest or {}
    gl = _story_glossary(load_glossary())
    gap = build_gap_data(cat_dir)
    status = latest.get("categoryStatus") or {}

    headline = _HEADLINES.get((gap or {}).get("gap_word"),
                              "The state of the GPU market.")
    label = term_swap(status.get("constraintLabel") or "supply of key components", gl)
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
            "findings": _series_evidence(ind, series.get(ind, []), gl),
            "series": c["spark"], "explore": "appendix.html"}

    model = {"category_id": category_id, "as_of": as_of, "revision": rev,
             "headline": headline, "deck": deck, "dateline": dateline,
             "gap": gap, "callouts": [], "kpis": {"anchored": anchored,
                                                  "picks": picks},
             "evidence": evidence, "scenes": [], "archive": [],
             "explore": {}}
    _add_scenes(model, latest, store_root, cat_dir, series, gl)
    return model


_ACCENTS = ["amber", "terracotta", "teal", "green"]


def _resolve_findings(latest: dict, ids: list[str]) -> list[dict]:
    by_id = {f.get("id"): f for f in latest.get("findings") or []}
    return [by_id[i] for i in ids if i in by_id]


def _finding_rows(findings: list[dict], gl: dict) -> list[dict]:
    rows, seen = [], set()
    for f in findings:
        for e in f.get("evidence") or []:
            url = e.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            rows.append({"source": term_swap(e.get("source", "source"), gl),
                        "date": e.get("date", ""),
                        "take": term_swap((f.get("statement") or "")[:90], gl),
                        "url": url})
    return rows[:3]


def _related(findings: list[dict], gl: dict) -> list[dict]:
    out, seen = [], set()
    for f in findings:
        for e in f.get("evidence") or []:
            if e.get("tier") != "secondary":
                continue
            url = e.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            out.append({"outlet": term_swap(e.get("source", ""), gl),
                        "title": term_swap(
                            (e.get("excerpt") or f.get("statement") or "")[:60], gl),
                        "date": e.get("date", ""), "url": url})
            if len(out) == 2:
                return out
    return out


def _source_line(findings: list[dict], gl: dict) -> str:
    names = []
    for f in findings:
        for e in f.get("evidence") or []:
            s = e.get("source")
            if s and s not in names:
                names.append(s)
    return "Source: " + term_swap(
        "; ".join(names[:3]) if names else "agent-tracked filings and reporting", gl)


def _mk_scene(n, title, paragraphs, series_vals, series_label, findings, gl):
    return {"n": n, "accent": _ACCENTS[(n - 1) % 4], "title": title,
            "paragraphs": [p for p in paragraphs if p],
            "visual": {"kind": "spark", "series": series_vals,
                       "label": series_label},
            "source_line": _source_line(findings, gl),
            "related": _related(findings, gl),
            "claims": [f"scene:{n}"]}


def _add_scenes(model, latest, store_root, cat_dir, series, gl):
    dims = latest.get("dimensionRatings") or {}
    status = latest.get("categoryStatus") or {}
    sv = lambda ind: [r["value"] for r in series.get(ind, [])[-8:]]
    plain = lambda t, n=2: first_n_sentences(term_swap(t or "", gl), n)

    specs = []
    if dims.get("bottleneck"):
        d = dims["bottleneck"]
        specs.append(("What tightened",
                      [plain(d.get("rationale")), plain(status.get("reason"), 1)],
                      "hbmSupplyCapex", sv("hbmSupplyCapex"),
                      "Memory factory spending",
                      _resolve_findings(latest, d.get("findingIds") or [])))
    if dims.get("momentum"):
        d = dims["momentum"]
        specs.append(("Demand kept climbing", [plain(d.get("rationale"))],
                      "hyperscalerCapexRevision", sv("hyperscalerCapexRevision"),
                      "Big buyers' spending plans",
                      _resolve_findings(latest, d.get("findingIds") or [])))
    if dims.get("unitEconomics") or series.get("odmMonthlyAiRevenue"):
        d = dims.get("unitEconomics") or {}
        specs.append(("Where supply is gaining", [plain(d.get("rationale"))],
                      "odmMonthlyAiRevenue", sv("odmMonthlyAiRevenue"),
                      "Servers actually shipped",
                      _resolve_findings(latest, d.get("findingIds") or [])))
    lines = read_implication_lines(store_root, model["category_id"],
                                   model["as_of"]) or []
    watch = [plain(l.get("text") or "", 1) for l in lines[:3]]
    watch_f = _resolve_findings(
        latest, [i for l in lines for i in l.get("finding_ids") or []])
    if watch:
        specs.append(("What would close the gap", watch,
                      "hbmSupplyCapex", sv("hbmSupplyCapex"),
                      "Memory factory spending", watch_f))

    scene_by_indicator: dict[str, int] = {}
    for i, (title, paras, ind, vals, vlabel, finds) in enumerate(specs, start=1):
        sc = _mk_scene(i, title, paras, vals, vlabel, finds, gl)
        if not sc["paragraphs"]:
            continue
        model["scenes"].append(sc)
        model["evidence"][f"scene:{sc['n']}"] = {
            "title": f"{title} — says who?",
            "claim_text": sc["paragraphs"][0],
            "findings": _finding_rows(finds, gl) or model["evidence"].get(
                "kpi:gpuRentalOnDemand", {}).get("findings", []),
            "series": vals, "explore": "appendix.html"}
        # A pick links to the scene whose visual is built from the pick's
        # own indicator series — the topical rule (owner decision). If
        # several scenes draw from the same series, keep the first
        # (lowest-numbered) one.
        scene_by_indicator.setdefault(ind, sc["n"])

    for pick in model["kpis"]["picks"]:
        ind = pick["claim"].split(":", 1)[1]
        n = scene_by_indicator.get(ind)
        if n is not None:
            pick["scene"] = n
            pick["caption"] = pick["caption"] or "picked by today's story"

    if model["gap"] and model["scenes"]:
        month = model["gap"]["months"][-1]
        first = model["scenes"][0]
        model["callouts"] = [{
            "month_key": month["key"],
            "text": f"{month['label']}: {first['title'].lower()}",
            "claim": f"scene:{first['n']}"}]

    # Archive contract (owner decision): a chip for month M shows what
    # happened DURING month M, i.e. the change from month M-1 to M — so an
    # entry needs a predecessor. The current (latest) month is today's
    # story, not archive, and is always excluded. With only 2 monthly
    # snapshots (today's data) there is no month that has both a
    # predecessor and is not the latest, so the archive is empty.
    #
    # The gap level is a running sum (see gap_chart.build_gap_data), so the
    # change in gap from M-1 to M collapses to _SCALE * (dmi_M - smi_M) —
    # exactly the same quantity, scale, and dead-band threshold that
    # decides the current month's own gap_word. Reuse those constants so
    # archive headlines are computed by the identical rule.
    from gpu_agent.dashboard.gap_chart import (_DEAD_BAND, _SCALE,
                                                _monthly_records)
    recs = _monthly_records(cat_dir)
    candidates = list(range(1, len(recs) - 1))  # has a predecessor, not latest
    arch = []
    for j in candidates[-4:]:
        delta = _SCALE * (recs[j]["dmi"] - recs[j]["smi"])
        if delta > _DEAD_BAND:
            word = "widened"
        elif delta < -_DEAD_BAND:
            word = "narrowed"
        else:
            word = "held"
        key = recs[j]["key"]
        label = dt.date(int(key[:4]), int(key[5:7]), 1).strftime("%B %Y")
        arch.append({"key": key, "label": label,
                    "text": _HEADLINES.get(word, "")})
    model["archive"] = arch

    model["explore"] = {
        "entities": len(list((store_root / "wiki" / "entity").glob("*.md"))),
        "findings": len(list((store_root / "findings").glob("*.json"))),
        "series": len(list((store_root / "series").glob("*.jsonl"))),
        "history": len(list(cat_dir.glob("*.json")))}
