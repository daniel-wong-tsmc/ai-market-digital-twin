"""F101c Phase C — shared scaffold + link-integrity gate for the Explore layer.

The Explore layer is the set of deep pages reached from inside the daily
story (story archive, findings browser, series, entity dossiers, verdict
history). Every one of those pages wraps its body in `page_scaffold` so it
gets the same "back to today's story" breadcrumb and the same one-line
reminder of which verdict it is backing up. `check_links` is the build-time
gate: it walks every emitted page's internal links and fails the build if
any of them point at a page that was never emitted.
"""
from __future__ import annotations

import posixpath
import re

from gpu_agent.freshness import AGING_THRESHOLD, FreshnessConfig, classify, load_freshness
from gpu_agent.freshness import weight as freshness_weight
from gpu_agent.reader import DIM_LABEL

from .explore_model import ENTITY_SERIES, SERIES_MEANING, markdown_to_html, series_groups
from .gap_chart import render_timeline_svg, spark_svg
from .render import esc
from .site_render import page
from .story_model import _CHIP_DEFS
from .story_render import (_scene_html, evidence_json, render_condense_script,
                            render_evidence_panel)

_HREF_RE = re.compile(r'href="([^"]+)"')

EXPLORE_CSS = """
.xp-crumb { margin: 0 0 .8rem; }
.xp-crumb a { text-decoration: none; }
.xp-tieback { color: var(--muted); font-size: .9rem; margin: 0 0 1.2rem; }
.xp-notice { font-style: italic; color: var(--muted); }
.xp-arch-row { border-bottom: 1px solid var(--line); padding: .5rem 0; }
.xp-arch-row .xp-fellback { color: var(--muted); font-style: italic; }
.xp-timeline { margin: 0 0 1rem; }
.xp-srcline { color: var(--muted); font-size: .85rem; }
.xp-dim-row { margin: .2rem 0; }
.xp-constraint { color: var(--muted); }
.xp-aging { opacity: .55; }
"""

_NO_NARRATED_ENTRY = ("No narrated entry this day — the page ran on "
                      "assembled data.")


def _rebase_explore(evidence: dict, prefix: str) -> dict:
    """Return a copy of the evidence blob with each entry's `explore` href
    prepended by `prefix`. story_model stores these hrefs CATEGORY-ROOT-RELATIVE
    (correct as-is on the front page at site/<cat>/index.html); a story permalink
    sits one directory below the category root (site/<cat>/story/<date>.html), so
    it re-bases them with "../" when it embeds the same blob. Absolute, external
    and fragment-only values are left untouched. Copies each touched entry (never
    mutates the shared model dict)."""
    out: dict = {}
    for k, v in evidence.items():
        exp = v.get("explore") if isinstance(v, dict) else None
        if exp and not exp.startswith(("http://", "https://", "/", "#", "..")):
            v = {**v, "explore": prefix + exp}
        out[k] = v
    return out


def render_story_day(artifact_model: dict | None, date: str) -> str:
    """A story-archive permalink page for one narrated day. `artifact_model`
    is the SAME dict shape `story_model.read_story_artifact` returns for
    that date (the caller reads it and passes it in; None covers both a
    missing artifact and one with `fellBack` set, since the reader already
    collapses those to the same value). Reuses `story_render._scene_html`
    verbatim -- see the front page's `render_story_page` -- so a scene reads
    byte-identical on the permalink and the front page."""
    if artifact_model is None:
        body = (f'<h1>{esc(date)}</h1>'
                f'<p class="xp-notice">{_NO_NARRATED_ENTRY}</p>')
        return page_scaffold(f"Story archive — {date}",
                             "what the front page said this day", body, depth=2)

    scenes = "".join(_scene_html(s) for s in artifact_model["scenes"])
    body = (f'<article class="st-page">'
            f'<header><p class="st-date">{esc(date)}</p>'
            f'<h1>{esc(artifact_model["headline"])}</h1>'
            f'<p class="st-deck">{esc(artifact_model["deck"])}</p></header>'
            f'{scenes}</article>'
            f'{evidence_json(_rebase_explore(artifact_model["evidence"], "../"))}'
            f'{render_evidence_panel()}{render_condense_script()}')
    return page_scaffold(f"Story archive — {date}: {artifact_model['headline']}",
                         artifact_model["headline"], body, depth=2)


