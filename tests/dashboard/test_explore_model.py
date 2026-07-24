import datetime as dt
from gpu_agent.dashboard import explore_model as xm
from tests.dashboard.test_explore_fixtures import _explore_store
from tests.dashboard.test_story_model import _store


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


def test_verdict_timeline_uses_same_month_gap_word(tmp_path):
    # A constant demand-vs-supply gap widening RATE (dmi - smi == 1.8 every
    # single month) must read "widened" every month -- the gap is a running
    # sum, so a constant rate keeps opening the gap wider each month. A
    # second-derivative computation (this month's dmi-smi minus last
    # month's) would wrongly read a flat "held" for months 2 and 3 because
    # the rate itself never changes -- this pins the correct same-month
    # derivation (shared with story_model's own gap word), not that bug.
    st = _store(tmp_path, dmi_smi=((2.0, 0.2), (2.0, 0.2), (2.0, 0.2)),
                months=["2026-05", "2026-06", "2026-07"])
    tl = xm.verdict_timeline(st / "chips.merchant-gpu")
    assert len(tl["months"]) == 3
    assert [m["headline"] for m in tl["months"]] == [
        "The GPU shortage got worse this month."] * 3
