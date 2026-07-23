import datetime as dt
import json
import re
from pathlib import Path
from gpu_agent.dashboard.story_model import (_STORY_TERMS,
                                              _collapse_repeated_word,
                                              build_story_model)
from gpu_agent.dashboard.story_render import _BANNED_STORY

CAT = "chips.merchant-gpu"


def _store(tmp_path, dmi_smi=((1.0, 0.5), (2.0, 0.2)), months=None):
    cat = tmp_path / CAT
    cat.mkdir(parents=True)
    months = months or ["2026-06", "2026-07"]
    for m, (dmi, smi) in zip(months, dmi_smi):
        (cat / f"{m}-v1.json").write_text(json.dumps({
            "asOf": m,
            "demandSupply": {"dmiContribution": dmi, "smiContribution": smi},
            "categoryStatus": {"rating": "Strong", "direction": "improving",
                               "bottleneck": "bottleneck",
                               "reason": "Packaging capacity is booked out.",
                               "constraintLabel": "advanced packaging"},
            "dimensionRatings": {
                "bottleneck": {"rating": "Weak", "direction": "worsening",
                                "findingIds": ["f-1"],
                                "rationale": "Memory makers cut back supply. New lines take a year."},
                "momentum": {"rating": "Strong", "direction": "improving",
                              "findingIds": ["f-2"],
                              "rationale": "Buyers raised budgets again."}},
            "findings": [
                {"id": "f-1", "statement": "SK Hynix shifted HBM output",
                 "evidence": [{"source": "Micron call", "url": "https://x.example/a",
                                "date": "2026-06-24", "excerpt": "…", "tier": "primary"}]},
                {"id": "f-2", "statement": "Oracle capex up 162%",
                 "evidence": [{"source": "CNBC", "url": "https://x.example/b",
                                "date": "2026-06-10", "excerpt": "…", "tier": "secondary"}]}],
        }), encoding="utf-8")
    series = tmp_path / "series"
    series.mkdir()
    rows = {
        "gpuRentalOnDemand": [("2026-05", 15.10), ("2026-06", 14.62)],
        "odmMonthlyAiRevenue": [("2026-05", 61.0), ("2026-06", 68.8)],
        "hbmSupplyCapex": [("2026-05", 42.0), ("2026-06", 50.0)],
        "hyperscalerCapexRevision": [("2026-05", 1.0), ("2026-06", 1.0)],
        "gpuSpotPrice": [("2026-02", 31000.0), ("2026-03", 32516.0)],
    }
    for ind, pts in rows.items():
        (series / f"{ind}.jsonl").write_text("\n".join(json.dumps({
            "indicatorId": ind, "period": p, "value": v, "unit": "x",
            "publishedAt": p + "-28",
            "source": {"url": f"https://src.example/{ind}", "title": f"{ind} source"},
        }) for p, v in pts), encoding="utf-8")
    (tmp_path / "implications" / CAT).mkdir(parents=True)
    (tmp_path / "implications" / CAT / "2026-07.json").write_text(json.dumps({
        "asOf": "2026-07", "categoryId": CAT,
        "lines": [{"dimensions": ["bottleneck"], "findingIds": ["f-1"],
                   "thesisIds": [], "watchItem": "Watch memory supply recovery."}],
    }), encoding="utf-8")
    return tmp_path