def render_story_index(entries: list[dict]) -> str:
    """The story-archive landing page: one row per narrated day (newest
    first, per `explore_model.story_index`'s own ordering -- this function
    renders `entries` in the order it's given, it does not re-sort). A row
    whose `fellBack` is true links to a permalink that will render the
    fallback notice, so it's marked "(assembled)" up front."""
    rows = []
    for e in entries:
        marker = ' <span class="xp-fellback">(assembled)</span>' if e["fellBack"] else ""
        rows.append(f'<p class="xp-arch-row"><a href="{esc(e["date"])}.html">'
                    f'{esc(e["date"])}</a> — {esc(e["headline"])}{marker}</p>')
    body = f'<h1>Story archive</h1>{"".join(rows)}'
    return page_scaffold("Story archive", "every day this desk has narrated",
                         body, depth=2)


def page_scaffold(title: str, tieback: str, body: str, depth: int) -> str:
    """Wrap `body` with the shared explore chrome, then hand off to `site_render.page`.

    `depth` counts path segments below the category root: 1 = `<cat>/history.html`,
    2 = `<cat>/story/x.html`, etc. — it drives both the "back to today's story"
    link and (via `site_render.page`) the stylesheet's relative path.
    """
    up = "../" * (depth - 1)
    crumb = (f'<nav class="xp-crumb"><a href="{up}index.html">'
             "← today's story</a></nav>")
    tie = f'<p class="xp-tieback">Behind the verdict: {esc(tieback)}</p>'
    return page(title, f"{crumb}\n{tie}\n{body}", depth=depth)


_FIND_GROUPS = (
    ("demand", "Evidence demand is growing", ""),
    ("supply", "Evidence supply is (or isn't) catching up", ""),
    ("other", "Other signals", " xp-muted"),
)

# Self-contained filter: reads `#dim=...&entity=...&tier=...&since=...` off
# location.hash on load, seeds the select/date controls from it, then wires
# those controls (plus every later change) to toggle `hidden` on non-matching
# `.xp-find` cards and refresh the live count line. No fetch, no external
# refs -- the whole thing has to run from a static file on disk.
_FIND_SCRIPT = ("<script>(function(){"
    "var params={};"
    "(location.hash||'').replace(/^#/,'').split('&').forEach(function(pair){"
    "if(!pair)return;"
    "var kv=pair.split('=');"
    "var k=decodeURIComponent(kv[0]||'');"
    "var v=decodeURIComponent((kv[1]||'').replace(/\\+/g,' '));"
    "if(k)params[k]=v;"
    "});"
    "var dimSel=document.getElementById('xp-dim');"
    "var entSel=document.getElementById('xp-entity');"
    "var tierSel=document.getElementById('xp-tier');"
    "var dateInp=document.getElementById('xp-date');"
    "if(params.dim&&dimSel)dimSel.value=params.dim;"
    "if(params.entity&&entSel)entSel.value=params.entity;"
    "if(params.tier&&tierSel)tierSel.value=params.tier;"
    "if(params.since&&dateInp)dateInp.value=params.since;"
    "var cards=document.querySelectorAll('.xp-find');"
    "var countEl=document.getElementById('xp-count');"
    "function apply(){"
    "var dim=dimSel?dimSel.value:'';"
    "var ent=entSel?entSel.value:'';"
    "var tier=tierSel?tierSel.value:'';"
    "var since=dateInp?dateInp.value:'';"
    "var shown=0;"
    "cards.forEach(function(c){"
    "var ok=true;"
    "if(dim&&(c.dataset.dim||'').split(',').indexOf(dim)===-1)ok=false;"
    "if(ent&&c.dataset.entity!==ent)ok=false;"
    "if(tier&&c.dataset.tier!==tier)ok=false;"
    "if(since&&c.dataset.date&&c.dataset.date<since)ok=false;"
    "c.hidden=!ok;"
    "if(ok)shown++;"
    "});"
    "if(countEl)countEl.textContent='Showing '+shown+' of '+cards.length+' findings';"
    "}"
    "[dimSel,entSel,tierSel,dateInp].forEach(function(el){"
    "if(el)el.addEventListener('change',apply);"
    "});"
    "apply();"
    "})();</script>")


def _find_weight(f: dict, today, cfg: FreshnessConfig) -> float:
    """The freshness weight for one finding: date is `observedAt or asOf`,
    kind is classified off its first evidence entry's url (empty string when
    it has none) plus its indicatorId. Shared by `_find_card` (display) and
    `render_findings_page` (sort key) so the two never drift apart."""
    date = f.get("observedAt") or f.get("asOf") or ""
    evidence = f.get("evidence") or []
    first_url = (evidence[0].get("url", "") if evidence and isinstance(evidence[0], dict) else "")
    kind = classify(first_url, f.get("indicatorId"), cfg)
    return freshness_weight(date, today, kind, cfg)


