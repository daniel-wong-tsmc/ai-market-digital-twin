import datetime as dt
import json
import re
from pathlib import Path
from gpu_agent.dashboard.story_model import (_STORY_TERMS,
                                              _collapse_repeated_word,
                                              _truncate,
                                              build_story_model,
                                              resolve_store_root)
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


def test_scene_with_no_findings_shows_honest_empty_evidence_not_a_borrowed_source(tmp_path):
    # Real-data reproduction: an implication line with its finding ids
    # stripped (common in real data) leaves the "What would close the gap"
    # scene with no resolvable findings of its own. The evidence entry for
    # that scene must show an honest empty list -- never fall back to
    # another claim's sources (e.g. the always-present gpuRentalOnDemand
    # chip), which would attribute the claim to a source that never made
    # it, defeating the page's whole "says who?" promise.
    st = _store(tmp_path)
    impl_path = st / "implications" / CAT / "2026-07.json"
    impl = json.loads(impl_path.read_text(encoding="utf-8"))
    for line in impl["lines"]:
        line["findingIds"] = []
    impl_path.write_text(json.dumps(impl), encoding="utf-8")

    m = build_story_model(CAT, st, dt.date(2026, 7, 22))
    watch_scene = next(s for s in m["scenes"] if s["title"] == "What would close the gap")
    ev = m["evidence"][f"scene:{watch_scene['n']}"]
    assert ev["findings"] == []
    # The GPU-rental chip's own evidence is real and non-empty -- proving
    # the empty list above is an honest empty state, not an accident of the
    # fixture having no evidence anywhere.
    rental_ev = m["evidence"]["kpi:gpuRentalOnDemand"]
    assert rental_ev["findings"]


def test_categorical_chip_suppresses_arrow(tmp_path):
    # The "Big buyers' spending plans" chip's value text is categorical
    # ("raised again"/"trimmed"/"holding"), not a number -- so an arrow
    # comparing the raw numbers behind it can contradict the word (a
    # smaller-but-still-positive revision reads "raised again" next to a
    # down arrow). The chip must carry no arrow at all.
    st = _store(tmp_path)
    series_path = st / "series" / "hyperscalerCapexRevision.jsonl"
    rows = [{"indicatorId": "hyperscalerCapexRevision", "period": p, "value": v,
             "unit": "x", "publishedAt": p + "-28",
             "source": {"url": "https://src.example/hcr", "title": "hcr source"}}
            for p, v in [("2026-05", 5.0), ("2026-06", 0.4)]]  # smaller but still positive
    series_path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    m = build_story_model(CAT, st, dt.date(2026, 7, 22))
    pick = next(p for p in m["kpis"]["picks"] if p["label"] == "Big buyers' spending plans")
    assert pick["value"] == "raised again"
    assert pick["arrow"] == ""


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


def test_explore_counts_same_either_invocation_shape(tmp_path):
    # The four explore tiles (entities/findings/series/history) must count
    # the same regardless of how the caller invokes the build: passing the
    # store root (holding <category>/ alongside series/, findings/,
    # wiki/) or passing the category directory itself (whose parent is the
    # store root -- the CLI's own established convention, and the shape
    # that used to leave the entity/findings globs pointed at a
    # non-existent nested directory while series happened to still resolve).
    st = _store(tmp_path)
    (st / "wiki" / "entity").mkdir(parents=True)
    (st / "wiki" / "entity" / "nvidia.md").write_text("x", encoding="utf-8")
    (st / "findings").mkdir()
    (st / "findings" / "a.json").write_text("{}", encoding="utf-8")

    m_root = build_story_model(CAT, st, dt.date(2026, 7, 22))
    m_catdir = build_story_model(CAT, st / CAT, dt.date(2026, 7, 22))

    expected = {"entities": 1, "findings": 1, "series": 5, "history": 2}
    assert m_root["explore"] == expected
    assert m_catdir["explore"] == expected


