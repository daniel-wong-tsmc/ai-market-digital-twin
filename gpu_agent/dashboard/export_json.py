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

A THIRD property, added after the first review round: internal consistency.
The chip, the gap chart, its caption, and the verdict's opening phrase must
never disagree with each other -- they are all derived from the ONE real
per-reading demand/supply series (`gap_chart.build_reading_series` +
`gap_chart.gap_trend_word`), never from two different quantities computed
two different ways.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema

from gpu_agent.chartdata.registry import load_chart_series
from gpu_agent.dashboard.bullets import _first_sentence, build_bullets
from gpu_agent.dashboard.gap_chart import (build_reading_series, gap_trend_word,
                                            monthly_best_files)
from gpu_agent.dashboard.plain_language import dimension_plain_name
from gpu_agent.dashboard.source_refs import assessment_ref, findings_index, refs_for_finding_ids

# Resolved relative to this package (not the process CWD) -- MINOR fix (review
# round 1): a relative path here only worked when the `dashboard-json` CLI
# verb happened to be invoked from the repo root. This is the CLI's only
# consumer, but the run-cycle and integration tasks may not share that
# assumption.
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "web" / "schema" / "dashboard.schema.json"

VERDICT_QUESTION = "Is supply catching up to demand?"
_SKIP_SCENE_TITLE = "What to watch from here"

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
# CONTROLLER RULING (review round 1, Critical 3): the answer must LEAD with a
# short, direct, data-derived answer to the verdict question, keyed off the
# SAME gap_trend_word() direction that drives the chip and the chart caption
# -- never a headline recast, and never contradicting the chip beside it.
_ANSWER_OPENING = {
    "widening": "Not yet.",
    "narrowing": "Getting closer.",
    "flat": "Not yet.",
}
# MINOR fix (review round 1): the mock's verdict-meta text carries no
# trailing period (it sits in a `<span>` next to a "·" separator, not a
# standalone sentence) -- matched verbatim here.
_CONFIDENCE_SENTENCE = {
    "high": "We are confident in this read",
    "medium": "We are reasonably confident in this read",
    "low": "This is a lower-confidence, more tentative read",
}
# CONTROLLER RULING (review round 1, Critical 1 + Important 5): the caption's
# direction word now comes from the exact same `gap_trend_word()` call that
# produces the chip's direction -- both index this one dict, so they can
# never name two different directions for the same day's data.
_GAP_WORD_CAPTION = {
    "widening": "The gap widened in the latest reading.",
    "narrowing": "The gap narrowed in the latest reading.",
    "flat": "The gap held roughly steady in the latest reading.",
}
# FINAL REVIEW, Important 1: the six dimension rows sit under the heading
# "How sure we are" and were pasting the scorecard's INTERNAL
# `confidence.basis` straight into reader copy -- an executive was reading
# "Medium — majority of 3/3 samples; capped by finding confidence (medium)."
# The approved mock (lines 601, 637) writes reader-facing sentences about
# the EVIDENCE, not about our sampling method. The verdict zone already
# translates the same contract field via `_CONFIDENCE_SENTENCE`; the
# dimension rows now get their own mapping, so the raw basis string never
# reaches a reader. The "high" and "medium" sentences below are the mock's
# own words, verbatim.
_DIMENSION_CONFIDENCE_SENTENCE = {
    "high": "High — drawn from company filings and calls.",
    "medium": "Medium — the underlying reports are single-source in places.",
    "low": "Low — the reporting behind this is thin and not yet corroborated.",
}
_STORY_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")



# ── verdict ──────────────────────────────────────────────────────────────

def _confidence_sentence(scorecard: dict) -> str:
    level = ((scorecard.get("confidence") or {}).get("level") or "").lower()
    return _CONFIDENCE_SENTENCE.get(
        level, "How sure we are in this read is not yet established")


def _build_chip(direction: str) -> dict:
    return {"label": _CHIP_LABEL[direction], "direction": direction}


def _verdict_support_sentence(story: dict) -> str:
    """The ONE supporting sentence for the verdict answer -- the story's own
    headline (its first sentence), falling back to the deck's first
    sentence only when there is no headline at all."""
    return _first_sentence(story.get("headline") or "") or _first_sentence(story.get("deck") or "")


