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
from gpu_agent.freshness import AGING_THRESHOLD

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
                 "evidence": [
                     {"source": "Micron call", "url": "https://x.example/a",
                      "date": "2026-06-24", "excerpt": "…", "tier": "primary"},
                     # Same registrable domain as the row above but a newer
                     # date -- exercises the one-row-per-publisher cap
                     # (F103 Task 2), which must keep this freshest row.
                     {"source": "Micron follow-up", "url": "https://x.example/a-followup",
                      "date": "2026-07-18", "excerpt": "…", "tier": "primary"},
                     # A stale investor-relations filing -- filingsDomains
                     # match ("investor.") on a half-life-5 kind, dated a
                     # month before "today" (2026-07-22), so it must rank
                     # last and be flagged aging (weight < AGING_THRESHOLD).
                     {"source": "Nvidia investor update",
                      "url": "https://investor.nvidia.com/news/2026-05",
                      "date": "2026-05-28", "excerpt": "…", "tier": "primary"}],
                 },
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
    # F103 Task 2: evidence rows are now weight-sorted with a one-row-per-
    # publisher cap. f-1 carries two x.example evidence rows (see _store) --
    # the newer "Micron follow-up" row decays less than the older "Micron
    # call" row, so it wins the publisher-diversity cap and sorts first.
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    ev = m["evidence"]["scene:1"]
    assert ev["findings"][0]["source"] == "Micron follow-up"
    assert ev["findings"][0]["url"] == "https://x.example/a-followup"
    demand_scene = next(s for s in m["scenes"] if s["title"] == "Demand kept climbing")
    assert demand_scene["related"][0]["outlet"] == "CNBC"


def test_evidence_rows_sorted_by_weight_and_dated(tmp_path):
    # F103 Task 2: scene:1's evidence rows (backed by f-1's two surviving
    # publishers -- see _store's x.example and investor.nvidia.com entries)
    # must be sorted with the highest-decay-weight row first, and every row
    # must carry both a "date" key (even when non-empty) and a "weight" key.
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    rows = m["evidence"]["scene:1"]["findings"]
    assert len(rows) >= 2
    weights = [r["weight"] for r in rows]
    assert weights == sorted(weights, reverse=True)
    for r in rows:
        assert "date" in r
        assert isinstance(r["weight"], float)


def test_one_row_per_publisher_keeps_freshest(tmp_path):
    # f-1 carries two evidence rows on the SAME registrable domain
    # (x.example): an older "Micron call" (2026-06-24) and a newer "Micron
    # follow-up" (2026-07-18). The publisher cap must collapse them to one
    # row -- the newer, higher-weight one.
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    rows = m["evidence"]["scene:1"]["findings"]
    x_example_rows = [r for r in rows if "x.example" in r["url"]]
    assert len(x_example_rows) == 1
    assert x_example_rows[0]["url"] == "https://x.example/a-followup"
    assert x_example_rows[0]["source"] == "Micron follow-up"


def test_may_filing_ranks_last_and_flags_aging(tmp_path):
    # The stale investor.nvidia.com filing (dated 2026-05-28, a filings-kind
    # half life of 5 days) must decay under AGING_THRESHOLD by "today"
    # (2026-07-22) and rank last among scene:1's evidence rows.
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    rows = m["evidence"]["scene:1"]["findings"]
    filing_row = next(r for r in rows if "investor.nvidia.com" in r["url"])
    assert filing_row["weight"] < AGING_THRESHOLD
    assert rows[-1] is filing_row


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


def test_collapse_repeated_word_does_not_eat_word_before_hyphenated_compound():
    # Reviewer-found bug: \b treats the hyphen in "supply-chain" as a word
    # boundary, so "supply supply-chain" matched on "supply" and silently
    # deleted the first copy. The fix requires a non-word/non-hyphen
    # character (or start/end of string) on both sides of the match, so a
    # word standing next to a hyphenated compound that starts the same way
    # must survive untouched.
    bw = {"supply", "memory", "demand", "chip", "packaging"}
    assert _collapse_repeated_word("the supply supply-chain risk", bw) == \
        "the supply supply-chain risk"
    assert _collapse_repeated_word("memory memory-maker capex", bw) == \
        "memory memory-maker capex"
    assert _collapse_repeated_word("a demand demand-led market", bw) == \
        "a demand demand-led market"
    assert _collapse_repeated_word("custom chip chip-level packaging", bw) == \
        "custom chip chip-level packaging"
    # The real stutter case (no hyphenated compound following) must still collapse:
    assert _collapse_repeated_word("advanced chip packaging packaging", bw) == \
        "advanced chip packaging"


