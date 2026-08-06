"""F110 Task 12: the category page is now the compiled React app.

`build_site` must stop writing the old story markup over `<cat>/index.html`
(that file is a COMMITTED build input now, not a generated output), must make
sure `<cat>/data/dashboard.json` is there, and must keep emitting every deep
page exactly as before. The last point is the dangerous one: the compiled app
builds into the same directory the deep pages live in, so a mistake here
silently deletes a large part of a live site.
"""
import datetime as dt
import json
import re
from pathlib import Path

import jsonschema
import pytest

from gpu_agent.dashboard.site_build import build_site
from tests.test_export_json import _make_store

CAT = "chips.merchant-gpu"
SCHEMA = json.loads(Path("web/schema/dashboard.schema.json").read_text(encoding="utf-8"))

# What the committed React page looks like on disk before a build runs: a
# stand-in for the real compiled index.html, distinctive enough that any
# overwrite is unmistakable.
REACT_SHELL = ('<!DOCTYPE html><html><head><title>t</title></head>'
               '<body><div id="root"></div>'
               '<script type="module" src="./assets/app-abc123.js"></script>'
               '</body></html>')


def _build(tmp_path, *, place_shell=True, require_category_page=False):
    store = _make_store(tmp_path)
    out = tmp_path / "site"
    if place_shell:
        (out / CAT).mkdir(parents=True, exist_ok=True)
        (out / CAT / "index.html").write_text(REACT_SHELL, encoding="utf-8")
    # build_site's own convention: the category's flat scorecard dir (it
    # resolves the store root itself, exactly as build_story_model does).
    build_site(CAT, str(store / CAT), "work-nonexistent", None, str(out),
               price_fn=lambda d: {}, today=dt.date(2026, 8, 5),
               require_category_page=require_category_page)
    return out


def test_dashboard_json_is_written_and_valid(tmp_path):
    out = _build(tmp_path)
    data_path = out / CAT / "data" / "dashboard.json"
    assert data_path.exists(), "the page's one data file was not written"
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    jsonschema.validate(payload, SCHEMA)
    assert payload["categoryId"] == CAT


def test_committed_react_index_is_left_untouched(tmp_path):
    out = _build(tmp_path)
    index = (out / CAT / "index.html").read_text(encoding="utf-8")
    assert index == REACT_SHELL, "build_site overwrote the committed React page"


def test_old_story_markup_is_gone_from_the_category_page(tmp_path):
    out = _build(tmp_path, place_shell=False)
    index_path = out / CAT / "index.html"
    text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    for marker in ('class="st-head"', 'class="st-scene', 'id="ev-data"'):
        assert marker not in text, f"old story markup still emitted: {marker}"


def test_deep_pages_are_still_emitted(tmp_path):
    out = _build(tmp_path)
    for rel in ("findings/index.html", "series/index.html", "story/index.html",
                "entities/index.html", "history.html", "appendix.html",
                "how/alert.html", "style.css"):
        assert (out / CAT / rel).exists(), f"deep page lost: {rel}"


def test_build_does_not_delete_anything_already_in_the_output_dir(tmp_path):
    """The compiled app and the Python renderer share one output directory.
    Nothing either side wrote may vanish when the other runs."""
    out = tmp_path / "site"
    (out / CAT / "assets").mkdir(parents=True)
    (out / CAT / "assets" / "app-abc123.js").write_text("//x", encoding="utf-8")
    (out / CAT / "findings").mkdir(parents=True, exist_ok=True)
    (out / CAT / "findings" / "keepme.html").write_text("<p>keep</p>", encoding="utf-8")
    _build(tmp_path)
    assert (out / CAT / "assets" / "app-abc123.js").exists()
    assert (out / CAT / "findings" / "keepme.html").exists()


def test_a_broken_export_does_not_stop_the_site_build(tmp_path, monkeypatch):
    """Spec section 8: a failed data export must never block the daily cycle --
    the live page just keeps yesterday's file. The deep pages still ship."""
    import gpu_agent.dashboard.site_build as sb

    def boom(*a, **k):
        raise ValueError("no readings")

    monkeypatch.setattr(sb, "write_dashboard_json", boom)
    out = _build(tmp_path)
    assert not (out / CAT / "data" / "dashboard.json").exists()
    assert (out / CAT / "findings" / "index.html").exists()


def test_a_missing_category_page_fails_the_build(tmp_path):
    """Every deep page carries a "back to today's story" link to the category
    page. The link gate resolves those against a registered key, not a file --
    so if the committed page were ever deleted, the gate alone would still pass
    with every one of those links dead. Building the real site checks the file
    is actually on disk."""
    with pytest.raises(ValueError, match="index.html"):
        _build(tmp_path, place_shell=False, require_category_page=True)


def test_the_build_is_happy_when_the_committed_page_is_there(tmp_path):
    out = _build(tmp_path, place_shell=True, require_category_page=True)
    assert (out / CAT / "index.html").read_text(encoding="utf-8") == REACT_SHELL


def test_the_real_site_build_requires_the_category_page(tmp_path):
    """The check is only worth having if the production path turns it on."""
    source = Path("gpu_agent/cli.py").read_text(encoding="utf-8")
    assert "require_category_page=True" in source, (
        "gpu_agent/cli.py's `site` verb must build with the category-page "
        "check on -- it is the only caller that builds the real site")


def test_vite_never_empties_the_shared_output_directory(tmp_path):
    """The one setting that stands between a rebuild and a deleted deep-page
    tree. Read straight off the config so a careless edit fails here."""
    config = Path("web/vite.config.ts").read_text(encoding="utf-8")
    assert re.search(r"emptyOutDir:\s*false", config), (
        "web/vite.config.ts must set emptyOutDir: false -- a true here wipes "
        "findings/, series/, story/, entities/ and history.html off the site")
    assert re.search(r"OUT_DIR\s*=\s*['\"]\.\./site/" + re.escape(CAT) + r"['\"]",
                     config) and re.search(r"outDir:\s*OUT_DIR", config), (
        "web/vite.config.ts must build into the category's own site folder")