def _find_card(f: dict, today, cfg: FreshnessConfig) -> str:
    """One `.xp-find` finding card, carrying all four filter data-*
    attributes so the inline script (and this module's own tests) never
    have to reach past the DOM to know what a card is about. Also carries
    the finding's freshness weight (`data-weight`) and, when that weight has
    decayed below AGING_THRESHOLD, an `xp-aging` class plus a visible
    "aging" chip."""
    targets = (f.get("impact") or {}).get("targets") or []
    dim = ",".join(str(t) for t in targets)
    entity = f.get("entitySlug") or ""
    evidence = f.get("evidence") or []
    tiers = {e.get("tier") for e in evidence if isinstance(e, dict)}
    tier = "primary" if "primary" in tiers else ("secondary" if "secondary" in tiers else "")
    date = f.get("observedAt") or f.get("asOf") or ""
    w = _find_weight(f, today, cfg)
    aging = w < AGING_THRESHOLD
    css_class = "xp-find xp-aging" if aging else "xp-find"
    aging_chip = '<span class="xp-tag xp-aging-chip">aging</span>' if aging else ""
    tags = "".join(f'<span class="xp-tag">{esc(t)}</span>' for t in targets)
    links = " ".join(
        f'<a href="{esc(e["url"])}" target="_blank" rel="noopener">{esc(e.get("source") or "source")}</a>'
        for e in evidence
        if isinstance(e, dict) and str(e.get("url") or "").startswith("https://"))
    return (f'<article class="{css_class}" data-dim="{esc(dim)}" data-entity="{esc(entity)}" '
            f'data-tier="{esc(tier)}" data-date="{esc(date)}" data-weight="{w}">'
            f'<p class="xp-stmt">{esc(f.get("statement") or "")}{aging_chip}</p>'
            f'<p class="xp-tags">{tags}</p>'
            f'<p class="xp-meta">{esc(f.get("entity") or "")} &middot; {esc(date)}</p>'
            f'<p class="xp-evidence">{links}</p>'
            f'</article>')


def render_findings_page(findings: list[dict], sides: dict[str, list[dict]], today) -> str:
    """The question-grouped findings browser: `sides` is `explore_model.
    split_by_side(findings)`'s own {"demand": [...], "supply": [...],
    "other": [...]} shape -- this function renders groups in that fixed
    order (demand, supply, then a muted "other" group). Within each group,
    findings are sorted (stable) descending by freshness weight -- freshest
    first -- so a decayed finding sinks toward the bottom of its own group
    rather than the whole page. `today` also bounds the date filter's `max`;
    it is never read from the clock here."""
    cfg = load_freshness()
    all_entities = sorted({f["entitySlug"] for f in findings if f.get("entitySlug")})
    all_dims = sorted({str(t) for f in findings
                       for t in (f.get("impact") or {}).get("targets") or []})

    def _options(values):
        return "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for v in values)

    sections = []
    for key, label, css in _FIND_GROUPS:
        group = sorted(sides.get(key, []),
                       key=lambda f: _find_weight(f, today, cfg), reverse=True)
        cards = "".join(_find_card(f, today, cfg) for f in group)
        sections.append(f'<section class="xp-group{css}"><h2>{esc(label)}</h2>{cards}</section>')

    filters = (
        '<div class="xp-filters">'
        '<label>Dimension <select id="xp-dim"><option value="">All</option>'
        f'{_options(all_dims)}</select></label>'
        '<label>Entity <select id="xp-entity"><option value="">All</option>'
        f'{_options(all_entities)}</select></label>'
        '<label>Tier <select id="xp-tier"><option value="">All</option>'
        '<option value="primary">Primary</option>'
        '<option value="secondary">Secondary</option></select></label>'
        f'<label>Since <input type="date" id="xp-date" max="{esc(today)}"></label>'
        '</div>')
    count = len(findings)
    count_line = f'<p class="xp-count" id="xp-count">Showing {count} of {count} findings</p>'

    body = (f'<h1>Findings</h1>{count_line}{filters}'
           f'{"".join(sections)}{_FIND_SCRIPT}')
    return page_scaffold("Findings", "every finding behind this category's verdict",
                         body, depth=2)


def _fmt_series_value(v) -> str:
    if isinstance(v, bool) or v is None:
        return ""
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int):
        return str(v)
    return str(v)