def _verdict_answer(direction: str, support_sentence: str) -> str:
    """A short, direct answer keyed off `direction` (so it can never
    contradict the chip built from the same value), plus exactly one
    supporting sentence -- roughly a dozen words, not the 51-word,
    self-quoting paragraph review round 1 flagged."""
    opening = _ANSWER_OPENING[direction]
    return f"{opening} {support_sentence}".strip()


def _verdict_so_what(story: dict, scorecard: dict, support_sentence: str) -> str:
    """The story's `deck`, unless its first sentence is the exact sentence
    already used inside `answer` -- in which case fall back to the
    scorecard narrative's first sentence, so `soWhat` never repeats a
    sentence the reader just read forty pixels above (review round 1,
    Critical 3)."""
    deck = (story.get("deck") or "").strip()
    if deck and _first_sentence(deck) != support_sentence:
        return deck
    narrative_first = _first_sentence(scorecard.get("narrative") or "")
    if narrative_first and narrative_first != support_sentence:
        return narrative_first
    return ""


def _headline_scene(story: dict) -> dict:
    for scene in story.get("scenes", []):
        if (scene.get("title") or "").strip() != _SKIP_SCENE_TITLE:
            return scene
    return {}


def _verdict_sources(story: dict, findings_by_id: dict) -> list[dict]:
    """assessment_ref over the headline scene's top-3 refs -- or an honest
    empty list (never an "our assessment, based on:" with nothing behind
    it) when none of its finding ids resolve to a real reference (MINOR fix,
    review round 1)."""
    scene = _headline_scene(story)
    refs = refs_for_finding_ids(scene.get("claimFindingIds", []), findings_by_id, max_refs=3)
    return [assessment_ref(refs)] if refs else []


def _build_verdict(story: dict, latest_raw: dict, direction: str, findings_by_id: dict) -> dict:
    support_sentence = _verdict_support_sentence(story)
    return {
        "question": VERDICT_QUESTION,
        "answer": _verdict_answer(direction, support_sentence),
        "chip": _build_chip(direction),
        "confidence": _confidence_sentence(latest_raw),
        "soWhat": _verdict_so_what(story, latest_raw, support_sentence),
        "sources": _verdict_sources(story, findings_by_id),
    }


# ── gap chart ────────────────────────────────────────────────────────────
#
# Reuses gap_chart.build_reading_series (real calendar dates -- USER DECISION,
# round 3: a MIX of genuine single-day readings and monthly deep-reads,
# anchored and sorted on a true calendar, never index-spaced -- see that
# function's own docstring) and gap_chart.gap_trend_word (the ONE direction
# computation shared with the verdict chip -- Critical 1, round 1). Neither
# is reimplemented here.

def _gap_annotation(readings: list[dict]) -> dict:
    idx = max(range(len(readings)), key=lambda i: abs(readings[i]["demand"] - readings[i]["supply"]))
    return {"date": readings[idx]["date"], "label": "Widest gap so far"}


def _gap_chart_sources(latest_raw: dict, findings_by_id: dict) -> list[dict]:
    """IMPORTANT fix (review round 1): the chart is our own reading of the
    dimension ratings' own findings -- an assessment over the top refs
    across every dimension's `findingIds` on the latest reading, per spec
    §6's synthesis form. An honest empty list only when nothing resolves."""
    ratings = latest_raw.get("dimensionRatings") or {}
    seen: set[str] = set()
    all_ids: list[str] = []
    for name in _DIM_ORDER:
        for fid in (ratings.get(name) or {}).get("findingIds") or []:
            if fid not in seen:
                seen.add(fid)
                all_ids.append(fid)
    refs = refs_for_finding_ids(all_ids, findings_by_id, max_refs=3)
    return [assessment_ref(refs)] if refs else []


# USER DECISION (round 3): the reader must be told, in plain English, that
# some points are single-day readings and others are a whole month's figure
# -- said once here, only when the series genuinely mixes both, never a
# fabricated disclosure on a series that happens to be all one grain.
_MIX_DISCLOSURE = (
    " Some points are a single day's reading; others are a whole month's "
    "figure, placed at the start of that month."
)