def test_resolve_store_root_handles_both_shapes(tmp_path):
    cat = tmp_path / CAT
    cat.mkdir(parents=True)
    assert resolve_store_root(CAT, tmp_path) == tmp_path       # store root
    assert resolve_store_root(CAT, cat) == tmp_path             # category dir


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
    # must survive untouched -- regardless of the boundary-word bound.
    bw = {"packaging", "is"}
    assert (_collapse_repeated_word("Packaging, packaging capacity is booked.", bw)
            == "Packaging, packaging capacity is booked.")
    assert (_collapse_repeated_word("what it is, is the bottleneck", bw)
            == "what it is, is the bottleneck")


def test_collapse_repeated_word_keeps_first_casing_and_is_case_insensitive():
    bw = {"logistics", "packaging", "the"}
    assert _collapse_repeated_word("Logistics logistics delays", bw) == "Logistics delays"
    assert _collapse_repeated_word("packaging Packaging supply", bw) == "packaging supply"
    assert _collapse_repeated_word("the the", bw) == "the"


def test_collapse_repeated_word_is_bounded_to_translation_boundary_words():
    # Reviewer-mandated bound: only collapse a duplicate when that word is
    # the first or last word of one of the translation table's own
    # replacement values. That provably covers every stutter a translation
    # swap can create (the swap can only ever strand its own first/last
    # word against the text immediately beside it) and -- unlike the old
    # unbounded rule -- cannot touch legitimate English like "had had" or
    # "that that", since neither "had" nor "that" is ever the first/last
    # word of a replacement value. This test replaces the one that used to
    # pin the unbounded (collapse-anything) behaviour, keeping the
    # trade-off documented rather than silently dropped.
    bw = {"packaging", "logistics"}
    assert _collapse_repeated_word("He had had enough of the delays.", bw) == \
        "He had had enough of the delays."
    assert _collapse_repeated_word("I know that that reading is stale.", bw) == \
        "I know that that reading is stale."
    # But a real stutter shape (the word IS a boundary word) still collapses:
    assert _collapse_repeated_word("advanced chip packaging packaging", bw) == \
        "advanced chip packaging"


def test_truncate_breaks_on_word_boundary_with_ellipsis():
    text = "fully booked through 2026, with wait time from order to delivery varying widely"
    out = _truncate(text, 60)
    assert len(out) <= 61  # 60 + the ellipsis character
    assert out.endswith("…")
    assert not out[:-1].endswith(" ")   # no trailing space before the ellipsis
    # Never cuts mid-word: what's left (minus the ellipsis) is a prefix of
    # the original text ending exactly at a word boundary.
    body = out[:-1].rstrip()
    assert text.startswith(body)
    assert text[len(body):len(body) + 1] in (" ", "")


def test_truncate_is_a_noop_under_the_limit():
    assert _truncate("short text", 90) == "short text"


def test_translate_then_truncate_never_cuts_a_translated_word_in_half(tmp_path):
    # Real-world case: truncating BEFORE translating a jargon term produces
    # a rendered line that blows the length budget and ends mid-word (a
    # 60-char cap on the untranslated text produced an 81-char rendered
    # line). The stored statement below is short enough to survive a
    # naive pre-translate 90-char cut mid-word through "packaging", but
    # once "CoWoS" expands to "advanced chip packaging" the translated
    # text is longer -- proving translation happened BEFORE truncation
    # only if the rendered text still ends on a whole word (or ellipsis),
    # never mid-word.
    st = _store(tmp_path)
    cat = st / CAT
    for f in cat.glob("2026-07-v1.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        data["findings"][0]["statement"] = (
            "Deep packaging lines are fully booked through 2026, with CoWoS "
            "packaging capacity the binding constraint on shipments")
        f.write_text(json.dumps(data), encoding="utf-8")
    m = build_story_model(CAT, st, dt.date(2026, 7, 22))
    ev = m["evidence"]["scene:1"]
    take = ev["findings"][0]["take"]
    assert len(take) <= 91
    body = take[:-1].rstrip() if take.endswith("…") else take
    last_word = body.split()[-1] if body.split() else ""
    # The last word must be a WHOLE word: if it happens to be a prefix of
    # "packaging" (the translated form of the stored "CoWoS"), it must be
    # the full word -- a shorter prefix would mean translation happened
    # AFTER truncation and cut the translated word in half.
    assert not ("packaging".startswith(last_word) and last_word != "packaging")


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
