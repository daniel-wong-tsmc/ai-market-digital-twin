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