def test_translation_boundary_words_exclude_common_english(tmp_path):
    # Item 2: the safety of the boundary bound depends on which words
    # actually begin or end the translation table's replacement values.
    # That set is derived at runtime from glossary.json (shared) plus
    # _STORY_TERMS (page-local) -- build it the same way the code does and
    # assert it doesn't contain ordinary function words a future glossary
    # entry could accidentally introduce. "the" and "up" are the two real
    # exceptions today (from "the leader's chip software" and "speeding
    # up") -- both are allowed here because "the the" / "up up" read as
    # typos, not legitimate English, so collapsing them is fine. A new
    # boundary word like "had" or "that" is NOT allowed and must fail this
    # test if introduced.
    from gpu_agent.dashboard.glossary import load_glossary
    from gpu_agent.dashboard.story_model import (_STORY_TERMS,
                                                  _story_glossary,
                                                  _translation_boundary_words)

    gl = _story_glossary(load_glossary())
    boundary_words = _translation_boundary_words(gl)

    allowed_exceptions = {"the", "up"}
    common_english = {
        "had", "that", "is", "a", "an", "and", "or", "but", "if", "it",
        "he", "she", "they", "we", "you", "was", "were", "be", "been",
        "to", "of", "in", "on", "at", "as", "for", "with", "this",
    } - allowed_exceptions

    offenders = boundary_words & common_english
    assert not offenders, (
        f"boundary word set now includes common English word(s) {offenders} -- "
        "a new glossary/prose_terms replacement widened the collapser's bound "
        "in a way that could rewrite legitimate English")


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


