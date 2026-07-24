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

_HREF_RE = re.compile(r'href="([^"]+)"')

EXPLORE_CSS = """
.xp-crumb { margin: 0 0 .8rem; }
.xp-crumb a { text-decoration: none; }
.xp-tieback { color: var(--muted); font-size: .9rem; margin: 0 0 1.2rem; }
"""


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
