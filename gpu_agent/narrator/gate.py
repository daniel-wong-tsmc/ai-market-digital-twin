"""gpu_agent/narrator/gate.py — deterministic quality gate for the daily narrator.

Phase B's brain is tool-less and unsupervised, so there is no scored eval bar
for its output. These six checks are the entire quality mechanism: a gate
that passes bad output silently ships a wrong story to a live,
executive-facing page. `gate_narrator` is pure (no I/O) and returns a list of
plain-sentence violations naming the offending value; an empty list is a
pass. Task 4's CLI verb refuses to write an artifact when the list is
non-empty and re-dispatches the brain once with these sentences appended, so
every message must be specific enough for a language model to fix itself
from.
"""
from __future__ import annotations

import html

from gpu_agent.dashboard.story_model import (ANCHORED_INDICATOR_ID,
                                             NO_SOURCE_LINE)
from gpu_agent.dashboard.story_render import lint_story_copy
from gpu_agent.narrator.schema import NarratorAnswer

_NO_SOURCE = NO_SOURCE_LINE
_FORWARD_MARKERS = ("close", "watch", "ahead", "next")


def gate_narrator(answer: NarratorAnswer, inputs: dict) -> list[str]:
    violations: list[str] = []

    for k in ("findings", "docPool", "seriesPool", "gapMonths"):
        if k not in inputs:
            violations.append(f"inputs is missing '{k}'")

    finding_ids = {f["id"] for f in inputs.get("findings", [])}
    doc_urls = {d["url"] for d in inputs.get("docPool", [])}
    series_ids = {s["indicatorId"] for s in inputs.get("seriesPool", [])}
    gap_months = set(inputs.get("gapMonths", []))

    # Check 2: claimFindingIds membership; sourceless scenes need exact wording.
    for scene in answer.scenes:
        for fid in scene.claimFindingIds:
            if fid not in finding_ids:
                violations.append(
                    f"scene {scene.n}: unknown finding id '{fid}' is not in "
                    f"inputs.findings")
        if not scene.claimFindingIds and scene.sourceLine != _NO_SOURCE:
            violations.append(
                f"scene {scene.n} has no claimed findings, so sourceLine must "
                f"be exactly '{_NO_SOURCE}' (got '{scene.sourceLine}')")

    # Check 3: relatedDocs.url membership.
    for scene in answer.scenes:
        for doc in scene.relatedDocs:
            url = doc.url
            if url not in doc_urls:
                violations.append(
                    f"scene {scene.n}: related doc url '{url}' is not in "
                    f"inputs.docPool")

    # Check 4: banned-word / style lint over all prose, reusing lint_story_copy.
    prose_bits = [answer.headline, answer.deck]
    for scene in answer.scenes:
        prose_bits.append(scene.title)
        prose_bits.extend(scene.paragraphs)
        prose_bits.append(scene.sourceLine)
    prose_bits.extend(k.whyCaption for k in answer.kpiPicks)
    prose_bits.extend(c.text for c in answer.calloutMonths)
    escaped_prose = [html.escape(bit) for bit in prose_bits]
    violations.extend(lint_story_copy("<p>" + " ".join(escaped_prose) + "</p>"))

    # Check 5: scene count/order bounds, forward-looking close, non-empty sourceLine.
    n_scenes = len(answer.scenes)
    if not (2 <= n_scenes <= 5):
        violations.append(
            f"story must have between 2 and 5 scenes; got {n_scenes}")
    scene_ns = [scene.n for scene in answer.scenes]
    if scene_ns != list(range(1, n_scenes + 1)):
        violations.append(
            f"scene n values must be 1..{n_scenes} contiguous; got {scene_ns}")
    if answer.scenes:
        last_title = answer.scenes[-1].title
        if not any(marker in last_title.lower() for marker in _FORWARD_MARKERS):
            violations.append(
                f"last scene title '{last_title}' must contain a "
                f"forward-looking marker (one of: "
                f"{', '.join(_FORWARD_MARKERS)})")
    for scene in answer.scenes:
        if not scene.sourceLine.strip():
            violations.append(f"scene {scene.n}: sourceLine must not be empty")

    # Check 6: kpiPicks/calloutMonths membership; kpiPicks scene uniqueness.
    kpi_scenes_seen: list[int] = []
    for kpi in answer.kpiPicks:
        if kpi.indicatorId == ANCHORED_INDICATOR_ID:
            violations.append(
                f"kpiPicks: indicatorId '{kpi.indicatorId}' is the anchored "
                f"indicator the page always shows on its own -- it must not "
                f"also be chosen as a kpi pick; pick from the other series "
                f"in inputs.seriesPool instead")
        if kpi.indicatorId not in series_ids:
            violations.append(
                f"kpiPicks: unknown indicatorId '{kpi.indicatorId}' is not "
                f"in inputs.seriesPool")
        if kpi.scene not in scene_ns:
            violations.append(
                f"kpiPicks: scene {kpi.scene} does not exist (scenes are "
                f"{scene_ns})")
        if kpi.scene in kpi_scenes_seen:
            violations.append(
                f"kpiPicks: scene {kpi.scene} is used by more than one pick; "
                f"scene values must be unique")
        kpi_scenes_seen.append(kpi.scene)
    for callout in answer.calloutMonths:
        if callout.monthKey not in gap_months:
            violations.append(
                f"calloutMonths: unknown monthKey '{callout.monthKey}' is "
                f"not in inputs.gapMonths")

    return violations
