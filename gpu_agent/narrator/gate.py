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
import re

from gpu_agent.dashboard.story_model import (ANCHORED_INDICATOR_ID,
                                             NO_SOURCE_LINE)
from gpu_agent.dashboard.story_render import lint_story_copy
from gpu_agent.narrator.schema import NarratorAnswer

_NO_SOURCE = NO_SOURCE_LINE
_FORWARD_MARKERS = ("close", "watch", "ahead", "next")

# Mirrors story_render.py's own pattern for the "index/indexed appears at
# most once" rule exactly (case-insensitive, same word boundaries), so the
# gate's count and the build-time page-level lint's count can never disagree
# on what counts as an occurrence.
_INDEX_WORD_RE = re.compile(r"\bindex(?:ed)?\b", re.I)


def gate_narrator(answer: NarratorAnswer, inputs: dict) -> list[str]:
    violations: list[str] = []

    for k in ("findings", "docPool", "seriesPool", "gapMonths"):
        if k not in inputs:
            violations.append(f"inputs is missing '{k}'")

    finding_ids = {f["id"] for f in inputs.get("findings", [])}
    doc_by_url = {d["url"]: d for d in inputs.get("docPool", [])}
    doc_urls = set(doc_by_url)
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

    # Check 3: relatedDocs.url membership, and (2b) outlet must match the
    # pooled doc's own `source` field for that url. `title` has no pooled
    # counterpart to check against (the gather blob contract carries no
    # `title` field -- it is inherently brain-authored) and is deliberately
    # left unvalidated here.
    for scene in answer.scenes:
        for doc in scene.relatedDocs:
            url = doc.url
            if url not in doc_urls:
                violations.append(
                    f"scene {scene.n}: related doc url '{url}' is not in "
                    f"inputs.docPool")
                continue
            pooled_source = doc_by_url[url].get("source", "")
            if doc.outlet != pooled_source:
                violations.append(
                    f"scene {scene.n}: related doc outlet '{doc.outlet}' for "
                    f"url '{url}' does not match its source in "
                    f"inputs.docPool ('{pooled_source}')")

    # Check 3b: scene.visual.seriesId must name a real series.
    for scene in answer.scenes:
        if scene.visual is not None and scene.visual.seriesId not in series_ids:
            violations.append(
                f"scene {scene.n}: visual seriesId '{scene.visual.seriesId}' "
                f"is not in inputs.seriesPool")

    # Check 4: banned-word / style lint over all prose, reusing lint_story_copy.
    # This must cover EXACTLY what story_render._scene_html later shows as
    # visible page text -- headline/deck/scene copy, chart labels, and
    # related-coverage titles/outlets alike -- so a gate pass can never leave
    # a banned word for build-time lint_story_copy to trip over.
    #
    # answer.headline is appended TWICE (not a typo): site_render.page()
    # renders it once in <title>Merchant GPU — {headline}</title> and
    # story_render._headline_block renders it again in <h1>{headline}</h1>,
    # so it is visible page text twice. The banned list's only count-based
    # rule ("index/indexed" appears at most once) must be checked against
    # that same two-occurrences-per-headline-index reality, or a headline
    # with exactly one "index" (which renders as two on the page) would
    # gate-pass and then crash the build-time lint. This only affects the
    # count-based rule -- boolean banned-word presence checks are unchanged
    # by a duplicate append.
    prose_bits = [answer.headline, answer.headline, answer.deck]
    for scene in answer.scenes:
        prose_bits.append(scene.title)
        prose_bits.extend(scene.paragraphs)
        prose_bits.append(scene.sourceLine)
        if scene.visual is not None:
            prose_bits.append(scene.visual.label)
        for doc in scene.relatedDocs:
            prose_bits.append(doc.title)
            prose_bits.append(doc.outlet)
            # doc.date is brain-authored freeform text (the schema places no
            # validation on it) and story_render._scene_html renders it as
            # visible page text in the "outlet · title · date" related-
            # coverage link, so it must be swept like title/outlet or a
            # banned word here would gate-pass and crash the build-time
            # lint.
            prose_bits.append(doc.date)
    prose_bits.extend(k.whyCaption for k in answer.kpiPicks)
    prose_bits.extend(c.text for c in answer.calloutMonths)
    escaped_prose = [html.escape(bit) for bit in prose_bits]
    joined_prose = " ".join(escaped_prose)
    violations.extend(lint_story_copy("<p>" + joined_prose + "</p>"))

    # Check 4b: chrome-aware index/indexed budget. gap_chart.py renders a
    # fixed axis label containing "indexed" whenever gapMonths is non-empty
    # (gpu_agent/dashboard/gap_chart.py's "orders vs. chips shipped, indexed"
    # text), and story_render.lint_story_copy's count-based rule scans the
    # WHOLE rendered page, not just narrator prose. That fixed chrome
    # occurrence is invisible to the lint_story_copy(prose_bits) call above,
    # which only ever sees narrator-authored text. So when a gap chart WILL
    # render, the page's single index/indexed budget is already spent by the
    # chart's own axis label, and the narrator's share of that budget is
    # zero -- any index/indexed in narrator prose would push the page-level
    # count to 2 and crash site_build.build_site's lint at build time. We key
    # this off gapMonths being non-empty (the actual rendering condition)
    # rather than hardcoding "narrator budget = page budget - 1": that way the
    # narrator can never ADD an occurrence on top of chrome that has already
    # spent the budget, and the rule keeps working even if the exact axis
    # wording in gap_chart.py changes later. When gapMonths is empty, no gap
    # chart renders, there is no fixed chrome occurrence, and the existing
    # lint_story_copy-over-prose_bits "at most once" rule above is already
    # the correct (and only) check.
    if gap_months and _INDEX_WORD_RE.search(joined_prose):
        violations.append(
            "narrator prose contains 'index'/'indexed', but a gap chart will "
            "render (inputs.gapMonths is non-empty) and its fixed axis label "
            "already uses the page's one allowed 'index/indexed' occurrence "
            "-- narrator prose must contain zero occurrences of "
            "'index'/'indexed' whenever a gap chart renders")

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
    n_callouts = len(answer.calloutMonths)
    if n_callouts > 2:
        violations.append(
            f"calloutMonths: at most 2 callouts are allowed; got {n_callouts}")
    for callout in answer.calloutMonths:
        if callout.monthKey not in gap_months:
            violations.append(
                f"calloutMonths: unknown monthKey '{callout.monthKey}' is "
                f"not in inputs.gapMonths")
        if callout.scene not in scene_ns:
            violations.append(
                f"calloutMonths: scene {callout.scene} does not exist "
                f"(scenes are {scene_ns})")

    return violations