def test_translate_then_truncate_never_blows_the_length_budget(tmp_path):
    # Real-world case: truncating BEFORE translating a jargon term produces
    # a rendered line that blows the length budget (a 60-char cap on the
    # untranslated text produced an 81-char rendered line). The stored
    # statement below reproduces the shape: "CoWoS" -> "advanced chip
    # packaging" lengthens the text enough that truncating-then-translating
    # (the WRONG order) would push the result past the 90-char budget,
    # while translating-then-truncating (the actual pipeline) never does.
    #
    # This replaces a prior version of this test whose "mid-word" assertion
    # never actually fired: _truncate always backs up to a word boundary
    # regardless of which text it's given, so it can never produce a
    # literal mid-word cut either way -- the real, order-dependent failure
    # is the length budget being blown, which is what this test now pins.
    st = _store(tmp_path)
    cat = st / CAT
    statement = ("Deep packaging lines are fully booked through 2026, with CoWoS "
                 "packaging capacity the binding constraint on shipments")
    for f in cat.glob("2026-07-v1.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        data["findings"][0]["statement"] = statement
        f.write_text(json.dumps(data), encoding="utf-8")
    m = build_story_model(CAT, st, dt.date(2026, 7, 22))
    ev = m["evidence"]["scene:1"]
    take = ev["findings"][0]["take"]
    assert len(take) <= 91  # what the real (correct-order) pipeline produces

    # Simulate the WRONG order directly against the same primitives the
    # pipeline uses, to prove the 91-char budget above is a real constraint
    # this fixture can actually violate -- not a limit the fixture happens
    # to never approach.
    from gpu_agent.dashboard.glossary import load_glossary
    from gpu_agent.dashboard.story_model import _story_glossary, _translate
    gl = _story_glossary(load_glossary())
    wrong_order = _translate(_truncate(statement, 90), gl)
    assert len(wrong_order) > 91, (
        "fixture no longer demonstrates the ordering bug -- truncating "
        "before translating should blow the length budget")


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


def test_build_story_model_guards_a_broken_artifact_mapper(tmp_path, monkeypatch, capsys):
    # RECOMMENDATION 4: read_story_artifact's whole point is to be
    # indistinguishable from "no artifact" whenever it can't safely drive the
    # page -- a hand-edited or legacy artifact that passes schema validation
    # but breaks the mapper in some way the gate never anticipated must not
    # crash the live page. This module's own defensive code (see
    # read_story_artifact and _mk_scene) already guards every place we could
    # find that a schema-valid-but-nonsensical artifact might reach -- so
    # this test forces the failure directly (monkeypatching
    # read_story_artifact to raise) to prove build_story_model's own
    # try/except actually falls through to the assembler and warns, rather
    # than propagating the exception to the caller.
    import gpu_agent.dashboard.story_model as story_model_mod

    def _boom(*a, **kw):
        raise RuntimeError("simulated broken artifact mapper")

    monkeypatch.setattr(story_model_mod, "read_story_artifact", _boom)

    st = _store(tmp_path)
    assembled = story_model_mod._assemble_model(
        CAT, story_model_mod.resolve_store_root(CAT, st), dt.date(2026, 7, 22))
    model = build_story_model(CAT, st, dt.date(2026, 7, 22))
    assert model == assembled
    err = capsys.readouterr().err
    assert "gpu-agent narrator: warning:" in err
    assert CAT in err


# ── F61: evidence-vintage + honest-confidence line ──────────────────────────

def _patch_latest(store, **updates):
    """Rewrite the latest (2026-07) scorecard in a `_store` fixture with
    `updates` merged in. A value of None deletes the key."""
    p = store / CAT / "2026-07-v1.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    for k, v in updates.items():
        if v is None:
            raw.pop(k, None)
        else:
            raw[k] = v
    p.write_text(json.dumps(raw), encoding="utf-8")
    return store


def _honesty(tmp_path, **updates):
    st = _patch_latest(_store(tmp_path), **updates)
    return build_story_model(CAT, st, dt.date(2026, 7, 22))["honesty"]


def test_honesty_carries_vintage_and_confidence(tmp_path):
    h = _honesty(tmp_path, confidence={"level": "high",
                                       "basis": "self-consistency over 3 samples"})
    # Evidence dates in the fixture: 2026-05-28, 2026-06-10, 2026-06-24, 2026-07-18.
    assert h["median"] == "2026-06-24"
    assert h["oldest"] == "2026-05-28"
    assert h["stale_pct"] == 0          # asOf 2026-07 -> cutoff 2026-05-20
    assert h["level"] == "high"
    assert h["votes"] == 3


def test_honesty_numbers_match_report_evidence_vintage(tmp_path):
    """One implementation of the date math: the story page must report exactly
    what report.evidence_vintage computes for the same scorecard."""
    from gpu_agent.report import evidence_vintage
    from gpu_agent.dashboard.story_model import _VintageAdapter

    st = _store(tmp_path)
    raw = json.loads((st / CAT / "2026-07-v1.json").read_text(encoding="utf-8"))
    median, oldest, share = evidence_vintage(_VintageAdapter(raw))
    h = build_story_model(CAT, st, dt.date(2026, 7, 22))["honesty"]
    assert (h["median"], h["oldest"]) == (median, oldest)
    assert h["stale_pct"] == round(share * 100)


def test_honesty_counts_stale_evidence(tmp_path):
    """An evidence date well before the asOf cutoff lifts the stale share."""
    st = _store(tmp_path)
    p = st / CAT / "2026-07-v1.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["findings"][1]["evidence"][0]["date"] = "2026-01-05"
    p.write_text(json.dumps(raw), encoding="utf-8")
    h = build_story_model(CAT, st, dt.date(2026, 7, 22))["honesty"]
    assert h["oldest"] == "2026-01-05"
    assert h["stale_pct"] == 25          # 1 of 4 dated pieces


def test_honesty_votes_none_when_basis_has_no_number(tmp_path):
    h = _honesty(tmp_path, confidence={"level": "medium",
                                       "basis": "agreement between reads"})
    assert h["level"] == "medium" and h["votes"] is None


def test_honesty_without_confidence_keeps_vintage(tmp_path):
    h = _honesty(tmp_path, confidence=None)
    assert h["median"] and h["level"] is None and h["votes"] is None


def test_honesty_without_dated_evidence_keeps_confidence(tmp_path):
    st = _store(tmp_path)
    p = st / CAT / "2026-07-v1.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["confidence"] = {"level": "low", "basis": "one read"}
    for f in raw["findings"]:
        for e in f["evidence"]:
            e["date"] = ""
    p.write_text(json.dumps(raw), encoding="utf-8")
    h = build_story_model(CAT, st, dt.date(2026, 7, 22))["honesty"]
    assert h["median"] is None and h["oldest"] is None and h["stale_pct"] is None
    assert h["level"] == "low"


def test_honesty_none_when_nothing_to_say(tmp_path):
    st = _store(tmp_path)
    p = st / CAT / "2026-07-v1.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw.pop("confidence", None)
    for f in raw["findings"]:
        f["evidence"] = []
    p.write_text(json.dumps(raw), encoding="utf-8")
    assert build_story_model(CAT, st, dt.date(2026, 7, 22))["honesty"] is None


def test_honesty_degrades_on_malformed_date(tmp_path, capsys):
    """A date the vintage math cannot parse must drop the line, not crash the
    live page -- the same contract build_story_model uses for a bad artifact."""
    st = _store(tmp_path)
    p = st / CAT / "2026-07-v1.json"
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["findings"][0]["evidence"][0]["date"] = "last spring"
    p.write_text(json.dumps(raw), encoding="utf-8")
    assert build_story_model(CAT, st, dt.date(2026, 7, 22))["honesty"] is None
    assert "evidence vintage" in capsys.readouterr().err


def test_honesty_is_deterministic(tmp_path):
    st = _patch_latest(_store(tmp_path),
                       confidence={"level": "high", "basis": "3 samples"})
    a = build_story_model(CAT, st, dt.date(2026, 7, 22))["honesty"]
    b = build_story_model(CAT, st, dt.date(2026, 7, 22))["honesty"]
    assert a == b
