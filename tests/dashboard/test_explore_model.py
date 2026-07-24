import datetime as dt
from gpu_agent.dashboard import explore_model as xm
from tests.dashboard.test_explore_fixtures import _explore_store


def test_findings_load_alias_and_sides(tmp_path):
    st = _explore_store(tmp_path)
    fs = xm.load_findings(st)
    assert {f["entitySlug"] for f in fs} >= {"nvidia", "tsmc"}   # NVDA folded in
    sides = xm.split_by_side(fs)
    assert sides["demand"] and sides["supply"]


def test_entity_roles(tmp_path):
    roles = xm.entity_roles(xm.load_findings(_explore_store(tmp_path)))
    assert roles["tsmc"] == "where the supply bottleneck lives"
    assert roles["nvidia"] == "a demand driver"


def test_entities_and_markdown(tmp_path):
    ents = xm.load_entities(_explore_store(tmp_path))
    assert {e["slug"] for e in ents} == {"nvidia", "tsmc"}
    html = xm.markdown_to_html("## Head\n\n**bold** <script>x</script>\n\n- a\n- b")
    assert "<h2>Head</h2>" in html and "<b>bold</b>" in html
    assert "<li>a</li>" in html and "<script>" not in html


def test_verdict_timeline_and_story_index(tmp_path):
    st = _explore_store(tmp_path)
    tl = xm.verdict_timeline(st / "chips.merchant-gpu")
    assert len(tl["months"]) == 2 and tl["months"][-1]["headline"]
    idx = xm.story_index(st, "chips.merchant-gpu")
    assert idx[0]["date"] == "2026-07-22" and idx[1]["fellBack"] is True
