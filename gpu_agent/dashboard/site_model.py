"""F95 site page model — one dict per category page, assembled from stored artifacts only.

Pure projection: reuses build_model (same change engine as the text brief — parity by
construction), then adds the F95 extras: featured metric, contribution rows, the FOR TSMC
implication artifact (read defensively; F65 may not be merged), and the WHY block."""
from __future__ import annotations

import json
from pathlib import Path

from gpu_agent.config import REGISTRY_PATH
from gpu_agent.cycle import AssignmentProvider
from gpu_agent.registry.indicators import IndicatorRegistry
from gpu_agent.report import _VERSION_RE, evidence_vintage, load_scorecard

from .build import build_model
from .contributions import contribution_rows
from .featured import assemble_readings, load_library, select_featured
from .glossary import load_glossary, term_swap
from .scorecards import load_scorecards

# F95 item 3: gpu_agent/report.py's shared change-engine renders a "this line is a brand
# new entry" marker as the full-width character U+FF0B ("＋"), not ASCII "+" (see
# _CHANGE_ARROW in report.py, FROZEN — F95 must not edit it or its byte-pinned report
# tests). Normalized to ASCII here, at the public-page presentation layer only.
_FULLWIDTH_PLUS = "＋"


def _drop_fullwidth_plus(text: str) -> str:
    return text.replace(_FULLWIDTH_PLUS, "+") if text else text

# Alert-ladder rule ids -> plain English (unknown ids fall back to id with spaces).
_RULE_PLAIN = {
    "gap-band-changed": "the demand-vs-supply gap band changed within the last week",
    "high-call-moved": "a high-confidence call moved within the last week",
    "constraint-rotated": "the main limiting factor changed within the last week",
    "calls-co-move": "two or more calls moved in the same direction within the last week",
    "high-call-broke": "a high-confidence call broke or was retired within the last week",
    "demand-reversal": "demand worsened while the gap moved toward glut within the last week",
}


def rule_plain(rule_id: str) -> str:
    return _RULE_PLAIN.get(rule_id, rule_id.replace("-", " "))


def read_implication(store_root, category_id: str, as_of: str):
    """F65 artifact, read defensively: {'lines': [str,...]} or None. Never raises."""
    p = Path(store_root) / "implications" / category_id / f"{as_of}.json"
    try:
        art = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    out = []
    for ln in (art.get("lines") or []) if isinstance(art, dict) else []:
        if isinstance(ln, str):
            out.append(ln)
        elif isinstance(ln, dict):
            out.append(ln.get("text") or ln.get("watchItem") or "")
    lines = [l for l in out if l]
    return {"lines": lines} if lines else None


def _band_word(tile_band: str) -> str:
    return tile_band.split()[0].capitalize()


def _delta_phrase(value, prior, unit):
    if prior is None:
        return "no prior run to compare"
    d = value - prior
    word = "up" if d > 0 else ("down" if d < 0 else "flat")
    if unit == "$/GPU-hr":
        return f"{word} ${abs(d):.2f} vs about a month ago"
    return f"{word} {abs(d):.2f} vs the prior run"


def _top_row(rows, side_key):
    live = [r for r in rows if r[side_key] != 0]
    if not live:
        return None
    return max(live, key=lambda r: (abs(r[side_key]), r["indicator_id"]))


def _why(model, featured, rows, sc):
    why = []
    a = model["alert"]
    fired = "; ".join(rule_plain(t) for t in a["triggers"]) if a["triggers"] else \
        "no alert rule fired"
    text = f"The light is {a['color'].upper()} because {fired}."
    if a["raw"] != a["color"]:
        text += (f" Today's raw read was {a['raw'].upper()}; the shown color only steps"
                 " down after two calm runs in a row.")
    why.append({"topic": "alert", "text": text})

    for topic, side_key, tile in (("demand", "demand_contribution", model["tiles"][0]),
                                  ("supply", "supply_contribution", model["tiles"][1])):
        top = _top_row(rows, side_key)
        if top is None:
            t = (f"{topic.capitalize()} reads {_band_word(tile['band'])}; no scoring"
                 " findings pulled it this cycle.")
        else:
            pull = "up" if top[side_key] > 0 else "down"
            # Row statements were already term_swap'd once in build_site_model's row
            # loop (the single canonical pass); reuse them as-is — no second swap.
            t = (f"{topic.capitalize()} reads {_band_word(tile['band'])}. Biggest pull"
                 f" {pull}: {top['label']} - {top['statement']}")
        why.append({"topic": topic, "text": t})

    ds = model["demand_supply"]
    why.append({"topic": "gap", "text":
                (f"The gap score is demand minus supply: {ds['dmi']:+.2f} minus"
                 f" {ds['smi']:+.2f} = {ds['sdgi']:+.2f}, currently"
                 f" {ds['sdgi_direction'] or 'balanced'}.")})

    if featured is not None:
        t = f"{featured['reason_text']} {featured['how_to_read']}"
        if featured["honesty_note"]:
            t += f" ({featured['honesty_note']})"
        why.append({"topic": "featured", "text": t})

    # evidence_vintage(sc) actually returns (median_date, oldest_date,
    # share_older_than_42d) -- confirmed against gpu_agent/report.py, NOT
    # (oldest, newest, share) as an earlier draft of this module assumed. There is no
    # "newest" date in its return value, so the trust sentence is built from the two
    # dates it really gives us (oldest + median) plus the staleness share, instead of
    # fabricating a "spans X to Y" claim the data can't support.
    median_date, oldest_date, stale_share = evidence_vintage(sc)
    if oldest_date and median_date:
        pct = round(stale_share * 100)
        span = (f"Evidence dates run back to {oldest_date}, with a typical (median) date"
                f" of {median_date}; {pct}% of it is more than six weeks old.")
    else:
        span = "Evidence dates were not recorded this cycle."
    prim = sum(1 for f in model["top_signals"] if f.get("tier") == "primary")
    why.append({"topic": "trust", "text":
                f"{span} {prim} of the {len(model['top_signals'])} ranked signals trace"
                " to a primary source."})
    return why


