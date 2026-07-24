"""F101 Phase A: assemble the narrative-page model from committed store data.

The returned dict's shape doubles as the Phase-B narrator artifact
contract: Phase B replaces this assembler with a reader of
store/<cat>/story/<date>.json, and the renderer must not notice.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from gpu_agent.dashboard.agenda import read_series
from gpu_agent.dashboard.brief_model import (first_n_sentences,
                                             latest_monthly,
                                             read_implication_lines)
from gpu_agent.dashboard.gap_chart import build_gap_data
from gpu_agent.dashboard.glossary import load_glossary, term_swap
from gpu_agent.narrator.store import StoryStore

_SERIES_IDS = ["gpuRentalOnDemand", "hyperscalerCapexRevision",
               "odmMonthlyAiRevenue", "hbmSupplyCapex", "gpuSpotPrice"]

# The renderer always shows this series as the anchored KPI chip (see
# `_base_model` below), so it must never also appear as a narrator kpiPick --
# that would render the same chip twice. `_SERIES_IDS[0]` is the one place
# that decision already lives (`_base_model`'s `anchored = _chip(...)` call
# and its `picks` loop over `_SERIES_IDS[1:]`); every other spot that needs
# "the anchored indicator's id" (the gate, the prompt, the narrated-path
# mapper) imports this constant instead of repeating the string literal.
ANCHORED_INDICATOR_ID = _SERIES_IDS[0]

# The exact sourceLine wording a sourceless scene (empty claimFindingIds)
# must carry. `gate.py` enforces this at write time so the brain can never
# ship a scene that claims nothing but writes a source line anyway; the
# narrated-path mapper below enforces it again at render time so a
# hand-edited or legacy artifact that slipped past (or predates) the gate
# still can't render a fabricated source line verbatim. One literal, shared
# by both enforcement points.
NO_SOURCE_LINE = "No new sourced evidence today."

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


# A translation can leave a stutter behind: glossary.json's "CoWoS" ->
# "advanced chip packaging" already ends in "packaging", and the stored text
# right after it ("CoWoS packaging and HBM supply") also starts with
# "packaging" -- so the swap produces "advanced chip packaging packaging".
# The same shape of bug can happen with any replacement whose first/last
# word matches the stored word immediately before/after it. Collapse it
# after translation, everywhere translated text reaches the page.
#
# Bounded per final review: collapsing ANY adjacent duplicate word also
# rewrites legitimate English ("had had" -> "had"). The bound only fires
# when the repeated word is the first or last word of one of the
# translation table's own replacement values -- that provably covers every
# stutter a translation swap can create (the swap can only ever strand its
# own first/last word against the stored text on either side of it). This
# does NOT by itself guarantee "had had" or "that that" survive -- that
# depends on "had"/"that" never being a boundary word, which is asserted
# separately by test_translation_boundary_words_exclude_common_english
# rather than claimed here as a property of the regex.
#
# The (?<![\w-]) / (?![\w-]) lookarounds (rather than \b) additionally keep
# the match from reaching into a hyphenated compound: \b alone treats the
# hyphen in "chip-level" as a word boundary, so "chip chip-level" would
# match on "chip" and silently delete it. Requiring a non-word/non-hyphen
# character (or start/end of string) on both sides of the whole match means
# the repeated word must stand alone, not lead into a hyphenated compound.
_REPEATED_WORD = re.compile(r"(?<![\w-])(\w+)[ \t]+\1(?![\w-])", re.IGNORECASE)


def _translation_boundary_words(gl: dict) -> set[str]:
    """The first and last word (lowercased) of every replacement value in
    the translation table -- the only words a translation swap can ever
    leave stuttering against the stored text immediately before/after it."""
    words: set[str] = set()
    for repl in (gl.get("prose_terms") or {}).values():
        parts = str(repl).split()
        if parts:
            words.add(parts[0].lower())
            words.add(parts[-1].lower())
    return words


def _collapse_repeated_word(text: str, boundary_words: set[str]) -> str:
    """Collapse an immediately-repeated word (case-insensitive match,
    whitespace-only separator), keeping the first occurrence's casing --
    but only when that word is a translation boundary word (see above).
    Repeats split by punctuation or another word (e.g. "that, that"), and
    any bare repeated word that isn't a boundary word (e.g. a genuine
    "had had"), are left untouched."""
    if not text:
        return text

    def _repl(m: re.Match) -> str:
        word = m.group(1)
        if word.lower() in boundary_words:
            return word
        return m.group(0)

    return _REPEATED_WORD.sub(_repl, text)


def _translate(text: str, gl: dict) -> str:
    """term_swap() plus the bounded stutter cleanup above, in one call.
    Every place in this module that renders stored text onto the story page
    should call this instead of term_swap() directly."""
    return _collapse_repeated_word(term_swap(text, gl), _translation_boundary_words(gl))


def _truncate(text: str, limit: int) -> str:
    """Truncate to at most `limit` characters, breaking on a word boundary
    and adding a trailing ellipsis rather than cutting mid-word. Callers
    MUST translate the text first -- translating after truncation can
    expand a jargon word into a longer plain-English phrase and blow the
    length budget (real case: a 60-char cap on the untranslated text
    produced an 81-char rendered line, cut mid-word)."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sp = cut.rfind(" ")
    if sp > 0:
        cut = cut[:sp]
    return cut.rstrip() + "…"

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
        # The value text above is categorical (words, not a number), but the
        # arrow (see _arrow()) compares the raw numbers behind the last two
        # readings -- a smaller-but-still-positive revision reads "raised
        # again" with a down arrow next to it, which contradicts itself.
        # Suppress the arrow for any chip whose value text is categorical.
        "categorical": True,
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
    arrow = "" if d.get("categorical") else _arrow(rows)
    return {"claim": f"kpi:{ind}", "label": d["label"],
            "value": d["fmt"](rows[-1]["value"]), "arrow": arrow,
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
        take_raw = r.get("note") or r.get("label") or "latest reading"
        out.append({"source": _translate(src.get("title", "source"), gl),
                    "date": r.get("publishedAt", ""),
                    "take": _truncate(_translate(take_raw, gl), 90), "url": key})
        if len(out) == 3:
            break
    return out


def resolve_store_root(category_id: str, store_dir: str | Path) -> Path:
    """Store-layout detection: `store_dir` either IS the store root (holding
    a <category_id>/ subdir alongside series/, findings/, wiki/) or IS the
    category directory itself (whose parent is the store root). Both shapes
    are real invocations (the CLI's own established convention passes the
    category directory; some callers pass the store root directly) and must
    resolve to the same store root either way. Mirrors build.py's and
    site_model.py's own detection (build.py:57-59) -- this is the one place
    it lives for the story page, so every caller of build_story_model gets
    it for free instead of having to pre-resolve store_dir themselves."""
    store_dir = Path(store_dir)
    if (store_dir / category_id).is_dir():
        return store_dir
    return store_dir.parent


def _base_model(category_id: str, store_root: Path, today: dt.date):
    """The shared tail of `build_story_model`: everything that comes from
    committed store data regardless of whether an artifact or the assembler
    ends up supplying headline/deck/scenes/kpis.picks/callouts. Both
    `_assemble_model` (Phase A, no artifact) and `read_story_artifact`
    (Phase B, narrated) call this and build on top of it, so gap chart,
    archive, explore, the anchored KPI chip, and the series-backed evidence
    entries are computed identically -- and only once -- either way.

    Returns `(model, ctx)`: `model` already carries the exact keys the final
    dict needs from the shared tail (category_id, as_of, revision, dateline,
    gap, kpis, evidence, archive, explore); `ctx` carries the raw
    ingredients (`latest`, `gl`, `series`, `cat_dir`) that the two callers
    still need to build their own headline/deck/scenes/callouts. (Both
    callers already have `store_root` as their own function parameter, so
    it is not duplicated into `ctx`.)
    """
    cat_dir = store_root / category_id
    latest, _prior, as_of, rev = latest_monthly(cat_dir)
    latest = latest or {}
    gl = _story_glossary(load_glossary())
    gap = build_gap_data(cat_dir)
    dateline = (today.strftime("%A, %B %d, %Y").replace(" 0", " ")
                + " · updated with each run")

    series = read_series(store_root / "series", _SERIES_IDS)
    evidence: dict[str, dict] = {}
    anchored = _chip(ANCHORED_INDICATOR_ID, series.get(ANCHORED_INDICATOR_ID, []))
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

    explore = {
        "entities": len(list((store_root / "wiki" / "entity").glob("*.md"))),
        "findings": len(list((store_root / "findings").glob("*.json"))),
        "series": len(list((store_root / "series").glob("*.jsonl"))),
        "history": len(list(cat_dir.glob("*.json")))}

    model = {"category_id": category_id, "as_of": as_of, "revision": rev,
             "dateline": dateline, "gap": gap,
             "kpis": {"anchored": anchored, "picks": picks},
             "evidence": evidence, "archive": arch, "explore": explore}
    ctx = {"latest": latest, "gl": gl, "series": series, "cat_dir": cat_dir}
    return model, ctx


def _assemble_model(category_id: str, store_root: Path, today: dt.date) -> dict:
    """Phase A: the original assembler, now built on the shared `_base_model`
    tail. Behaviorally unchanged from the pre-Phase-B assembler -- only the
    gap/archive/explore/anchored-chip/evidence-series computation moved into
    `_base_model` so the artifact-driven path can reuse it verbatim."""
    base, ctx = _base_model(category_id, store_root, today)
    latest, gl = ctx["latest"], ctx["gl"]
    series = ctx["series"]
    status = latest.get("categoryStatus") or {}

    headline = _HEADLINES.get((base["gap"] or {}).get("gap_word"),
                              "The state of the GPU market.")
    label = _translate(status.get("constraintLabel") or "supply of key components", gl)
    reason = first_n_sentences(_translate(status.get("reason") or "", gl), 1)
    deck = f"The main chokepoint is {label}. {reason}".strip()

    model = {**base, "headline": headline, "deck": deck, "callouts": [],
             "scenes": []}
    _add_scenes(model, latest, store_root, series, gl)
    return model


def read_story_artifact(category_id: str, store_root: Path,
                        today: dt.date) -> dict | None:
    """Phase B: load today's narrator artifact and map it onto the exact
    model dict shape `_assemble_model` produces. Returns None when there is
    no artifact for the date, or when the artifact has `fellBack` set --
    either way the caller must fall back to the assembler, indistinguishable
    from Phase A behavior."""
    art = StoryStore(store_root).read(category_id, today.isoformat())
    if art is None or art.narratorMeta.fellBack:
        return None

    base, ctx = _base_model(category_id, store_root, today)
    latest, gl, series = ctx["latest"], ctx["gl"], ctx["series"]

    scenes = []
    evidence = dict(base["evidence"])
    for sc in art.scenes:
        vals = ([r["value"] for r in series.get(sc.visual.seriesId, [])[-8:]]
                if sc.visual else [])
        vlabel = sc.visual.label if sc.visual else ""
        findings = _resolve_findings(latest, sc.claimFindingIds)
        # Reuse the assembler's own scene-dict shape instead of hand-rebuilding
        # it here, then override the two fields the artifact actually supplies
        # (`_mk_scene` would otherwise derive them from `findings`/`gl`, which
        # is the assembler's job, not the narrated path's).
        scene_dict = _mk_scene(sc.n, sc.title, sc.paragraphs, vals, vlabel,
                               findings, gl)
        # An empty claimFindingIds list means "nothing sourced today" -- the
        # mapper substitutes the exact required wording itself rather than
        # trusting the artifact's own sourceLine, so a hand-edited or legacy
        # artifact can never render a fabricated source line for a claim it
        # didn't actually make (gate.py enforces the same rule at write time;
        # this is the read-time backstop the plan's consistency note calls for).
        scene_dict["source_line"] = (sc.sourceLine if sc.claimFindingIds
                                     else NO_SOURCE_LINE)
        scene_dict["related"] = [{"outlet": r.outlet, "title": r.title,
                                  "date": r.date, "url": r.url}
                                 for r in sc.relatedDocs]
        scenes.append(scene_dict)
        evidence[f"scene:{sc.n}"] = {
            "title": f"{sc.title} — says who?",
            # Same filtered paragraph list `_mk_scene` used for `scene_dict`
            # above (empty-string paragraphs dropped), so the evidence panel
            # can never show blank claim text while the scene itself renders.
            "claim_text": (scene_dict["paragraphs"][0]
                           if scene_dict["paragraphs"] else ""),
            # Same rule as the assembler (Phase A review finding #1): a
            # scene with no claimFindingIds of its own gets an honest empty
            # findings list -- never borrowed from another scene/claim.
            "findings": _finding_rows(findings, gl),
            "series": vals, "explore": "appendix.html"}

    picks = []
    for kp in art.kpiPicks:
        # The renderer always shows the anchored indicator as its own chip
        # (see `_base_model` above); a kpiPick naming that same indicator
        # would render it a second time. `gate.py` already rejects this at
        # write time, but a hand-edited or legacy artifact could still slip
        # one through, so skip it here too -- mirrors the assembler's own
        # structural exclusion (`_SERIES_IDS[1:]` in `_base_model`).
        if kp.indicatorId == ANCHORED_INDICATOR_ID:
            continue
        c = _chip(kp.indicatorId, series.get(kp.indicatorId, []))
        if c is None:
            continue
        c["caption"] = kp.whyCaption
        c["scene"] = kp.scene
        picks.append(c)

    callouts = [{"month_key": cm.monthKey, "text": cm.text,
                "claim": f"scene:{cm.scene}"} for cm in art.calloutMonths]

    return {**base, "headline": art.headline, "deck": art.deck,
            "scenes": scenes, "callouts": callouts, "evidence": evidence,
            "kpis": {"anchored": base["kpis"]["anchored"], "picks": picks}}


def build_story_model(category_id: str, store_dir: str | Path,
                      today: dt.date) -> dict:
    store_root = resolve_store_root(category_id, store_dir)
    artifact_model = read_story_artifact(category_id, store_root, today)
    if artifact_model is not None:
        return artifact_model
    return _assemble_model(category_id, store_root, today)


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
            rows.append({"source": _translate(e.get("source", "source"), gl),
                        "date": e.get("date", ""),
                        "take": _truncate(
                            _translate(f.get("statement") or "", gl), 90),
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
            title_raw = e.get("excerpt") or f.get("statement") or ""
            out.append({"outlet": _translate(e.get("source", ""), gl),
                        "title": _truncate(_translate(title_raw, gl), 60),
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
    return "Source: " + _translate(
        "; ".join(names[:3]) if names else "agent-tracked filings and reporting", gl)


def _mk_scene(n, title, paragraphs, series_vals, series_label, findings, gl):
    return {"n": n, "accent": _ACCENTS[(n - 1) % 4], "title": title,
            "paragraphs": [p for p in paragraphs if p],
            "visual": {"kind": "spark", "series": series_vals,
                       "label": series_label},
            "source_line": _source_line(findings, gl),
            "related": _related(findings, gl),
            "claims": [f"scene:{n}"]}


def _add_scenes(model, latest, store_root, series, gl):
    dims = latest.get("dimensionRatings") or {}
    status = latest.get("categoryStatus") or {}
    sv = lambda ind: [r["value"] for r in series.get(ind, [])[-8:]]
    plain = lambda t, n=2: first_n_sentences(_translate(t or "", gl), n)

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
            # No fallback: a scene with no findings of its own must show an
            # honest empty state (see story_render's evidence panel), never
            # borrow another claim's sources -- attributing a claim to a
            # source that never made it defeats the page's whole "says who?"
            # promise.
            "findings": _finding_rows(finds, gl),
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
    # Archive and explore are computed once by `_base_model` (the shared
    # tail both the assembler and the artifact-driven path build on) --
    # `model["archive"]`/`model["explore"]` already carry those values from
    # there and are not recomputed here.
