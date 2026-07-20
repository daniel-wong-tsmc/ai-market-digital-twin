import json
from gpu_agent.dashboard.brief_model import (
    last_signal_check, latest_monthly, read_implication_lines,
    read_thesis_book, select_calls)

CAT = "chips.merchant-gpu"


def _mk_store(tmp_path):
    root = tmp_path / "store"
    cat = root / CAT
    cat.mkdir(parents=True)
    return root, cat


def _monthly(as_of, narrative="n", findings=()):
    return {"asOf": as_of, "narrative": narrative,
            "categoryStatus": {"rating": "Strong", "direction": "steady",
                               "reason": "r.", "constraintLabel": "HBM supply"},
            "dimensionRatings": {}, "findings": list(findings), "sources": []}


def test_latest_monthly_picks_highest_revision_and_prior(tmp_path):
    root, cat = _mk_store(tmp_path)
    (cat / "2026-07-v1.json").write_text(json.dumps(_monthly("2026-07", "one")),
                                         encoding="utf-8")
    (cat / "2026-07-v2.json").write_text(json.dumps(_monthly("2026-07", "two")),
                                         encoding="utf-8")
    (cat / "2026-07-06-v1.json").write_text(json.dumps(_monthly("2026-07-06")),
                                            encoding="utf-8")   # daily: excluded
    latest, prior, as_of, rev = latest_monthly(cat)
    assert latest["narrative"] == "two" and prior["narrative"] == "one"
    assert (as_of, rev) == ("2026-07", 2)


def test_read_thesis_book_and_select_calls(tmp_path):
    root, _ = _mk_store(tmp_path)
    book = root / "theses" / CAT
    book.mkdir(parents=True)
    entries = [
        {"title": "prov", "conviction": "high", "status": "provisional",
         "streak": 9, "lens": "risk", "lastVerdict": "strengthened",
         "falsifiableTrigger": "t"},
        {"title": "low-reg", "conviction": "low", "status": "registered",
         "streak": 5, "lens": "demand", "lastVerdict": None,
         "falsifiableTrigger": "t"},
        {"title": "high-reg", "conviction": "high", "status": "registered",
         "streak": 1, "lens": "supply", "lastVerdict": "weakened",
         "falsifiableTrigger": "t"},
    ]
    (book / "book.json").write_text(json.dumps({"entries": entries}),
                                    encoding="utf-8")
    got = read_thesis_book(root, CAT)
    rows, total, prov = select_calls(got, cap=2)
    assert total == 3 and prov == 1
    assert [r["title"] for r in rows] == ["high-reg", "low-reg"]  # registered first


def test_select_calls_empty_book():
    assert select_calls([], cap=7) == ([], 0, 0)


def test_read_implication_lines_falls_back_to_newest(tmp_path):
    root, _ = _mk_store(tmp_path)
    impl = root / "implications" / CAT
    impl.mkdir(parents=True)
    art = {"lines": [{"watchItem": "w1", "dimensions": ["momentum"],
                      "thesisIds": ["a"], "findingIds": ["f1"]}]}
    (impl / "2026-06.json").write_text(json.dumps(art), encoding="utf-8")
    got = read_implication_lines(root, CAT, "2026-07")     # 07 missing -> 06
    assert got[0]["text"] == "w1" and got[0]["dims"] == ["momentum"]
    assert read_implication_lines(root, "nope", "2026-07") == []


def test_last_signal_check_prefers_cycle_log(tmp_path):
    root, cat = _mk_store(tmp_path)
    (root / "cycle-log.json").write_text(
        json.dumps({"capturedAt": "2026-07-15T10:55:20Z"}), encoding="utf-8")
    f = {"capturedAt": "2026-07-06T01:00:00Z"}
    (cat / "2026-07-v1.json").write_text(json.dumps(_monthly("2026-07",
                                         findings=[f])), encoding="utf-8")
    assert last_signal_check(root, cat) == "2026-07-15"
    (root / "cycle-log.json").unlink()
    assert last_signal_check(root, cat) == "2026-07-06"


