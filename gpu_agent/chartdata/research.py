"""gpu_agent/chartdata/research.py -- F113 Task 3: the researcher's "ask" side.

A `CandidateSeries` is what a tool-USING research agent is asked to hand
back for one chartless dashboard bullet: a small, published, honestly
sourced numeric series that relates to that bullet's story. This module
only defines that shape and writes the per-bullet prompts asking for it --
it never fetches anything itself, and it never decides whether a returned
candidate is trustworthy (that is Task 4's deterministic verifier,
`gpu_agent/chartdata/verify.py`).

`registry/chart-series.json` (the human-curated registry) is only ever
READ here, via `build_bullets` -> `load_chart_series` -- this module adds
no writer to it, and never will (spec §8 / plan Task 7's grep proof).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator

from gpu_agent.chartdata.registry import load_chart_series
from gpu_agent.chartdata.research_prompt import build_research_prompt
from gpu_agent.dashboard.bullets import _MAX_BULLETS, _SKIP_SCENE_TITLE, build_bullets
from gpu_agent.dashboard.export_json import _latest_story
from gpu_agent.dashboard.gap_chart import monthly_best_files
from gpu_agent.dashboard.source_refs import findings_index

# A comparison pair (e.g. supply vs. demand) is a real, honest chart with
# only two points -- everything else needs at least this many published
# points before it reads as a trend rather than a guess.
_MIN_POINTS_NOT_PAIR = 3


class CandidatePoint(BaseModel):
    """One published, dated, sourced number on a candidate series -- never
    a value without the exact URL it came from (spec §3: "every point
    needs the URL it came from")."""
    model_config = ConfigDict(extra="forbid")

    label: str
    value: float
    sourceUrl: str
    publishedAt: str


class CandidateSeries(BaseModel):
    """What the research agent hands back for one bullet.

    `points` must have at least `_MIN_POINTS_NOT_PAIR` entries, UNLESS
    `pair=True` (the supply-vs-demand two-series comparison case spec §3
    calls out by name) -- enforced below, not left to the caller.

    `bulletIndex` (cross-task dependency, F113 plan self-review): the
    researcher itself never fills this in -- it doesn't know its own
    position in the day's bullet list. It is defined here, now, so
    Task 4's verifier can stamp it onto the quarantine record it writes
    (matching the `bullet-<n>-prompt.txt` / `bullet-<n>.json` numbering
    `emit_research` uses below) without ever needing to relax
    `extra="forbid"` later. Task 5 reads it back to match an accepted
    candidate to the bullet it was researched for.
    """
    model_config = ConfigDict(extra="forbid")

    seriesName: str
    unit: str
    form: str  # 'columns' | 'bars' | 'line'
    sourceName: str
    points: list[CandidatePoint]
    pair: bool = False
    notes: str = ""
    bulletIndex: Optional[int] = None

    @model_validator(mode="after")
    def _check_point_count(self) -> "CandidateSeries":
        if not self.pair and len(self.points) < _MIN_POINTS_NOT_PAIR:
            raise ValueError(
                f"CandidateSeries needs at least {_MIN_POINTS_NOT_PAIR} points "
                f"unless pair=True, got {len(self.points)}")
        return self


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _claim_finding_ids_per_bullet(story: dict) -> list[list[str]]:
    """Each bullet's own `claimFindingIds`, in the SAME order and via the
    SAME selection logic `build_bullets` uses (narrator-written `bullets`
    when there are exactly `_MAX_BULLETS` of them, else the mechanical
    scene-based fallback, skipping `_SKIP_SCENE_TITLE`) -- so the findings
    handed to the research prompt are exactly the ones a bullet is actually
    sourced from, never a different or re-derived set.

    `build_bullets` itself doesn't return `claimFindingIds` on its output
    bullets (they're consumed internally to build `sources`/`chart`), so
    this mirrors just that one piece of its selection, read-only, off the
    same `story` dict `emit_research` already has on hand."""
    artifact_bullets = story.get("bullets") or []
    if len(artifact_bullets) == _MAX_BULLETS:
        return [b.get("claimFindingIds") or [] for b in artifact_bullets]
    scenes = story.get("scenes", [])
    usable = [s for s in scenes if (s.get("title") or "").strip() != _SKIP_SCENE_TITLE]
    return [s.get("claimFindingIds", []) for s in usable[:_MAX_BULLETS]]


def _findings_for_bullet(claim_finding_ids: list[str], findings_by_id: dict[str, dict]) -> list[dict]:
    """Each finding cited by this bullet, reshaped to {statement, url} pairs
    for the research prompt.

    `statement` is the finding's own concrete numeric claim (e.g. "Intel
    Data Center and AI revenue was $5.1 billion in Q1 2026, up 22% year
    over year") -- the single most useful cue for what published series to
    go look for. An earlier version of this function built context from
    the bullet's already-resolved `sources` refs instead, whose `title` is
    only an ATTRIBUTION string (an outlet name or a synthesis label), never
    the claim itself -- that dropped the one thing the researcher most
    needs, so this reads the real `statement` field off the scorecard
    finding directly (round-2 review fix). The URL(s) it already carried
    are kept, now paired with the statement rather than standing alone --
    one prompt-context entry per evidence item, so a finding backed by
    several sources isn't collapsed down to just one link.

    A cited finding with no evidence at all still contributes its
    statement (url=None) rather than being dropped silently."""
    findings: list[dict] = []
    for fid in claim_finding_ids:
        finding = findings_by_id.get(fid)
        if finding is None:
            continue
        statement = finding.get("statement") or ""
        evidence = finding.get("evidence") or []
        if not evidence:
            findings.append({"statement": statement, "url": None})
            continue
        for ev in evidence:
            findings.append({"statement": statement, "url": ev.get("url")})
    return findings


def emit_research(category_id: str, store_dir: str, work_dir: str,
                  do_not_fetch_path=None) -> list[Path]:
    """Write one research prompt per CHARTLESS dashboard bullet for
    `category_id`'s latest cycle, to
    `<work_dir>/chart-research/bullet-<n>-prompt.txt` (1-indexed, matching
    the bullet's position in the day's 3-bullet list -- the SAME numbering
    the run-cycle skill's answer files (`bullet-<n>.json`) and Task 4's
    quarantine `bulletIndex` use). A bullet that already carries a chart
    gets no prompt at all -- the researcher is only dispatched where the
    honest matcher (`build_bullets`) came up empty.

    Returns the list of prompt file paths written, in bullet order.
    """
    store_root = Path(store_dir)
    cat_dir = store_root / category_id
    series_dir = store_root / "series"

    files = monthly_best_files(cat_dir)
    if not files:
        raise ValueError(f"no monthly scorecard history found for {category_id!r} under {cat_dir}")
    latest_raw = _load_json(files[max(files)])

    story = _latest_story(cat_dir / "story")
    series_reg = load_chart_series()
    bullets = build_bullets(story, latest_raw, series_reg, str(series_dir))

    findings_by_id = findings_index(latest_raw)
    claim_ids_per_bullet = _claim_finding_ids_per_bullet(story)

    out_dir = Path(work_dir) / "chart-research"
    paths: list[Path] = []
    for i, bullet in enumerate(bullets, start=1):
        if bullet.get("chart") is not None:
            continue
        claim_ids = claim_ids_per_bullet[i - 1] if i - 1 < len(claim_ids_per_bullet) else []
        findings = _findings_for_bullet(claim_ids, findings_by_id)
        prompt = build_research_prompt(bullet, findings,
                                       do_not_fetch_path=do_not_fetch_path)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"bullet-{i}-prompt.txt"
        path.write_text(prompt, encoding="utf-8")
        paths.append(path)
    return paths
