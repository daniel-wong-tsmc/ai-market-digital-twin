"""F110 Task 5: story bullets + honest chart matching.

Deterministic Python only -- no AI, no prompts, no model calls. Turns the
day's story scenes into exactly three dashboard bullets, and decides --
honestly -- whether each bullet may carry a small supporting chart.

The rule that matters more than any other: a small chart reads as an
established fact to an executive reader, so it may only appear when there
is real, defensible, non-estimate data behind it (>= the density
thresholds below). When nothing qualifies, the bullet gets a plain-English
``noChartReason`` explaining what's missing -- never a decorative or
forced chart.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from gpu_agent.chartdata.registry import ChartSeries
from gpu_agent.dashboard.source_refs import findings_index, refs_for_finding_ids

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

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def _first_sentence(text: str) -> str:
    """First sentence of `text` (up to and including its terminal
    punctuation); the whole (stripped) string if none is found.

    Splits only at a terminator immediately followed by whitespace, so a
    mid-number decimal point (e.g. "1.4 gigawatts") is never mistaken for
    a sentence end -- a naive "first '.' found" scan would cut "SpaceX
    ended the June quarter with 1.4 gigawatts..." off after "1."."""
    text = text.strip()
    if not text:
        return text
    return _SENTENCE_SPLIT.split(text, maxsplit=1)[0].strip()


def _bullet_text(scene: dict) -> str:
    title = (scene.get("title") or "").strip().rstrip(".")
    paragraphs = scene.get("paragraphs") or [""]
    sentence = _first_sentence(paragraphs[0] if paragraphs else "")
    return f"{title}. {sentence}".strip()


def _readable_indicator_name(indicator_id: str) -> str:
    """A generic, non-jargon fallback label for an indicator id with no
    registry entry backing it, e.g. 'hyperscalerCapexRevision' ->
    'Hyperscaler Capex Revision'. Never used for a registered ChartSeries
    (those carry their own reader-facing `name`)."""
    words = _WORD_BOUNDARY.sub(" ", indicator_id)
    return (words[:1].upper() + words[1:]) if words else indicator_id


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


def _chart_from_series(cs: ChartSeries, rows: list[dict]) -> dict:
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


def _chart_from_fallback(scene: dict, indicator_id: str, rows: list[dict]) -> dict:
    visual = scene.get("visual") or {}
    if visual.get("seriesId") == indicator_id and visual.get("label"):
        title = visual["label"]
    else:
        title = _readable_indicator_name(indicator_id)
    last = rows[-1]
    source_title = (last.get("source") or {}).get("title") or title
    points = [_point_from_row(r) for r in rows[-_MAX_CHART_POINTS:]]
    source_ref = {
        "title": source_title,
        "outlet": source_title,
        "url": (last.get("source") or {}).get("url"),
        "date": last.get("publishedAt"),
        "tier": "secondary",
    }
    return {
        "form": "line",
        "title": title,
        "caption": f"{title}. Source: {source_title}.",
        "unit": last.get("unit", ""),
        "points": points,
        "source": source_ref,
    }


def _match_registered_series(tags: set[str], series_reg: dict[str, ChartSeries],
                              store_dir: str) -> dict | None:
    """Rule 2: a registered chart series matches if any of its topicTags
    is among the scene's tags, it's chartable (hard-fact, never estimate),
    and its jsonl has enough points. Registry walked in id order so ties
    resolve deterministically."""
    for series_id in sorted(series_reg):
        cs = series_reg[series_id]
        if not cs.chartable:
            continue
        if not any(tag in cs.topicTags for tag in tags):
            continue
        rows = _read_jsonl(Path(store_dir) / f"{cs.id}.jsonl")
        if len(rows) < _MIN_SERIES_POINTS:
            continue
        rows = sorted(rows, key=lambda r: r.get("period", ""))
        return _chart_from_series(cs, rows)
    return None


def _fallback_reason(indicator_ids: list[str], store_dir: str) -> str:
    """An honest, reader-facing explanation of exactly what's missing --
    never a technical/internal phrase like 'insufficient series density'."""
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

    return ("No chart. There isn't yet enough of a track record -- too few "
            "confirmed data points, or too narrow a span of time, to show a "
            "trend without being misleading.")


def _match_fallback_history(scene: dict, indicator_ids: list[str],
                             store_dir: str) -> tuple[dict | None, str | None]:
    """Rule 3: the scene's own findings' numeric history. Dense enough
    only if >= _MIN_FALLBACK_POINTS non-estimate points span
    >= _MIN_FALLBACK_MONTHS distinct months; else an honest noChartReason."""
    for indicator_id in indicator_ids:
        rows = _read_jsonl(Path(store_dir) / f"{indicator_id}.jsonl")
        real_rows = [r for r in rows if r.get("estimateGrade") is False]
        months = {r.get("period", "")[:7] for r in real_rows}
        if len(real_rows) >= _MIN_FALLBACK_POINTS and len(months) >= _MIN_FALLBACK_MONTHS:
            real_rows = sorted(real_rows, key=lambda r: r.get("period", ""))
            return _chart_from_fallback(scene, indicator_id, real_rows), None

    return None, _fallback_reason(indicator_ids, store_dir)


def build_bullets(story: dict, scorecard: dict, series_reg: dict[str, ChartSeries],
                   store_dir: str) -> list[dict]:
    """Exactly 3 bullets shaped for the dashboard schema's `bullets` array.

    Bullet text = scene title + first sentence of paragraphs[0], for the
    first 3 scenes whose title isn't "What to watch from here". Each
    bullet gets exactly one of `chart` (rule 2, else rule 3 fallback) or
    `noChartReason` -- never both, never neither.
    """
    findings_by_id = findings_index(scorecard)
    date = story.get("storyDate", "")
    story_href = f"story/{date}.html" if date else "story/"

    scenes = [s for s in story.get("scenes", [])
              if (s.get("title") or "").strip() != _SKIP_SCENE_TITLE][:_MAX_BULLETS]

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