def _gap_chart_caption(readings: list[dict], direction: str) -> str:
    grains = {r["grain"] for r in readings}
    mix_clause = _MIX_DISCLOSURE if len(grains) > 1 else ""
    return (_GAP_WORD_CAPTION[direction] +
            " Demand and supply are each reading's own reported momentum "
            "score, not a raw shipment count." + mix_clause)


def _build_gap_chart(readings: list[dict], direction: str, latest_raw: dict,
                      findings_by_id: dict) -> dict:
    # "grain" (reading/month) drives the caption's mix disclosure above but
    # is never part of the schema-facing point shape -- gapPoint is exactly
    # {date, demand, supply}, additionalProperties: false.
    points = [{"date": r["date"], "demand": r["demand"], "supply": r["supply"]} for r in readings]
    return {
        "points": points,
        "annotation": _gap_annotation(readings),
        "caption": _gap_chart_caption(readings, direction),
        "sources": _gap_chart_sources(latest_raw, findings_by_id),
    }


# ── six dimensions ───────────────────────────────────────────────────────

def _dimension_summary_and_reasoning(rationale: str) -> tuple[str, str]:
    """Row summary: the rationale's own first REAL sentence
    (`bullets._first_sentence` -- already battle-tested against decimal
    points ("67.7") and abbreviations, so it is reused verbatim here rather
    than re-derived).

    IMPORTANT 7 fix, review round 3: a length-capped clause-boundary cut
    (round 1's fix) produced grammatically broken summaries on real data --
    five of six real dimensions ended on a dangling comma, one on a colon,
    and one ("...as custom chips.") was a hard mid-clause cut with a
    FABRICATED period, manufacturing a confident-sounding statement the
    source never made. On an honesty-first page, a truncation that changes
    the meaning is worse than a long sentence, so this function no longer
    tries to cut short: a summary must always be the rationale's own
    complete first sentence, ending in real terminal punctuation the source
    itself wrote -- never a comma, colon, semicolon, conjunction, or
    preposition, and never a period this code invented. If that sentence
    happens to be short, the row reads short (as most real ones do); if it
    is long, the row reads long -- length is the lesser problem next to a
    fabricated-sounding fragment.

    Panel reasoning: whatever of the rationale is NOT already the summary,
    so opening the click-to-explain panel adds new sentences instead of
    repeating the row word for word. When the rationale is short enough
    that its first (and only) sentence IS the whole rationale, there is
    honestly nothing left to add -- reasoning is then an explicit empty
    string, never the summary repeated back (round 3 fix: the round-1
    fallback-to-full-rationale here was exactly that repeat, just masked on
    real data because every real rationale happens to have more than one
    sentence)."""
    rationale = (rationale or "").strip()
    if not rationale:
        return "", ""
    summary = _first_sentence(rationale)
    remainder = rationale[len(summary):].strip() if rationale.startswith(summary) else ""
    return summary, remainder


def _dimension_confidence_sentence(rating: dict) -> str:
    """A full plain-English sentence about the EVIDENCE (mock lines 601 and
    637), not the raw "medium"/"high" level string and NEVER the scorecard's
    internal `confidence.basis`.

    FINAL REVIEW, Important 1: this used to paste `basis` verbatim, so the
    row's "How sure we are" block read "Medium — majority of 3/3 samples;
    capped by finding confidence (medium)." -- internal scoring method
    language in front of an executive. The verdict zone has translated the
    same contract field through `_CONFIDENCE_SENTENCE` since round 1; this
    is the matching translation for the dimension rows, so one contract
    field now has two reader-facing consumers and no raw one.

    A level we do not recognise (or none at all) returns an empty string --
    the panel then omits the block entirely rather than showing a heading
    over nothing, or guessing at a confidence we cannot honestly name."""
    conf = rating.get("confidence") or {}
    level = (conf.get("level") or "").strip().lower()
    return _DIMENSION_CONFIDENCE_SENTENCE.get(level, "")


