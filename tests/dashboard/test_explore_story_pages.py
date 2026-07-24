"""F101c Task 3: story archive permalinks + index."""
import datetime as dt

from gpu_agent.dashboard import explore_render as xr
from gpu_agent.dashboard import story_model as sm
from gpu_agent.dashboard.render import esc
from gpu_agent.dashboard.story_render import _scene_html, lint_story_copy, render_story_page
from tests.dashboard.test_explore_fixtures import _explore_store

CAT = "chips.merchant-gpu"


def test_read_story_artifact_today_behavior_unchanged(tmp_path):
    root = _explore_store(tmp_path)
    today = dt.date(2026, 7, 22)
    m1 = sm.read_story_artifact(CAT, root, today)
    m2 = sm.read_story_artifact(CAT, root, today, story_date=None)
    assert m1 == m2
    assert m1 is not None


def test_read_story_artifact_story_date_reads_arbitrary_day(tmp_path):
    root = _explore_store(tmp_path)
    # "today" is a different date than the artifact we want -- story_date
    # is what picks the artifact, not the `today` param.
    m = sm.read_story_artifact(CAT, root, dt.date(2026, 7, 23), story_date="2026-07-22")
    assert m is not None
    assert m["headline"] == "Yesterday's H"


def test_read_story_artifact_story_date_missing_returns_none(tmp_path):
    root = _explore_store(tmp_path)
    assert sm.read_story_artifact(CAT, root, dt.date(2026, 7, 23),
                                   story_date="2026-01-01") is None


def test_read_story_artifact_story_date_fellback_returns_none(tmp_path):
    root = _explore_store(tmp_path)
    assert sm.read_story_artifact(CAT, root, dt.date(2026, 7, 23),
                                   story_date="2026-07-21") is None


def test_render_story_day_reuses_scene_html_and_has_evidence(tmp_path):
    root = _explore_store(tmp_path)
    date = "2026-07-22"
    model = sm.read_story_artifact(CAT, root, dt.date(2026, 7, 22), story_date=date)
    front_html = render_story_page(model)
    day_html = xr.render_story_day(model, date)

    scene = model["scenes"][0]
    expected = _scene_html(scene)
    assert expected in front_html
    assert expected in day_html
    assert esc(model["headline"]) in day_html
    assert 'id="ev-data"' in day_html
    assert lint_story_copy(day_html) == []


def test_render_story_day_missing_renders_notice(tmp_path):
    html = xr.render_story_day(None, "2026-07-01")
    assert "No narrated entry this day — the page ran on assembled data." in html
    assert lint_story_copy(html) == []


def test_render_story_day_fellback_renders_notice(tmp_path):
    root = _explore_store(tmp_path)
    date = "2026-07-21"
    model = sm.read_story_artifact(CAT, root, dt.date(2026, 7, 21), story_date=date)
    assert model is None
    html = xr.render_story_day(model, date)
    assert "No narrated entry this day — the page ran on assembled data." in html
    assert lint_story_copy(html) == []


def test_render_story_index_marks_fellback_and_lists_both(tmp_path):
    entries = [
        {"date": "2026-07-22", "headline": "Yesterday's H", "fellBack": False},
        {"date": "2026-07-21", "headline": "H", "fellBack": True},
    ]
    html = xr.render_story_index(entries)
    assert "2026-07-22" in html and esc("Yesterday's H") in html
    assert "2026-07-21" in html
    assert "(assembled)" in html
    assert lint_story_copy(html) == []