def _series_indicator_html(indicator_id: str, rows: list[dict]) -> str:
    """One indicator's block on the series page (and, reused as-is, an
    entity dossier's "owned series" block): anchor heading, full-history
    chart, latest value + unit, the story page's own plain-words chip
    description (when this indicator has one), the series' one-line
    meaning, and a deduped source table. An indicator with no rows yet
    renders a "no data yet" row instead of touching rows[-1] or charting
    an empty series -- it must never crash the page."""
    chip = _CHIP_DEFS.get(indicator_id)
    label = chip["label"] if chip else indicator_id
    heading = f'<h3 id="s-{esc(indicator_id)}">{esc(label)}</h3>'
    meaning = SERIES_MEANING.get(indicator_id, "")
    meaning_line = f'<p class="xp-meaning">{esc(meaning)}</p>' if meaning else ""

    if not rows:
        return (f'<section class="xp-series">{heading}{meaning_line}'
                f'<p class="xp-notice">No data yet.</p></section>')

    values = [r["value"] for r in rows if isinstance(r.get("value"), (int, float))]
    chart = spark_svg(values, 640, 120) if values else ""

    latest = rows[-1]
    unit = latest.get("unit") or ""
    value_line = (f'<p class="xp-latest">Latest: '
                 f'{esc(_fmt_series_value(latest.get("value")))} {esc(unit)}</p>')

    tip_line = f'<p class="xp-tip">{esc(chip["tip"])}</p>' if chip else ""

    seen = set()
    src_rows = []
    for r in rows:
        src = r.get("source") or {}
        title = src.get("title") or ""
        date = r.get("publishedAt") or r.get("date") or ""
        key = (title, date)
        if not title or key in seen:
            continue
        seen.add(key)
        src_rows.append(f"<tr><td>{esc(title)}</td><td>{esc(date)}</td></tr>")
    if not src_rows:
        src_rows = ['<tr><td colspan="2">No sources recorded.</td></tr>']
    table = (f'<table class="xp-sources"><thead><tr><th>Source</th>'
            f'<th>Date</th></tr></thead><tbody>{"".join(src_rows)}</tbody></table>')

    return (f'<section class="xp-series">{heading}{chart}{value_line}'
           f'{tip_line}{meaning_line}{table}</section>')


def render_series_page(series: dict, today) -> str:
    """One section per `series_groups()` entry, rendered in that fixed
    order; `series` maps indicatorId -> rows, and an indicator absent (or
    empty) in `series` still renders its heading and a "no data yet" row
    rather than being skipped or crashing."""
    sections = []
    for group in series_groups():
        items = "".join(_series_indicator_html(ind, series.get(ind) or [])
                        for ind in group["indicatorIds"])
        sections.append(f'<section class="xp-series-group">'
                        f'<h2>{esc(group["label"])}</h2>{items}</section>')
    body = f"<h1>Series</h1>{''.join(sections)}"
    return page_scaffold("Series", "the underlying numbers behind this category's verdict",
                         body, depth=2)


def render_entity_page(entity: dict, role: str, findings: list[dict],
                       series: dict, today) -> str:
    """An entity dossier: role line, the wiki page's own markdown body,
    any series this entity owns (`explore_model.ENTITY_SERIES`), and a
    "What we've observed" section of that entity's own findings, rendered
    with the same finding-card markup Task 4 uses (but with no filter
    script -- a single entity's findings never need client-side filtering)."""
    slug = entity.get("slug") or ""
    title = entity.get("title") or slug

    cfg = load_freshness()
    own_findings = [f for f in findings if f.get("entitySlug") == slug]
    own_findings = sorted(own_findings,
                          key=lambda f: _find_weight(f, today, cfg), reverse=True)
    cards = "".join(_find_card(f, today, cfg) for f in own_findings)
    if not cards:
        cards = '<p class="xp-notice">No findings recorded yet.</p>'

    charts = "".join(_series_indicator_html(ind, series.get(ind) or [])
                     for ind in ENTITY_SERIES.get(slug, []))

    body = (f'<h1>{esc(title)}</h1>'
           f'<p class="xp-role">{esc(role)}</p>'
           f'{markdown_to_html(entity.get("body_md") or "")}'
           f'{charts}'
           f'<section class="xp-observed"><h2>What we have observed</h2>{cards}</section>')
    return page_scaffold(title, f"{title} — {role}", body, depth=2)


_ROLE_TO_GROUP = {
    "where the supply bottleneck lives": "Supply chain",
    "a supply-side player": "Makers",
    "a demand driver": "Buyers",
}
_INDEX_GROUP_ORDER = ("Supply chain", "Buyers", "Makers", "Other")


