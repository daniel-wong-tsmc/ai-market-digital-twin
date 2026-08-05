"""F110 Task 5: story bullets + honest chart matching.

Deterministic Python only -- no AI, no prompts, no model calls. Turns the
day's story scenes into exactly three dashboard bullets, and decides --
honestly -- whether each bullet may carry a small supporting chart.

The rule that matters more than any other: a small chart reads as an
established fact to an executive reader, so it may only appear when there
is real, defensible, non-estimate data behind it, drawn from a real
measured quantity we can name in plain English, and honestly attributed.
When nothing qualifies, the bullet gets a plain-English ``noChartReason``
explaining what's missing -- never a decorative or forced chart.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from gpu_agent.chartdata.registry import ChartSeries
from gpu_agent.dashboard.source_refs import assessment_ref, findings_index, refs_for_finding_ids

_SKIP_SCENE_TITLE = "What to watch from here"
_MAX_BULLETS = 3
_MAX_CHART_POINTS = 10

# Rule 2 (registered chart-series) density gate.
_MIN_SERIES_POINTS = 4
# Rule 3 (fallback: the scene's own findings' indicator history) density
# gate -- fixed by the brief: at least 6 points, spanning at least 3
# distinct months, and never estimate-grade.
_MIN_FALLBACK_POINTS = 6
_MIN_FALLBACK_MONTHS = 3

# Controller ruling (review of this task, applying the design spec's
# honesty principle -- not a new design decision): the rule-3 fallback may
# only chart a raw store/series unit when that unit names a real,
# plain-English measurable quantity -- never an internal composite score
# or index. 'revision_direction' (a net count of buyers revising spend up
# vs. down), 'credit_condition_index', 'ramp_minus_order_rate_pct' and
# 'price_vs_volume_rate' are all internal analytical constructs, not
# things a reader can point to in the world, so none of them may ever
# reach a chart's axis. Only units in this map may be charted, and the
# chart always shows the plain value, never the raw code.
#
# Loaded from a small JSON file (round-2 review, MINOR): a new legitimate
# unit (e.g. "GW" for gigawatts, "USD_M") can be whitelisted by editing
# data, not code. Falls back to this same built-in default if the file is
# missing or unreadable -- never crashes the pipeline over a missing file.
_DEFAULT_PLAIN_UNITS = {
    "USD_B": "US$ billions",
    "USD": "US$",
    "USD_per_hr": "US$ per hour",
    "pct_yoy": "%, year over year",
}
_PLAIN_UNITS_PATH = "registry/plain-units.json"


def _load_plain_units(path: str = _PLAIN_UNITS_PATH) -> dict[str, str]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        units = raw.get("units")
        if isinstance(units, dict) and all(isinstance(v, str) for v in units.values()):
            return units
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return dict(_DEFAULT_PLAIN_UNITS)


_PLAIN_UNITS = _load_plain_units()

_SENTENCE_BOUNDARY = re.compile(r"[.!?]+(?=\s|$)")
# Round-2 review (MINOR): "no" removed -- it made "The answer is no. It
# kept growing." get merged into one sentence, which is a far more common
# real-text pattern than "No. 5" ever needing that abbreviation guard.
_ABBREVIATIONS = {
    "u.s", "u.s.a", "u.k", "e.g", "i.e", "dr", "mr", "mrs", "ms", "prof",
    "sr", "jr", "st", "vs", "etc", "inc", "corp", "co", "ltd",
    "gen", "col", "sgt", "rep", "sen", "gov", "approx",
}


def _looks_like_abbreviation(token: str) -> bool:
    """True for a token whose trailing '.' is NOT a real sentence end --
    a known abbreviation ('Dr.', 'e.g.', 'U.S.') or a bare initial ('J.').
    """
    token = token.rstrip(".!?")
    if not token:
        return False
    if token.lower() in _ABBREVIATIONS:
        return True
    # Initials like "U.S" (parts ["U", "S"]) or a lone capital letter "J".
    parts = [p for p in token.split(".") if p]
    return bool(parts) and all(len(p) <= 1 for p in parts)


def _first_sentence(text: str) -> str:
    """First real sentence of `text` (up to and including its terminal
    punctuation); the whole (stripped) string if no real boundary is found.

    Two failure modes a naive "stop at the first terminator" scan hits on
    real story text, both guarded against here:
    - a mid-number decimal point ("1.4 gigawatts") is never a boundary,
      because a terminator only counts when it's followed by whitespace
      (or end of string) -- "1.4" has no space after the '.'.
    - an abbreviation ("U.S.", "Dr.", "e.g.") IS followed by whitespace,
      so that alone isn't enough; `_looks_like_abbreviation` on the token
      immediately before the candidate boundary skips those too.
    """
    text = text.strip()
    if not text:
        return text
    for match in _SENTENCE_BOUNDARY.finditer(text):
        candidate = text[:match.end()]
        last_token = candidate.split()[-1] if candidate.split() else ""
        if _looks_like_abbreviation(last_token):
            continue
        return candidate.strip()
    return text


def _bullet_text(scene: dict) -> str:
    title = (scene.get("title") or "").strip().rstrip(".!?")
    paragraphs = scene.get("paragraphs") or [""]
    sentence = _first_sentence(paragraphs[0] if paragraphs else "")
    return f"{title}. {sentence}".strip()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _scene_tags(scene: dict, findings_by_id: dict) -> set[str]:
    """Every finding's indicatorId + entity string cited by this scene,
    collected into one set for topicTag matching (rule 2)."""
    tags: set[str] = set()
    for fid in scene.get("claimFindingIds", []):
        finding = findings_by_id.get(fid)
        if finding is None:
            continue
        if finding.get("indicatorId"):
            tags.add(finding["indicatorId"])
        if finding.get("entity"):
            tags.add(finding["entity"])
    return tags


def _scene_indicator_ids(scene: dict, findings_by_id: dict) -> list[str]:
    """Indicator ids named by the scene's own cited findings, in
    first-seen order (deterministic, never reordered)."""
    seen: list[str] = []
    for fid in scene.get("claimFindingIds", []):
        finding = findings_by_id.get(fid)
        if finding is None:
            continue
        ind = finding.get("indicatorId")
        if ind and ind not in seen:
            seen.append(ind)
    return seen


def _point_from_row(row: dict) -> dict:
    label = row.get("label") or row.get("period", "")
    return {
        "label": str(label),
        "value": float(row["value"]),
        "hollow": False,
        "sourceUrl": (row.get("source") or {}).get("url"),
    }


def _outlet_from_url(url: str | None) -> str:
    """The publication a URL belongs to, derived from its own hostname --
    never the article headline. 'www.' is stripped so 'www.cnbc.com' and
    'cnbc.com' read as the same outlet."""
    if not url:
        return ""
    try:
        host = urlparse(url).netloc
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _chart_from_series(cs: ChartSeries, rows: list[dict]) -> dict:
    """Rule 2: a single registered, curated ChartSeries genuinely is one
    real source (e.g. AMD's own investor-relations page), so a single
    plain 'Source: <name>' attribution is honest here."""
    last = rows[-1]
    points = [_point_from_row(r) for r in rows[-_MAX_CHART_POINTS:]]
    source_ref = {
        "title": cs.name,
        "outlet": cs.sourceName,
        "url": cs.sourceUrl,
        "date": last.get("publishedAt"),
        "tier": "primary",
    }
    return {
        "form": cs.form,
        "title": cs.name,
        "caption": f"{cs.name}. Source: {cs.sourceName}.",
        "unit": cs.unit,
        "points": points,
        "source": source_ref,
    }


def _chart_from_fallback(title: str, plain_unit: str, rows: list[dict]) -> dict:
    """Rule 3: this history is stitched together across many separately
    reported events (different companies, different articles), so it is a
    synthesis, not one source -- the schema's assessment ref form is used
    instead of pretending one row's article is "the" source of the whole
    series (Critical 1 from review: drawing 10 points from 5 companies and
    then captioning the chart with whichever article happened to be the
    most recent row was misleading -- CNBC did not publish the series)."""
    chart_rows = rows[-_MAX_CHART_POINTS:]
    points = [_point_from_row(r) for r in chart_rows]

    based_on: list[dict] = []
    seen_urls: set[str] = set()
    for r in chart_rows:
        src = r.get("source") or {}
        url = src.get("url")
        if url is not None and url in seen_urls:
            continue
        if url is not None:
            seen_urls.add(url)
        headline = src.get("title") or ""
        # Round-2 review (MINOR): a headline is never an honest stand-in
        # for "outlet" -- that was the exact bug Important 4 fixed on the
        # normal path. When there's no url to derive a domain from, say so
        # plainly instead of quietly falling back to the headline again.
        based_on.append({
            "title": headline,
            "outlet": _outlet_from_url(url) or "Unknown outlet",
            "url": url,
            "date": r.get("publishedAt"),
            "tier": "secondary",
        })

    return {
        "form": "line",
        "title": title,
        "caption": f"{title}. Our assessment, based on the sources cited below.",
        "unit": plain_unit,
        "points": points,
        "source": assessment_ref(based_on),
    }


def _match_registered_series(tags: set[str], series_reg: dict[str, ChartSeries],
                              store_dir: str) -> dict | None:
    """Rule 2: a registered chart series matches if any of its topicTags
    is among the scene's tags, it's chartable (hard-fact, never estimate),
    and it has enough real (non-estimate) rows. Registry walked in id
    order so ties resolve deterministically.

    Row-level estimateGrade is filtered here too, not just the registry's
    quality flag: store/series/ has several other writers besides the
    chartdata fetch framework, and a series registered as hard-fact could
    still have an all-estimate file on disk today (review finding --
    `quality` is a claim about the series; `estimateGrade` is the ground
    truth about each row actually on disk, and the ground truth wins)."""
    for series_id in sorted(series_reg):
        cs = series_reg[series_id]
        if not cs.chartable:
            continue
        if not any(tag in cs.topicTags for tag in tags):
            continue
        rows = _read_jsonl(Path(store_dir) / f"{cs.id}.jsonl")
        real_rows = [r for r in rows if r.get("estimateGrade") is False]
        if len(real_rows) < _MIN_SERIES_POINTS:
            continue
        real_rows = sorted(real_rows, key=lambda r: r.get("period", ""))
        return _chart_from_series(cs, real_rows)
    return None


def _fallback_reason(indicator_ids: list[str], store_dir: str, *,
                      saw_non_measurable_unit: bool,
                      saw_missing_title: bool) -> str:
    """An honest, reader-facing explanation of exactly what's missing --
    never a technical/internal phrase like 'insufficient series density',
    and never a reason that's simply untrue of the case it's describing.

    Round-2 review (IMPORTANT, introduced by the round-1 fix): the two
    distinct honesty-gate failures inside `_match_fallback_history` used
    to share one message ("an internal analytical score"), which was a
    FALSE statement about a series that's a perfectly real, plain,
    measurable quantity (e.g. real USD revenue) that simply has no
    narrator-supplied title yet. They now get their own, separately true
    reasons -- `saw_non_measurable_unit` (the number itself isn't one we
    can name in plain English) is a different, and differently true,
    situation from `saw_missing_title` (we have a real measured number,
    just no plain-English name for it in the story yet).
    """
    if not indicator_ids:
        return ("No chart. This story isn't tied to a tracked number yet -- "
                "what's here is reported facts, not a running data series.")

    all_rows = [r for i in indicator_ids for r in _read_jsonl(Path(store_dir) / f"{i}.jsonl")]
    if not all_rows:
        return ("No chart. Nobody is tracking a number for this yet -- the "
                "reporting behind it is one-off, not a running series.")

    if all(r.get("estimateGrade") is not False for r in all_rows):
        return ("No chart. The only numbers here are our own estimates, not "
                "published facts, so we don't chart them.")

    if saw_non_measurable_unit:
        return ("No chart. We don't yet have a plain-English way to "
                "describe what this number measures, so we don't draw it.")

    if saw_missing_title:
        return ("No chart. We have real, tracked numbers behind this, but "
                "no plain-English name for what they measure yet, so we "
                "don't chart them.")

    return ("No chart. There isn't yet enough of a track record -- too few "
            "confirmed data points, or too narrow a span of time, to show a "
            "trend without being misleading.")


def _match_fallback_history(scene: dict, indicator_ids: list[str],
                             store_dir: str) -> tuple[dict | None, str | None]:
    """Rule 3: the scene's own findings' numeric history. Dense enough
    only if >= _MIN_FALLBACK_POINTS non-estimate points span
    >= _MIN_FALLBACK_MONTHS distinct months. On top of that density gate,
    two more honesty conditions both have to hold before anything is
    drawn (controller ruling from review, applying the design spec's
    honesty principle -- not a new design decision):

    - the row's raw unit must name a real, plain-English measurable
      quantity (see `_PLAIN_UNITS`) -- an internal composite score never
      qualifies, no matter how dense its history is;
    - the chart's title must come from the scene's own narrator copy
      (`visual.label`, when `visual.seriesId` names this indicator) --
      never a mechanically-derived label from a bare indicator id like
      "S9", which is meaningless to a reader.

    Either failing means this indicator can't be charted; the loop moves
    on to the scene's next cited indicator id, and only if none qualify
    do we fall to an honest `noChartReason` -- and (round-2 review) the
    two failure causes are tracked separately so the reason given is
    always true of the case it describes.
    """
    saw_non_measurable_unit = False
    saw_missing_title = False
    for indicator_id in indicator_ids:
        rows = _read_jsonl(Path(store_dir) / f"{indicator_id}.jsonl")
        real_rows = [r for r in rows if r.get("estimateGrade") is False]
        months = {r.get("period", "")[:7] for r in real_rows}
        if len(real_rows) < _MIN_FALLBACK_POINTS or len(months) < _MIN_FALLBACK_MONTHS:
            continue

        raw_unit = real_rows[-1].get("unit", "")
        plain_unit = _PLAIN_UNITS.get(raw_unit)
        if plain_unit is None:
            saw_non_measurable_unit = True
            continue

        visual = scene.get("visual") or {}
        plain_title = visual.get("label") if visual.get("seriesId") == indicator_id else None
        if not plain_title:
            saw_missing_title = True
            continue

        real_rows = sorted(real_rows, key=lambda r: r.get("period", ""))
        return _chart_from_fallback(plain_title, plain_unit, real_rows), None

    return None, _fallback_reason(indicator_ids, store_dir,
                                   saw_non_measurable_unit=saw_non_measurable_unit,
                                   saw_missing_title=saw_missing_title)


def build_bullets(story: dict, scorecard: dict, series_reg: dict[str, ChartSeries],
                   store_dir: str) -> list[dict]:
    """Exactly 3 bullets shaped for the dashboard schema's `bullets` array.

    Bullet text = scene title + first sentence of paragraphs[0], for the
    first 3 scenes whose title isn't "What to watch from here". Each
    bullet gets exactly one of `chart` (rule 2, else rule 3 fallback) or
    `noChartReason` -- never both, never neither.

    Raises ValueError if the story doesn't have at least 3 such scenes --
    the schema requires exactly 3 bullets, so a short story day must fail
    here, clearly, rather than silently ship a 1- or 2-bullet payload that
    only fails validation later with a confusing error.
    """
    findings_by_id = findings_index(scorecard)
    date = story.get("storyDate", "")
    story_href = f"story/{date}.html" if date else "story/"

    all_scenes = [s for s in story.get("scenes", [])
                  if (s.get("title") or "").strip() != _SKIP_SCENE_TITLE]
    if len(all_scenes) < _MAX_BULLETS:
        raise ValueError(
            f"build_bullets needs at least {_MAX_BULLETS} story scenes "
            f"(excluding {_SKIP_SCENE_TITLE!r}), found {len(all_scenes)}"
        )
    scenes = all_scenes[:_MAX_BULLETS]

    bullets = []
    for scene in scenes:
        tags = _scene_tags(scene, findings_by_id)
        indicator_ids = _scene_indicator_ids(scene, findings_by_id)

        chart = _match_registered_series(tags, series_reg, store_dir)
        no_chart_reason = None
        if chart is None:
            chart, no_chart_reason = _match_fallback_history(scene, indicator_ids, store_dir)

        bullets.append({
            "date": date,
            "text": _bullet_text(scene),
            "storyHref": story_href,
            "chart": chart,
            "noChartReason": no_chart_reason,
            "sources": refs_for_finding_ids(scene.get("claimFindingIds", []), findings_by_id),
        })
    return bullets