def build_site_model(category_id, store_dir, work_dir, plain_path, price_fn=None,
                     assignments_root="fixtures"):
    model, _summary = build_model(category_id, store_dir, work_dir, plain_path,
                                  generated_at="")
    g = load_glossary()

    # F95 item 3: strip the shared renderer's full-width "new entry" marker (see
    # _FULLWIDTH_PLUS above) before it reaches the public page.
    for w in model["what_changed"]:
        w["phrase"] = _drop_fullwidth_plus(w["phrase"])
        w["text"] = _drop_fullwidth_plus(w["text"])

    # Same layout detection as build_model (build.py:57-59): store_dir either IS the
    # category dir or is the store root holding <category_id>/.
    store_dir = Path(store_dir)
    if (store_dir / category_id).is_dir():
        store_root, cat_dir = store_dir, store_dir / category_id
    else:
        store_root, cat_dir = store_dir.parent, store_dir
    latest_path = max((p for p in cat_dir.iterdir() if _VERSION_RE.match(p.name)),
                      key=lambda p: (_VERSION_RE.match(p.name).group(1),
                                     int(_VERSION_RE.match(p.name).group(2))))
    sc = load_scorecard(latest_path)

    # F97: full-rationale projection for the appendix's per-dimension anchors —
    # read straight off the latest scorecard's validated dimension ratings (each
    # DimensionRating already carries a non-empty rating and rationale).
    dimension_rationales = [
        {"name": name, "rating": r.rating, "rationale": r.rationale}
        for name, r in sc.dimensionRatings.items()]

    reg = IndicatorRegistry.load(REGISTRY_PATH)
    # F95 item 2: same source of truth pipeline.py uses — the per-category assignment
    # config file (AssignmentProvider, `<root>/asg.<category_id>.json`, default root
    # "fixtures"; see gpu_agent/cycle.py and cli.py's --assignments default). This is
    # static per-category config, not per-run state, so the site builder can read it too.
    assignment = AssignmentProvider(assignments_root).get(category_id)
    weight_overrides = assignment.weights if assignment is not None else {}
    rows = contribution_rows(sc.findings, reg, category_id, weight_overrides=weight_overrides)
    for r in rows:
        r["statement"] = term_swap(r["statement"], g)

    recs = load_scorecards(category_id, str(cat_dir))
    latest, prev = recs[-1], (recs[-2] if len(recs) > 1 else None)
    readings = assemble_readings(load_library(), latest, prev, latest["as_of"],
                                 price_fn=price_fn)
    sel = select_featured(readings, model["alert"]["triggers"])
    featured = None
    if sel is not None:
        r = sel.reading
        featured = {"metric_id": r.metric_id, "plain_label": r.plain_label,
                    "display": r.display, "unit": r.unit,
                    "delta_phrase": _delta_phrase(r.value, r.prior, r.unit),
                    "reason_code": sel.reason_code, "reason_text": sel.reason_text,
                    "how_to_read": r.how_to_read, "honesty_note": r.honesty_note,
                    "value": r.value, "prior": r.prior}

    model.update({
        "as_of": model["latest_date"],
        "category_id": category_id,
        "featured": featured,
        "contributions": rows,
        "implication": read_implication(store_root, category_id, model["latest_date"]),
        "why": _why(model, featured, rows, sc),
        "dimension_rationales": dimension_rationales,
    })
    return model