def test_readers_defensive_on_missing_and_corrupt(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    # missing category dir -> latest_monthly never raises (locks in d9b9444)
    assert latest_monthly(root / "nope") == (None, None, "", 0)
    assert last_signal_check(root, root / "nope") == ""
    # corrupt thesis book: non-list "entries" -> [] (never raises)
    book = root / "theses" / CAT
    book.mkdir(parents=True)
    (book / "book.json").write_text(json.dumps({"entries": 5}), encoding="utf-8")
    assert read_thesis_book(root, CAT) == []
    # corrupt implications: non-list "lines" -> [] (never raises)
    impl = root / "implications" / CAT
    impl.mkdir(parents=True)
    (impl / "2026-07.json").write_text(json.dumps({"lines": 5}), encoding="utf-8")
    assert read_implication_lines(root, CAT, "2026-07") == []
    # corrupt cycle-log: top-level list -> falls back to monthly (empty) -> "" (never raises)
    (root / "cycle-log.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    cat = root / CAT
    cat.mkdir(parents=True, exist_ok=True)
    assert last_signal_check(root, cat) == ""


import datetime as dt
from gpu_agent.dashboard.brief_model import (
    build_brief_model, counterweight_ids, signal_strip)

TODAY = dt.date(2026, 7, 16)


def _finding(fid, mag, statement, observed="2026-07-01", captured="2026-07-06T00:00:00Z",
             indicator="D2", kind="measured", value={"number": 1.0, "unit": "pct"}):
    return {"id": fid, "magnitude": mag, "statement": statement,
            "observedAt": observed, "capturedAt": captured,
            "indicatorId": indicator, "kind": kind, "value": value, "trend": "rising",
            "evidence": [{"tier": "primary", "source": "src"}]}


def test_signal_strip_biggest_new_finding_per_revision(tmp_path):
    cat = tmp_path / "c"
    cat.mkdir()
    f1 = _finding("a", 2, "First sentence. Second.", captured="2026-07-02T09:00:00Z")
    f2 = _finding("b", 3, "Big mover statement.", captured="2026-07-14T09:00:00Z")
    (cat / "2026-07-v1.json").write_text(json.dumps({"asOf": "2026-07",
        "findings": [f1]}), encoding="utf-8")
    (cat / "2026-07-v2.json").write_text(json.dumps({"asOf": "2026-07",
        "findings": [f1, f2]}), encoding="utf-8")
    strip = signal_strip(cat)
    assert [e["date"] for e in strip] == ["2026-07-14", "2026-07-02"]
    assert strip[0]["text"] == "Big mover statement." and strip[0]["source"] == "src"
    assert strip[1]["text"] == "First sentence."


def test_counterweight_ids_maps_risk_thesis_evidence():
    entries = [{"title": "Circularity", "lens": "risk",
                "findingIds": ["f9"], "status": "registered"},
               {"title": "Demand", "lens": "demand", "findingIds": ["f1"]}]
    assert counterweight_ids(entries) == {"f9": "Circularity"}


def test_build_brief_model_assembles(tmp_path, monkeypatch):
    root = tmp_path / "store"
    cat = root / "chips.merchant-gpu"
    cat.mkdir(parents=True)
    monthly = {"asOf": "2026-07", "narrative": "The story.",
               "categoryStatus": {"rating": "Strong", "direction": "steady",
                                  "reason": "Supply caps it. More.",
                                  "constraintLabel": "HBM supply"},
               "dimensionRatings": {"momentum": {
                   "rating": "Very strong", "direction": "improving",
                   "confidence": {"level": "high"},
                   "rationale": "First reason. Extra."}},
               "dimensionStatus": {"momentum": {"confidenceCap": None}},
               "findings": [_finding("a", 3, "NVIDIA revenue was $75.2B.")],
               "sources": []}
    (cat / "2026-07-v1.json").write_text(json.dumps(monthly), encoding="utf-8")
    (root / "cycle-log.json").write_text(json.dumps(
        {"capturedAt": "2026-07-15T10:00:00Z"}), encoding="utf-8")
    m = build_brief_model("chips.merchant-gpu", root, TODAY)
    assert m["month_label"] == "July 2026" and m["revision"] == 1
    assert m["status"]["constraint"] == "HBM supply"
    assert m["last_check"] == "2026-07-15" and m["stale"] is False
    assert m["dimensions"][0]["sentence"] == "First reason."
    assert m["agenda"] and m["agenda"][0]["display"]           # slot filled
    assert m["evidence"]["n"] == 1 and m["evidence"]["primary"] == 1
    stale = build_brief_model("chips.merchant-gpu", root, dt.date(2026, 7, 25))
    assert stale["stale"] is True


def test_build_brief_model_defensive_on_missing_and_corrupt(tmp_path):
    import datetime as dt
    root = tmp_path / "store"
    root.mkdir()
    # missing category dir -> build_brief_model never raises
    m = build_brief_model("chips.merchant-gpu", root, dt.date(2026, 7, 16))
    assert m["strip"] == [] and m["agenda"] == [] and m["revision"] == 0
    # corrupt monthly: non-dict findings items + non-dict dimensionRatings value -> no raise
    cat = root / "chips.merchant-gpu"
    cat.mkdir()
    (cat / "2026-07-v1.json").write_text(json.dumps({
        "asOf": "2026-07", "narrative": "n",
        "categoryStatus": {"rating": "Strong"},
        "findings": ["not-a-dict", 5, None,
                     {"id": "a", "magnitude": 1, "statement": "S.",
                      "observedAt": "2026-07-01", "capturedAt": "2026-07-02T00:00:00Z",
                      "indicatorId": "D2", "kind": "measured",
                      "value": {"number": 1.0, "unit": "pct"},
                      "evidence": [{"tier": "primary", "source": "x"}]}],
        "dimensionRatings": {"momentum": "not-a-dict",
                             "moat": {"rating": "Mixed", "direction": "steady",
                                      "rationale": "R."}},
        "dimensionStatus": {}}), encoding="utf-8")
    m2 = build_brief_model("chips.merchant-gpu", root, dt.date(2026, 7, 16))
    assert m2["evidence"]["n"] == 1 and m2["evidence"]["primary"] == 1
    assert [d["name"] for d in m2["dimensions"]] == ["moat"]


def test_signal_strip_and_model_defensive_on_corrupt_multi_revision(tmp_path):
    import datetime as dt
    root = tmp_path / "store"
    cat = root / "chips.merchant-gpu"
    cat.mkdir(parents=True)
    good = {"id": "a", "magnitude": 2, "statement": "Real mover.",
            "observedAt": "2026-07-01", "capturedAt": "2026-07-02T00:00:00Z"}
    # two revisions: v1 findings array holds non-dict junk; v2 findings is a non-list
    # scalar. signal_strip (multi-revision path) must not raise.
    (cat / "2026-07-v1.json").write_text(json.dumps(
        {"asOf": "2026-07", "findings": ["junk", 5, good]}), encoding="utf-8")
    (cat / "2026-07-v2.json").write_text(json.dumps(
        {"asOf": "2026-07", "findings": 99}), encoding="utf-8")
    strip = signal_strip(cat)
    assert any(e["text"] == "Real mover." for e in strip)
    # full assembly also never raises on this store
    m = build_brief_model("chips.merchant-gpu", root, dt.date(2026, 7, 16))
    assert isinstance(m["strip"], list)


def test_first_sentence_skips_common_abbreviations():
    from gpu_agent.dashboard.brief_model import _first_sentence
    assert _first_sentence("NVIDIA will contribute $485 billion to U.S. buyers. More.") \
        == "NVIDIA will contribute $485 billion to U.S. buyers."
    assert _first_sentence("Growth, e.g. in HBM, is strong. Next.") \
        == "Growth, e.g. in HBM, is strong."
    assert _first_sentence("Revenue set a record. The next quarter guides up.") \
        == "Revenue set a record."


def test_first_n_sentences_takes_two():
    from gpu_agent.dashboard.brief_model import first_n_sentences
    t = "Demand is at record levels. The gap is narrowing. A third point."
    assert first_n_sentences(t, 2) == "Demand is at record levels. The gap is narrowing."


def test_first_n_sentences_short_input_returns_all():
    from gpu_agent.dashboard.brief_model import first_n_sentences
    assert first_n_sentences("Only one here.", 2) == "Only one here."


def test_first_n_sentences_empty():
    from gpu_agent.dashboard.brief_model import first_n_sentences
    assert first_n_sentences("", 2) == "" and first_n_sentences(None, 2) == ""


from gpu_agent.dashboard.brief_model import chart_series


def _rev(cat, name, dmi, smi):
    (cat / name).write_text(json.dumps({
        "asOf": name[:7], "demandSupply": {"dmiContribution": dmi, "smiContribution": smi},
        "findings": []}), encoding="utf-8")


def test_chart_series_orders_and_limits(tmp_path):
    cat = tmp_path / "store" / CAT; cat.mkdir(parents=True)
    _rev(cat, "2026-07-v1.json", 1.0, -0.2)
    _rev(cat, "2026-07-v2.json", 1.5, -0.1)
    _rev(cat, "2026-07-v3.json", 2.0, 0.1)
    (cat / "2026-07-05-v1.json").write_text(json.dumps({"demandSupply": {}, "findings": []}), encoding="utf-8")  # daily excluded
    s = chart_series(cat, limit=2)
    assert s["demand"] == [1.5, 2.0]        # last 2, chronological
    assert s["supply"] == [-0.1, 0.1]
    assert s["labels"] == ["2026-07-v2", "2026-07-v3"]


def test_chart_series_missing_dir_is_empty(tmp_path):
    s = chart_series(tmp_path / "nope")
    assert s == {"labels": [], "demand": [], "supply": []}