def render_entities_index(entities: list[dict], roles: dict[str, str]) -> str:
    """Entities grouped by `explore_model.entity_roles`' own role strings:
    supply-bottleneck entities under "Supply chain", other supply-side
    players under "Makers", demand drivers under "Buyers", everything else
    (including any entity `roles` has no opinion on) under "Other"."""
    groups: dict[str, list[dict]] = {g: [] for g in _INDEX_GROUP_ORDER}
    for e in entities:
        role = roles.get(e.get("slug") or "", "")
        groups[_ROLE_TO_GROUP.get(role, "Other")].append(e)

    sections = []
    for label in _INDEX_GROUP_ORDER:
        ents = groups[label]
        if not ents:
            continue
        rows = "".join(
            f'<p class="xp-ent-row"><a href="{esc(e["slug"])}.html">{esc(e["title"])}</a></p>'
            for e in ents)
        sections.append(f'<section class="xp-ent-group"><h2>{esc(label)}</h2>{rows}</section>')
    body = f"<h1>Entities</h1>{''.join(sections)}"
    return page_scaffold("Entities", "who's involved in this category's story",
                         body, depth=2)


# Dimension ids -> plain-English display labels for the history page. Sourced
# from the canonical table (gpu_agent.reader.DIM_LABEL) with two deliberate
# overrides, so the four shared labels never drift: "momentum" (canonical
# "Momentum rating" would itself trip lint_story_copy's "momentum" ban) and
# "bottleneck" (canonical "Supply bottleneck"; kept as the shorter "Bottleneck"
# these pages have always shown). Both overrides are lint-safe.
_DIM_DISPLAY = {**DIM_LABEL, "momentum": "Demand pace", "bottleneck": "Bottleneck"}


def _month_details(month: dict) -> str:
    """One `<details id="m-<key>">` block: the month's rating/direction up
    front, then each dimension's own rating/direction, then the binding
    constraint that month landed on."""
    dims = month.get("dims") or {}
    dim_rows = "".join(
        f'<p class="xp-dim-row"><b>{esc(_DIM_DISPLAY.get(name, name))}:</b> '
        f'{esc(d.get("rating") or "")} ({esc(d.get("direction") or "")})</p>'
        for name, d in dims.items())
    constraint = month.get("constraint") or ""
    constraint_line = (f'<p class="xp-constraint">Binding constraint: '
                       f'{esc(constraint)}</p>' if constraint else "")
    summary = (f'{esc(month["label"])} — {esc(month.get("rating") or "")} '
              f'({esc(month.get("direction") or "")})')
    return (f'<details id="m-{esc(month["key"])}"><summary>{summary}</summary>'
           f'{dim_rows}{constraint_line}</details>')


def render_history_page(timeline: dict, today) -> str:
    """The verdict timeline: the gap chart over every month on record with
    each month's headline pinned to it, then one expandable `<details>` row
    per month carrying that month's dimension ratings/directions and its
    binding constraint. `today` is accepted for scaffold-signature parity
    with the other Explore pages; this page has no date-bounded control
    that needs it."""
    months = timeline.get("months") or []
    headlines = [m.get("headline") or "" for m in months]
    svg = render_timeline_svg(timeline.get("gap"), headlines)
    chart_section = (f'<section class="xp-timeline">{svg}'
                     f'<p class="xp-srcline">Source: agent-tracked orders and '
                     f'shipment data; company filings</p></section>' if svg else "")
    rows = "".join(_month_details(m) for m in months)
    body = (f'<h1>Verdict history</h1>{chart_section}{rows}'
           f'<p class="xp-appendix-link"><a href="appendix.html">'
           f'How this desk works</a></p>')
    return page_scaffold("Verdict history", "every month this category's verdict has landed on",
                         body, depth=1)


def check_links(pages: dict[str, str]) -> list[str]:
    """Report every internal href in `pages` whose target isn't a key of `pages`.

    `pages` maps emitted RELATIVE paths (e.g. "chips.merchant-gpu/findings/index.html")
    to their rendered HTML. Skips external links (http/https), fragment-only links
    (#...), and mailto: links. Targets are resolved relative to the linking page's
    own directory, with any #fragment or ?query stripped first. Empty list = pass.
    """
    errors: list[str] = []
    for src_page, html in pages.items():
        directory = posixpath.dirname(src_page)
        for href in _HREF_RE.findall(html):
            if href.startswith(("http://", "https://", "#", "mailto:")):
                continue
            target = href.split("#", 1)[0].split("?", 1)[0]
            if not target:
                continue
            resolved = posixpath.normpath(posixpath.join(directory, target))
            if resolved not in pages:
                errors.append(f"{src_page}: dead link to {href!r} (resolved {resolved})")
    return errors