def test_headline_deck_dateline(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    assert m["headline"] == "The GPU shortage got worse this month."
    assert "advanced packaging" in m["deck"]
    assert m["dateline"].startswith("Wednesday, July 22, 2026")
    assert m["gap"]["gap_word"] == "widened"


def test_headline_when_gap_narrows(tmp_path):
    st = _store(tmp_path, dmi_smi=((2.0, 0.2), (0.5, 2.0)))
    m = build_story_model(CAT, st, dt.date(2026, 7, 22))
    assert m["headline"] == "Supply gained ground on demand this month."


def test_kpi_band_anchored_and_picks(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    a = m["kpis"]["anchored"]
    assert a["claim"] == "kpi:gpuRentalOnDemand"
    assert a["value"] == "$14.62/hr" and a["arrow"] == "▼"
    assert "price of scarcity" in a["caption"]
    labels = [p["label"] for p in m["kpis"]["picks"]]
    assert "Servers actually shipped" in labels
    assert "Big buyers' spending plans" in labels
    pick = next(p for p in m["kpis"]["picks"] if p["label"] == "Servers actually shipped")
    assert pick["value"] == "+69% vs last year" and pick["arrow"] == "▲"
    assert pick["tip"]  # hover description present


def test_every_chip_has_evidence_entry(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    chips = [m["kpis"]["anchored"], *m["kpis"]["picks"]]
    for c in chips:
        ev = m["evidence"][c["claim"]]
        assert "says who?" in ev["title"]
        assert ev["findings"] and ev["findings"][0]["url"].startswith("https://")


def test_missing_series_chip_skipped(tmp_path):
    st = _store(tmp_path)
    (st / "series" / "odmMonthlyAiRevenue.jsonl").unlink()
    m = build_story_model(CAT, st, dt.date(2026, 7, 22))
    assert "Servers actually shipped" not in [p["label"] for p in m["kpis"]["picks"]]


def test_scenes_assembled(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    titles = [s["title"] for s in m["scenes"]]
    assert titles[0] == "What tightened"
    assert titles[-1] == "What would close the gap"
    s1 = m["scenes"][0]
    assert s1["n"] == 1 and s1["accent"] == "amber"
    assert any("memory makers cut back" in p.lower() for p in s1["paragraphs"])
    assert s1["visual"]["kind"] == "spark" and s1["visual"]["series"]
    assert s1["source_line"].startswith("Source: ")
    assert "momentum" not in " ".join(
        p for s in m["scenes"] for p in s["paragraphs"]).lower()


def test_scene_evidence_and_related(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    ev = m["evidence"]["scene:1"]
    assert ev["findings"][0]["source"] == "Micron call"
    assert ev["findings"][0]["url"] == "https://x.example/a"
    demand_scene = next(s for s in m["scenes"] if s["title"] == "Demand kept climbing")
    assert demand_scene["related"][0]["outlet"] == "CNBC"


def test_forward_scene_from_implications(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    last = m["scenes"][-1]
    assert any("memory supply recovery" in p.lower() for p in last["paragraphs"])


def test_kpi_scene_links_and_callouts(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    # Topical rule (owner decision): a chip links to the scene whose visual
    # is built from that chip's own indicator series, not to a scene by
    # position. The "Big buyers' spending plans" chip (hyperscalerCapexRevision)
    # must land on "Demand kept climbing", the scene that actually draws
    # that series.
    demand_n = next(s["n"] for s in m["scenes"] if s["title"] == "Demand kept climbing")
    big_buyers = next(p for p in m["kpis"]["picks"]
                      if p["label"] == "Big buyers' spending plans")
    assert big_buyers["scene"] == demand_n
    # gpuSpotPrice has no scene built from it in this fixture -> no link.
    spot = next((p for p in m["kpis"]["picks"] if p["label"] == "Street price per GPU"),
               None)
    if spot is not None:
        assert spot["scene"] is None
    assert m["callouts"] and m["callouts"][0]["claim"].startswith("scene:")


def test_callout_claim_points_to_first_surviving_scene(tmp_path):
    # The "bottleneck" dimension is present but carries no rationale (and
    # categoryStatus has no reason), so scene 1 ("What tightened") ends up
    # with no paragraphs and is dropped. Because scene numbers are assigned
    # by position before that drop, the next scene ("Demand kept climbing")
    # keeps number 2 rather than being renumbered to 1. The callout's claim
    # must reference that scene's real number, not a hardcoded "scene:1"
    # that no longer exists in evidence.
    cat = tmp_path / CAT
    cat.mkdir(parents=True)
    for m, (dmi, smi) in zip(["2026-06", "2026-07"], ((1.0, 0.5), (2.0, 0.2))):
        (cat / f"{m}-v1.json").write_text(json.dumps({
            "asOf": m,
            "demandSupply": {"dmiContribution": dmi, "smiContribution": smi},
            "categoryStatus": {"rating": "Strong", "direction": "improving",
                               "reason": "",
                               "constraintLabel": "advanced packaging"},
            "dimensionRatings": {
                "bottleneck": {"rating": "Weak", "direction": "worsening",
                                "findingIds": [], "rationale": ""},
                "momentum": {"rating": "Strong", "direction": "improving",
                              "findingIds": ["f-2"],
                              "rationale": "Buyers raised budgets again."}},
            "findings": [
                {"id": "f-2", "statement": "Oracle capex up 162%",
                 "evidence": [{"source": "CNBC", "url": "https://x.example/b",
                                "date": "2026-06-10", "excerpt": "…", "tier": "secondary"}]}],
        }), encoding="utf-8")
    series = tmp_path / "series"
    series.mkdir()
    (series / "hyperscalerCapexRevision.jsonl").write_text("\n".join(json.dumps({
        "indicatorId": "hyperscalerCapexRevision", "period": p, "value": v, "unit": "x",
        "publishedAt": p + "-28",
        "source": {"url": "https://src.example/hcr", "title": "hcr source"},
    }) for p, v in [("2026-05", 1.0), ("2026-06", 1.0)]), encoding="utf-8")
    m = build_story_model(CAT, tmp_path, dt.date(2026, 7, 22))
    assert m["scenes"]
    assert m["scenes"][0]["title"] != "What tightened"
    assert m["scenes"][0]["n"] != 1
    assert m["callouts"]
    claim = m["callouts"][0]["claim"]
    assert claim == f"scene:{m['scenes'][0]['n']}"
    assert claim in m["evidence"]


def test_archive_and_explore_counts(tmp_path):
    st = _store(tmp_path)
    (st / "wiki" / "entity").mkdir(parents=True)
    (st / "wiki" / "entity" / "nvidia.md").write_text("x", encoding="utf-8")
    (st / "findings").mkdir()
    (st / "findings" / "a.json").write_text("{}", encoding="utf-8")
    m = build_story_model(CAT, st, dt.date(2026, 7, 22))
    assert m["explore"] == {"entities": 1, "findings": 1, "series": 5,
                            "history": 2}
    # Owner decision: a chip for month M needs the month before it, and the
    # current (latest) month is today's story, not archive. With only two
    # monthly snapshots (June + July) no month has both a predecessor and
    # is not the latest, so the archive is empty.
    assert m["archive"] == []


def test_constraint_label_with_banned_word_is_translated(tmp_path):
    # Real-world case: a scorecard's constraintLabel is "CoWoS and HBM4
    # allocation" -- "allocation" is on the copy lint's banned-word list.
    # The deck sentence must carry the translated label, not the raw one,
    # or the page-build lint fires the day this scorecard becomes latest.
    st = _store(tmp_path)
    cat = st / CAT
    for f in cat.glob("2026-07-v1.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        data["categoryStatus"]["constraintLabel"] = "CoWoS and HBM4 allocation"
        f.write_text(json.dumps(data), encoding="utf-8")
    m = build_story_model(CAT, st, dt.date(2026, 7, 22))
    assert "allocation" not in m["deck"].lower()
    assert "how supply is split" in m["deck"]


def test_story_terms_replacements_contain_no_banned_word(tmp_path):
    # The translation table exists to strip banned words from stored text.
    # If a replacement value itself contained a banned word, the table
    # would silently reintroduce the very jargon it's meant to remove.
    # Compare against the page lint's own banned-word list rather than a
    # second hardcoded copy, so the two can't drift apart unnoticed.
    for replacement in _STORY_TERMS.values():
        for banned in _BANNED_STORY:
            assert not re.search(rf"\b{banned}\b", replacement, re.I), (
                f"replacement {replacement!r} contains banned word {banned!r}")


def test_cowos_translation_does_not_stutter(tmp_path):
    # Real-world case: the stored constraintLabel is literally
    # "CoWoS packaging and HBM supply". Translating "CoWoS" ->
    # "advanced chip packaging" (glossary.json) leaves the stored word
    # "packaging" stranded right after it -- "advanced chip packaging
    # packaging" -- unless the doubled word gets collapsed.
    st = _store(tmp_path)
    cat = st / CAT
    for f in cat.glob("2026-07-v1.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        data["categoryStatus"]["constraintLabel"] = "CoWoS packaging and HBM supply"
        f.write_text(json.dumps(data), encoding="utf-8")
    m = build_story_model(CAT, st, dt.date(2026, 7, 22))
    assert "advanced chip packaging" in m["deck"]
    assert "packaging packaging" not in m["deck"].lower()
    assert m["deck"].startswith(
        "The main chokepoint is advanced chip packaging and high-bandwidth memory supply.")


def test_collapse_repeated_word_leaves_punctuated_repeat_alone():
    # A legitimate repeat separated by punctuation (or any non-whitespace)
    # is not the "stranded word" shape the translation bug produces, and
    # must survive untouched.
    assert (_collapse_repeated_word("Packaging, packaging capacity is booked.")
            == "Packaging, packaging capacity is booked.")
    assert (_collapse_repeated_word("what it is, is the bottleneck")
            == "what it is, is the bottleneck")


def test_collapse_repeated_word_keeps_first_casing_and_is_case_insensitive():
    assert _collapse_repeated_word("Logistics logistics delays") == "Logistics delays"
    assert _collapse_repeated_word("packaging Packaging supply") == "packaging supply"
    assert _collapse_repeated_word("the the") == "the"


def test_collapse_repeated_word_judgement_call_is_general_not_translation_only():
    # Judgement call: collapse ANY immediately-repeated word, not only ones
    # a translation created. This means a genuine doubled word like "had
    # had" or "that that" would also be collapsed if it ever showed up in
    # stored text. A repo-wide scan of every stored/test fixture in this
    # project (JSON, Markdown, Python) turned up zero adjacent same-word
    # repeats outside the CoWoS bug itself, so in this codebase's actual
    # data the general rule never fires on legitimate prose -- but the
    # trade-off is real and worth pinning down explicitly here rather than
    # discovering it later.
    assert _collapse_repeated_word("He had had enough of the delays.") == \
        "He had enough of the delays."
    assert _collapse_repeated_word("I know that that reading is stale.") == \
        "I know that reading is stale."


def test_archive_multi_month_semantics(tmp_path):
    # Five monthly snapshots: Mar, Apr, May, Jun, Jul. Jul is the latest
    # (excluded, it's today's story). Mar has no predecessor, so the
    # archive covers Apr, May, Jun in that order, each headline reflecting
    # the change DURING that labelled month (not the change into the
    # following month).
    months = ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]
    dmi_smi = (
        (1.0, 1.0),   # Mar: baseline, no predecessor -> never archived
        (2.0, 0.5),   # Apr: gap widens during April
        (0.5, 2.0),   # May: gap narrows during May
        (1.0, 1.0),   # Jun: gap holds during June
        (2.0, 0.2),   # Jul: latest -> excluded from archive
    )
    st = _store(tmp_path, dmi_smi=dmi_smi, months=months)
    m = build_story_model(CAT, st, dt.date(2026, 7, 22))
    assert [e["key"] for e in m["archive"]] == ["2026-04", "2026-05", "2026-06"]
    assert [e["label"] for e in m["archive"]] == ["April 2026", "May 2026", "June 2026"]
    texts = {e["key"]: e["text"] for e in m["archive"]}
    assert texts["2026-04"] == "The GPU shortage got worse this month."
    assert texts["2026-05"] == "Supply gained ground on demand this month."
    assert texts["2026-06"] == "The GPU shortage held steady this month."
