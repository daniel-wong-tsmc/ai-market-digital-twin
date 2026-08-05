"""gpu_agent/dashboard/export_json.py — F110 Task 6: the dashboard.json exporter.

Deterministic Python only -- no AI, no clock, no network. Turns the day's
already-computed store artifacts (scorecard history, narrator story, chart
series) into the ONE payload the new React dashboard reads:
``site/<categoryId>/data/dashboard.json``.

Two properties matter more than any other line of code here:

1. Determinism -- the same on-disk inputs must produce byte-identical output
   across runs. No clock reads, no randomness, no dict-ordering dependence.
   ``capturedAt`` never enters the payload. The file is written UTF-8, LF-only
   (``newline="\\n"``), with sorted keys.
2. Validate before write -- a payload that fails web/schema/dashboard.schema.json
   must never reach disk. The live page renders whatever is on disk, so
   writing an invalid file is worse than writing nothing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema

from gpu_agent.chartdata.registry import load_chart_series
from gpu_agent.dashboard.bullets import _first_sentence, build_bullets
from gpu_agent.dashboard.gap_chart import _MONTHLY, build_gap_data
from gpu_agent.dashboard.plain_language import dimension_plain_name
from gpu_agent.dashboard.source_refs import assessment_ref, findings_index, refs_for_finding_ids

SCHEMA_PATH = "web/schema/dashboard.schema.json"

VERDICT_QUESTION = "Is supply catching up to demand?"
_SKIP_SCENE_TITLE = "What to watch from here"
_DEAD_BAND_PCT = 0.05

_DIM_ORDER = ["bottleneck", "momentum", "competitiveStructure", "moat",
              "unitEconomics", "strategicRisk"]
_TONE_FOR_RATING = {
    "Very weak": "bad", "Weak": "bad",
    "Mixed": "mixed",
    "Strong": "good", "Very strong": "good",
}
_DIRECTION_FOR_SCORECARD = {"improving": "improving", "worsening": "worsening", "steady": "flat"}

_CHIP_LABEL = {
    "narrowing": "Gap narrowing",
    "widening": "Gap widening",
    "flat": "Gap holding steady",
}
_CONFIDENCE_SENTENCE = {
    "high": "We are confident in this read.",
    "medium": "We are reasonably confident in this read.",
    "low": "This is a lower-confidence, more tentative read.",
}
_GAP_WORD_CAPTION = {
    "widened": "The gap widened in the latest reading.",
    "narrowed": "The gap narrowed in the latest reading.",
    "held": "The gap held roughly steady in the latest reading.",
}
_STORY_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")


# ── file selection (reuses gap_chart's own regex/tie-break rule; never
#    reimplements it -- see gpu_agent/dashboard/explore_model.py's
#    `_monthly_best_files`, which documents this exact same reuse) ──────────

def _monthly_best_files(cat_dir: Path) -> dict[str, Path]:
    """<asOf month key> -> the winning (highest-revision) scorecard file for
    that month, using gap_chart's own `_MONTHLY` pattern and "highest
    revision wins" tie-break -- the SAME selection rule
    `gap_chart._monthly_records` uses for the chart, so a caller that needs
    the rest of that month's snapshot (confidence, dimensionRatings,
    indices...) reads the exact same file rather than re-deriving which one
    is "the latest"."""
    best: dict[str, tuple[int, Path]] = {}
    for p in Path(cat_dir).glob("*.json"):
        m = _MONTHLY.match(p.name)
        if not m:
            continue
        key, rev = m.group(1), int(m.group(2))
        if key not in best or rev > best[key][0]:
            best[key] = (rev, p)
    return {k: v[1] for k, v in best.items()}


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _latest_story(story_dir: Path) -> dict:
    best_key, best_path = None, None
    for p in Path(story_dir).glob("*.json"):
        m = _STORY_DATE_RE.match(p.name)
        if not m:
            continue
        if best_key is None or m.group(1) > best_key:
            best_key, best_path = m.group(1), p
    if best_path is None:
        raise ValueError(f"no story files found under {story_dir}")
    return _load_json(best_path)


# ── verdict ──────────────────────────────────────────────────────────────

def _confidence_sentence(scorecard: dict) -> str:
    level = ((scorecard.get("confidence") or {}).get("level") or "").lower()
    return _CONFIDENCE_SENTENCE.get(
        level, "How sure we are in this read is not yet established.")


def _gap_direction(cur: float | None, prev: float | None) -> str:
    """narrowing/widening/flat on the CURRENT scorecard's own
    `indices.divergence.sdgiGap` vs. the PREVIOUS scorecard's, with a 5%
    relative dead-band (never an absolute one -- that is gap_chart.py's own,
    unrelated, chart-level word, computed on a different quantity)."""
    if cur is None or prev is None or prev == 0:
        return "flat"
    change = cur - prev
    if abs(change) / abs(prev) <= _DEAD_BAND_PCT:
        return "flat"
    return "widening" if change > 0 else "narrowing"


def _sdgi_gap(raw: dict | None) -> float | None:
    if not raw:
        return None
    return ((raw.get("indices") or {}).get("divergence") or {}).get("sdgiGap")


def _build_chip(latest_raw: dict, prev_raw: dict | None) -> dict:
    direction = _gap_direction(_sdgi_gap(latest_raw), _sdgi_gap(prev_raw))
    return {"label": _CHIP_LABEL[direction], "direction": direction}


def _verdict_answer(story: dict) -> str:
    """headline recast by rule: the headline stands as the first sentence
    (narrator headlines are written to already answer the verdict question),
    with the first sentence of `deck` appended as the second."""
    headline = (story.get("headline") or "").strip()
    deck_first = _first_sentence(story.get("deck") or "")
    if not headline:
        return deck_first
    sep = "" if headline.endswith((".", "!", "?")) else "."
    return f"{headline}{sep} {deck_first}".strip()


def _verdict_so_what(story: dict, scorecard: dict) -> str:
    deck = story.get("deck")
    if deck:
        return deck
    return _first_sentence(scorecard.get("narrative") or "")


def _headline_scene(story: dict) -> dict:
    for scene in story.get("scenes", []):
        if (scene.get("title") or "").strip() != _SKIP_SCENE_TITLE:
            return scene
    return {}


def _verdict_sources(story: dict, findings_by_id: dict) -> list[dict]:
    scene = _headline_scene(story)
    refs = refs_for_finding_ids(scene.get("claimFindingIds", []), findings_by_id, max_refs=3)
    return [assessment_ref(refs)]


def _build_verdict(story: dict, latest_raw: dict, prev_raw: dict | None,
                    findings_by_id: dict) -> dict:
    return {
        "question": VERDICT_QUESTION,
        "answer": _verdict_answer(story),
        "chip": _build_chip(latest_raw, prev_raw),
        "confidence": _confidence_sentence(latest_raw),
        "soWhat": _verdict_so_what(story, latest_raw),
        "sources": _verdict_sources(story, findings_by_id),
    }


# ── gap chart (reuses gap_chart.build_gap_data verbatim for the dated
#    demand/supply points -- its own date/version selection is never
#    reimplemented here) ─────────────────────────────────────────────────

def _gap_annotation(gap_data: dict) -> dict:
    demand, supply, months = gap_data["demand"], gap_data["supply"], gap_data["months"]
    idx = max(range(len(months)), key=lambda i: abs(demand[i] - supply[i]))
    return {"date": months[idx]["key"], "label": "Widest gap so far"}


def _build_gap_chart(gap_data: dict) -> dict:
    points = [{"date": m["key"], "demand": d, "supply": s}
              for m, d, s in zip(gap_data["months"], gap_data["demand"], gap_data["supply"])]
    caption = (_GAP_WORD_CAPTION[gap_data["gap_word"]] +
               " Demand and supply are shown as an indexed score built from "
               "each month's reported momentum, not a raw unit.")
    return {
        "points": points,
        "annotation": _gap_annotation(gap_data),
        "caption": caption,
        "sources": [],
    }


# ── six dimensions ───────────────────────────────────────────────────────

def _build_dimensions(latest_raw: dict, findings_by_id: dict) -> list[dict]:
    ratings = latest_raw.get("dimensionRatings") or {}
    dims = []
    for name in _DIM_ORDER:
        r = ratings.get(name) or {}
        rating_word = r.get("rating") or ""
        rationale = r.get("rationale") or ""
        dims.append({
            "id": name,
            "plainName": dimension_plain_name(name),
            "ratingWord": rating_word,
            "tone": _TONE_FOR_RATING.get(rating_word, "mixed"),
            "direction": _DIRECTION_FOR_SCORECARD.get(r.get("direction"), "flat"),
            "confidence": (r.get("confidence") or {}).get("level") or "",
            "summary": _first_sentence(rationale),
            "reasoning": rationale,
            "evidence": refs_for_finding_ids(r.get("findingIds") or [], findings_by_id, max_refs=3),
        })
    return dims


def _footer_links() -> list[dict]:
    return [
        {"label": "Evidence", "href": "findings/"},
        {"label": "Numbers we track", "href": "series/"},
        {"label": "Past readings", "href": "history.html"},
        {"label": "Story archive", "href": "story/"},
    ]


# ── top-level assembly ───────────────────────────────────────────────────

def build_dashboard_payload(category_id: str, store_dir: str) -> dict:
    """Assemble and validate the dashboard.json payload for `category_id`.

    `store_dir` is the store ROOT (e.g. "store"): scorecards + story live
    under `<store_dir>/<category_id>/`, chart series under
    `<store_dir>/series/`, matching every other CLI verb's convention
    (see gpu_agent/cli.py's chart-fetch / coverage-record).

    Raises ValueError (never writes anything) when the inputs cannot honestly
    support a payload -- no scorecard history, no story, or fewer than two
    months of demand/supply history for the gap chart -- rather than
    fabricating a partial or misleading page.
    """
    store_root = Path(store_dir)
    cat_dir = store_root / category_id
    series_dir = store_root / "series"

    files = _monthly_best_files(cat_dir)
    if not files:
        raise ValueError(f"no monthly scorecard history found for {category_id!r} under {cat_dir}")
    keys = sorted(files)
    latest_raw = _load_json(files[keys[-1]])
    prev_raw = _load_json(files[keys[-2]]) if len(keys) > 1 else None

    story = _latest_story(cat_dir / "story")
    findings_by_id = findings_index(latest_raw)

    series_reg = load_chart_series()
    bullets = build_bullets(story, latest_raw, series_reg, str(series_dir))

    gap_data = build_gap_data(cat_dir)
    if gap_data is None:
        raise ValueError(
            f"fewer than two months of demand/supply history under {cat_dir} "
            "-- cannot honestly draw the gap chart")

    payload = {
        "schemaVersion": "1.0",
        "categoryId": category_id,
        "asOf": story.get("storyDate", ""),
        "verdict": _build_verdict(story, latest_raw, prev_raw, findings_by_id),
        "gapChart": _build_gap_chart(gap_data),
        "bullets": bullets,
        "dimensions": _build_dimensions(latest_raw, findings_by_id),
        "footerLinks": _footer_links(),
    }

    schema = json.loads(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)
    return payload


def write_dashboard_json(category_id: str, store_dir: str, site_dir: str) -> Path:
    """Build + validate the payload, then write it to
    `<site_dir>/<category_id>/data/dashboard.json` -- UTF-8, LF line endings,
    sorted keys, so an unchanged input produces a byte-identical file (a
    quiet daily commit, not a noisy full-file diff)."""
    payload = build_dashboard_payload(category_id, store_dir)
    out_path = Path(site_dir) / category_id / "data" / "dashboard.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.write("\n")
    return out_path
