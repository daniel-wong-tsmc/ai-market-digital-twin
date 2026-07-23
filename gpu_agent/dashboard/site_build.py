"""F95 site builder — emits the committed site/ folder Cloudflare Pages serves as-is."""
from __future__ import annotations

import datetime
from pathlib import Path

from .brief_render import BRIEF_CSS, DASHBOARD_CSS
from .site_model import build_site_model
from .site_render import (
    SITE_CSS, render_appendix, render_how_alert, render_how_featured,
    render_how_tile, render_index_redirect,
)
from .story_model import build_story_model
from .story_render import STORY_CSS, lint_story_copy, render_story_page


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build_site(category_id, store_dir, work_dir, plain_path, out_dir,
               price_fn=None, today=None):
    model = build_site_model(category_id, store_dir, work_dir, plain_path,
                             price_fn=price_fn)
    today = today or datetime.date.today()

    # Same store-layout detection build_site_model uses (store_dir either IS the
    # category dir or is the store root holding <category_id>/).
    store_root = Path(store_dir)
    if not (store_root / category_id).is_dir():
        store_root = store_root.parent
    story_model = build_story_model(category_id, store_root, today)
    index_html = render_story_page(story_model)
    story_lint = lint_story_copy(index_html)
    if story_lint:
        # F101 Phase A: the story-copy register gate — a lint failure must never
        # reach the deployed site (mirrors the retired brief-lint abort).
        raise ValueError(f"story copy lint failed: {story_lint}")

    out = Path(out_dir)
    cat = out / category_id
    pages = 0

    # F95 item 4: use the model's own human label (e.g. "Merchant-GPU Market") instead of
    # deriving one from the category id, which mangled it into "Merchant Gpu".
    label = model["category_label"]
    _write(out / "index.html",
           render_index_redirect(f"{category_id}/index.html", label))
    _write(out / "style.css", SITE_CSS + BRIEF_CSS + DASHBOARD_CSS + STORY_CSS)
    _write(cat / "style.css", SITE_CSS + BRIEF_CSS + DASHBOARD_CSS + STORY_CSS)
    _write(cat / "index.html", index_html); pages += 1
    _write(cat / "appendix.html", render_appendix(model)); pages += 1
    _write(cat / "how" / "alert.html", render_how_alert(model)); pages += 1
    for side in ("demand", "supply", "gap"):
        _write(cat / "how" / f"{side}.html", render_how_tile(model, side)); pages += 1
    featured = model.get("featured")
    if featured is not None:
        _write(cat / "how" / "featured.html", render_how_featured(model)); pages += 1

    return {"pages": pages + 1,   # +1 for the root redirect
            "out": str(out),
            "featured": featured["metric_id"] if featured else None,
            "story_lint": story_lint}