def _build_dimensions(latest_raw: dict, findings_by_id: dict) -> list[dict]:
    ratings = latest_raw.get("dimensionRatings") or {}
    dims = []
    for name in _DIM_ORDER:
        r = ratings.get(name) or {}
        rating_word = r.get("rating") or ""
        # MINOR fix (review round 1): an unrecognized/missing rating word
        # used to silently fall back to tone "mixed" -- exactly the
        # silent-failure pattern this lane keeps catching. A dimension row
        # we cannot honestly color must fail loudly, not quietly mislabel.
        if rating_word not in _TONE_FOR_RATING:
            raise ValueError(
                f"dimension {name!r}: unrecognized rating word {rating_word!r} "
                "-- refusing to guess a bad/mixed/good tone")
        rationale = r.get("rationale") or ""
        summary, reasoning = _dimension_summary_and_reasoning(rationale)
        dims.append({
            "id": name,
            "plainName": dimension_plain_name(name),
            "ratingWord": rating_word,
            "tone": _TONE_FOR_RATING[rating_word],
            "direction": _DIRECTION_FOR_SCORECARD.get(r.get("direction"), "flat"),
            "confidence": _dimension_confidence_sentence(r),
            "summary": summary,
            "reasoning": reasoning,
            "evidence": refs_for_finding_ids(r.get("findingIds") or [], findings_by_id, max_refs=3),
        })
    return dims


def _footer_links() -> list[dict]:
    return [
        {"label": "Evidence", "href": "findings/"},
        {"label": "Numbers we track", "href": "series/"},
        {"label": "Past readings", "href": "history.html"},
        {"label": "Story archive", "href": "story/"},
        {"label": "Companies", "href": "entities/"},
    ]


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


# ── top-level assembly ───────────────────────────────────────────────────

def build_dashboard_payload(category_id: str, store_dir: str) -> dict:
    """Assemble and validate the dashboard.json payload for `category_id`.

    `store_dir` is the store ROOT (e.g. "store"): scorecards + story live
    under `<store_dir>/<category_id>/`, chart series under
    `<store_dir>/series/`, matching every other CLI verb's convention
    (see gpu_agent/cli.py's chart-fetch / coverage-record).

    Raises ValueError (never writes anything) when the inputs cannot honestly
    support a payload -- no scorecard history, no story, or fewer than two
    real readings for the gap chart -- rather than fabricating a partial or
    misleading page.
    """
    store_root = Path(store_dir)
    cat_dir = store_root / category_id
    series_dir = store_root / "series"

    files = monthly_best_files(cat_dir)
    if not files:
        raise ValueError(f"no monthly scorecard history found for {category_id!r} under {cat_dir}")
    latest_raw = _load_json(files[max(files)])

    story = _latest_story(cat_dir / "story")
    findings_by_id = findings_index(latest_raw)

    series_reg = load_chart_series()
    # F113: the quarantine store of series this cycle's researcher found and
    # the deterministic verifier re-checked, sitting between the curated
    # match and the findings fallback (design spec §4). It is deliberately
    # NOT `registry/chart-series.json` -- that registry stays human-curated
    # and gains no writer here.
    bullets = build_bullets(story, latest_raw, series_reg, str(series_dir),
                            research_dir=str(cat_dir / "research-series"))

    readings = build_reading_series(cat_dir)
    if len(readings) < 2:
        raise ValueError(
            f"fewer than two real readings under {cat_dir} "
            "-- cannot honestly draw the gap chart")
    direction = gap_trend_word(readings)

    payload = {
        "schemaVersion": "1.1",
        "categoryId": category_id,
        "asOf": story.get("storyDate", ""),
        "verdict": _build_verdict(story, latest_raw, direction, findings_by_id),
        "gapChart": _build_gap_chart(readings, direction, latest_raw, findings_by_id),
        "bullets": bullets,
        "dimensions": _build_dimensions(latest_raw, findings_by_id),
        "footerLinks": _footer_links(),
    }

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)
    return payload


def write_dashboard_json(category_id: str, store_dir: str, site_dir: str) -> Path:
    """Build + validate the payload, then write it to
    `<site_dir>/<category_id>/data/dashboard.json` -- UTF-8, LF line endings,
    sorted keys, so an unchanged input produces a byte-identical file (a
    quiet daily commit, not a noisy full-file diff).

    Validation happens INSIDE `build_dashboard_payload`, before this function
    ever opens the output path -- an invalid payload raises here and no file
    is created or overwritten (see tests/test_export_json.py's
    `test_corrupt_input_leaves_no_file_on_disk`, which proves this ordering
    by reversing it and watching the test go red)."""
    payload = build_dashboard_payload(category_id, store_dir)
    out_path = Path(site_dir) / category_id / "data" / "dashboard.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.write("\n")
    return out_path
