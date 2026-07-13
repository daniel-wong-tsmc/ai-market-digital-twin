"""F95 site builder — emits the committed site/ folder Cloudflare Pages serves as-is."""
from __future__ import annotations

from pathlib import Path

from .site_model import build_site_model
from .site_render import (
    SITE_CSS, render_appendix, render_category_page, render_how_alert,
    render_how_featured, render_how_tile, render_index_redirect,
)


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build_site(category_id, store_dir, work_dir, plain_path, out_dir, price_fn=None):
    model = build_site_model(category_id, store_dir, work_dir, plain_path,
                             price_fn=price_fn)
    out = Path(out_dir)
    cat = out / category_id
    pages = 0

    label = category_id.rsplit(".", 1)[-1].replace("-", " ").title()
    _write(out / "index.html",
           render_index_redirect(f"{category_id}/index.html", label))
    _write(out / "style.css", SITE_CSS)
    _write(cat / "style.css", SITE_CSS)
    _write(cat / "index.html", render_category_page(model)); pages += 1
    _write(cat / "appendix.html", render_appendix(model)); pages += 1
    _write(cat / "how" / "alert.html", render_how_alert(model)); pages += 1
    for side in ("demand", "supply", "gap"):
        _write(cat / "how" / f"{side}.html", render_how_tile(model, side)); pages += 1
    featured = model.get("featured")
    if featured is not None:
        _write(cat / "how" / "featured.html", render_how_featured(model)); pages += 1

    return {"pages": pages + 1,   # +1 for the root redirect
            "out": str(out),
            "featured": featured["metric_id"] if featured else None}
