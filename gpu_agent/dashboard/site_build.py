"""F95 site builder — emits the committed site/ folder Cloudflare Pages serves as-is."""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

from .brief_render import BRIEF_CSS, DASHBOARD_CSS
from .agenda import read_series
from .explore_model import (ENTITY_SERIES, entity_roles, load_entities,
                            load_findings, series_groups, split_by_side,
                            story_index, verdict_timeline)
from .export_json import write_dashboard_json
from .explore_render import (EXPLORE_CSS, check_links, render_entities_index,
                             render_entity_page, render_findings_page,
                             render_history_page, render_series_page,
                             render_story_day, render_story_index)
from .site_model import build_site_model
from .site_render import (
    SITE_CSS, render_appendix, render_how_alert, render_how_featured,
    render_how_tile, render_index_redirect,
)
from .story_model import build_story_model, read_story_artifact, resolve_store_root
from .story_render import STORY_CSS, lint_story_copy, render_story_page


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build_site(category_id, store_dir, work_dir, plain_path, out_dir,
               price_fn=None, today=None, require_category_page=False):
    """Emit the static site for `category_id` into `out_dir`.

    `require_category_page`: when true, the committed category page
    (`<out_dir>/<category_id>/index.html`, the compiled dashboard app) must
    already be on disk or the build fails. Every deep page links back to it, and
    the link gate can only resolve those links against a registered key -- so
    without this check a deleted category page would sail through the gate with
    every "back to today's story" link dead. The `site` CLI verb, the only
    caller that builds the real site, turns it on; builds into a scratch
    directory (tests) leave it off, since the committed page is an input they
    have no reason to stage."""
    model = build_site_model(category_id, store_dir, work_dir, plain_path,
                             price_fn=price_fn)
    today = today or datetime.date.today()

    # store_dir is the dashboard's own convention: the category's flat scorecard
    # directory OR the store root (resolve_store_root handles both, mirroring
    # build_story_model). The Explore layer reads findings/wiki/series from the
    # STORE ROOT and scorecards from <root>/<category_id>/.
    store_root = resolve_store_root(category_id, store_dir)
    cat_dir = store_root / category_id

    # --- F101c Explore-layer data assembly (pure reads) ------------------
    findings = load_findings(store_root)
    sides = split_by_side(findings)
    roles = entity_roles(findings)
    entities = load_entities(store_root)
    series_ids = [i for g in series_groups() for i in g["indicatorIds"]]
    series_ids += [i for ids in ENTITY_SERIES.values() for i in ids]
    series = read_series(store_root / "series", series_ids)
    timeline = verdict_timeline(cat_dir)
    story_entries = story_index(store_root, category_id)

    # Entity titles mentioned in scene prose become links to their dossier
    # (front page sits at <cat>/index.html, so dossiers are one dir down).
    entity_links = {e["title"]: f"entities/{e['slug']}.html" for e in entities}

    # story_model.build_story_model does its own store-layout detection now
    # (resolve_store_root, reused from there rather than re-implemented
    # here) -- see its docstring. Pass store_dir straight through.
    #
    # F110 Task 12: the category page is no longer this story page -- it is the
    # compiled React dashboard, a COMMITTED file at site/<category_id>/index.html
    # that this builder must never write over. The story copy itself still ships,
    # on the story permalinks below (render_story_day reuses story_render's own
    # scene renderer verbatim), so the copy-register gate stays exactly where it
    # was: it lints the assembled story page and aborts the whole build on a
    # violation, before a single file is written.
    story_model = build_story_model(category_id, store_dir, today)
    story_lint = lint_story_copy(render_story_page(story_model, entity_links))
    if story_lint:
        # F101 Phase A: the story-copy register gate — a lint failure must never
        # reach the deployed site (mirrors the retired brief-lint abort).
        raise ValueError(f"story copy lint failed: {story_lint}")

    out = Path(out_dir)
    cat = out / category_id
    pages = 0

    # Every emitted page (and stylesheet) keyed by its POSIX path relative to
    # `out`, for the link-integrity gate run at the end.
    page_map: dict[str, str] = {}

    def _emit(rel: str, text: str):
        _write(out / rel, text)
        page_map[rel] = text

    stylesheet = SITE_CSS + BRIEF_CSS + DASHBOARD_CSS + STORY_CSS + EXPLORE_CSS

    # F95 item 4: use the model's own human label (e.g. "Merchant-GPU Market") instead of
    # deriving one from the category id, which mangled it into "Merchant Gpu".
    label = model["category_label"]
    _emit("index.html",
          render_index_redirect(f"{category_id}/index.html", label))
    _emit("style.css", stylesheet)
    _emit(f"{category_id}/style.css", stylesheet)
    # The category page is a committed build input (the compiled React app), so
    # it is NOT written here. Register the path as a link-resolution target only
    # -- an empty value means "this exists", without pretending to scan a file
    # this builder did not produce. Every deep page links back to it.
    page_map.setdefault(f"{category_id}/index.html", "")
    if require_category_page and not (cat / "index.html").exists():
        raise ValueError(
            f"the committed category page {cat / 'index.html'} is missing -- "
            "every deep page's link back to today's reading would be dead. "
            "Rebuild it with `npm run build` in web/.")
    _emit(f"{category_id}/appendix.html", render_appendix(model)); pages += 1
    _emit(f"{category_id}/how/alert.html", render_how_alert(model)); pages += 1
    for side in ("demand", "supply", "gap"):
        _emit(f"{category_id}/how/{side}.html",
              render_how_tile(model, side)); pages += 1
    featured = model.get("featured")
    if featured is not None:
        _emit(f"{category_id}/how/featured.html",
              render_how_featured(model)); pages += 1

    # --- F101c Explore-layer pages ---------------------------------------
    explore_pages = 0

    _emit(f"{category_id}/story/index.html",
          render_story_index(story_entries)); explore_pages += 1
    for entry in story_entries:
        date = entry["date"]
        art = read_story_artifact(category_id, store_root, today, story_date=date)
        _emit(f"{category_id}/story/{date}.html",
              render_story_day(art, date)); explore_pages += 1

    _emit(f"{category_id}/findings/index.html",
          render_findings_page(findings, sides, today)); explore_pages += 1
    _emit(f"{category_id}/series/index.html",
          render_series_page(series, today)); explore_pages += 1
    _emit(f"{category_id}/entities/index.html",
          render_entities_index(entities, roles)); explore_pages += 1
    for e in entities:
        slug = e["slug"]
        # Cross-task interface note (Task 5): render_entity_page filters the
        # FULL findings list internally by entitySlug -- do NOT pre-filter.
        _emit(f"{category_id}/entities/{slug}.html",
              render_entity_page(e, roles.get(slug, ""), findings, series,
                                 today)); explore_pages += 1
    _emit(f"{category_id}/history.html",
          render_history_page(timeline, today)); explore_pages += 1

    # Directory-alias keys so the front page's directory routes (href="findings/"
    # etc.) resolve in the gate. Empty value: the key only needs to EXIST as a
    # resolution target -- the real index.html page is scanned under its own key,
    # and re-scanning it here (at the wrong directory depth) would misresolve its
    # own relative links.
    for d in ("story", "findings", "series", "entities"):
        page_map.setdefault(f"{category_id}/{d}", "")

    # --- F110 the one data file the category page reads ------------------
    # Belt and braces: the daily cycle already runs `dashboard-json` as its own
    # step, but a site build should never leave the page with no data to read.
    # A failure here must not stop the build (spec section 8) -- the live page
    # simply keeps yesterday's file, and the deep pages still ship.
    dashboard_json = None
    try:
        dashboard_json = str(write_dashboard_json(category_id, str(store_root),
                                                  str(out)))
    except Exception as e:  # noqa: BLE001 -- see comment above
        print(f"site build: dashboard data not written: {e}", file=sys.stderr)

    # --- Link-integrity gate over the whole emitted set ------------------
    violations = check_links(page_map)
    if violations:
        raise ValueError("dead internal links in emitted site:\n" +
                         "\n".join(violations))

    return {"pages": pages + 1,   # +1 for the root redirect
            "explore_pages": explore_pages,
            "dashboard_json": dashboard_json,
            "out": str(out),
            "featured": featured["metric_id"] if featured else None,
            "story_lint": story_lint}
