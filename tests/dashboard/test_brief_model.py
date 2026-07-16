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
