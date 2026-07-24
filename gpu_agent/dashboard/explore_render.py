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

from .render import esc
from .site_render import page
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
"""

_NO_NARRATED_ENTRY = ("No narrated entry this day — the page ran on "
                      "assembled data.")


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
            f'{evidence_json(artifact_model["evidence"])}'
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


def _find_card(f: dict) -> str:
    """One `.xp-find` finding card, carrying all four filter data-*
    attributes so the inline script (and this module's own tests) never
    have to reach past the DOM to know what a card is about."""
    targets = (f.get("impact") or {}).get("targets") or []
    dim = ",".join(str(t) for t in targets)
    entity = f.get("entitySlug") or ""
    evidence = f.get("evidence") or []
    tiers = {e.get("tier") for e in evidence if isinstance(e, dict)}
    tier = "primary" if "primary" in tiers else ("secondary" if "secondary" in tiers else "")
    date = f.get("observedAt") or f.get("asOf") or ""
    tags = "".join(f'<span class="xp-tag">{esc(t)}</span>' for t in targets)
    links = " ".join(
        f'<a href="{esc(e["url"])}" target="_blank" rel="noopener">{esc(e.get("source") or "source")}</a>'
        for e in evidence
        if isinstance(e, dict) and str(e.get("url") or "").startswith("https://"))
    return (f'<article class="xp-find" data-dim="{esc(dim)}" data-entity="{esc(entity)}" '
            f'data-tier="{esc(tier)}" data-date="{esc(date)}">'
            f'<p class="xp-stmt">{esc(f.get("statement") or "")}</p>'
            f'<p class="xp-tags">{tags}</p>'
            f'<p class="xp-meta">{esc(f.get("entity") or "")} &middot; {esc(date)}</p>'
            f'<p class="xp-evidence">{links}</p>'
            f'</article>')


def render_findings_page(findings: list[dict], sides: dict[str, list[dict]], today) -> str:
    """The question-grouped findings browser: `sides` is `explore_model.
    split_by_side(findings)`'s own {"demand": [...], "supply": [...],
    "other": [...]} shape -- this function renders groups in that fixed
    order (demand, supply, then a muted "other" group) and does not re-sort
    within a group. `today` only bounds the date filter's `max`; it is never
    read from the clock here."""
    all_entities = sorted({f["entitySlug"] for f in findings if f.get("entitySlug")})
    all_dims = sorted({str(t) for f in findings
                       for t in (f.get("impact") or {}).get("targets") or []})

    def _options(values):
        return "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for v in values)

    sections = []
    for key, label, css in _FIND_GROUPS:
        cards = "".join(_find_card(f) for f in sides.get(key, []))
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
