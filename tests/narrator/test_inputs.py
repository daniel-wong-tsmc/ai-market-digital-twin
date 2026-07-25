import datetime as dt
import json
from gpu_agent.narrator.inputs import build_narrator_inputs
from gpu_agent.narrator.store import StoryStore
from tests.narrator.test_store import _art, CAT
from tests.dashboard.test_story_model import _store   # Phase A fixture builder


def test_inputs_assembled(tmp_path):
    store = _store(tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    (run / "blobs.json").write_text(json.dumps({"rounds": 1, "skipped": [],
        "blobs": [{"source": "Reuters", "url": "https://r.example/hbm",
                    "date": "2026-07-23", "entity": "market", "content": "x"},
                   {"source": "sketch", "url": "http://insecure.example/x",
                    "date": "2026-07-23", "entity": "m", "content": "y"}]}),
        encoding="utf-8")
    StoryStore(store).write(_art("2026-07-22", headline="Yesterday's H"))
    inp = build_narrator_inputs(CAT, store, dt.date(2026, 7, 23), run)
    assert inp["storyDate"] == "2026-07-23"
    assert inp["scorecard"]["asOf"] == "2026-07"
    assert any(f["id"] == "f-1" for f in inp["findings"])
    assert any(s["indicatorId"] == "gpuRentalOnDemand" for s in inp["seriesPool"])
    assert inp["memory"]["yesterday"]["headline"] == "Yesterday's H"
    assert [d["url"] for d in inp["docPool"]] == ["https://r.example/hbm"]  # https only
    assert "2026-07" in inp["gapMonths"]


def test_inputs_no_run_dir_no_memory(tmp_path):
    inp = build_narrator_inputs(CAT, _store(tmp_path), dt.date(2026, 7, 23), None)
    assert inp["docPool"] == [] and inp["memory"]["yesterday"] is None


def test_findings_and_docpool_carry_freshness_weight(tmp_path):
    store = _store(tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    (run / "blobs.json").write_text(json.dumps({"rounds": 1, "skipped": [],
        "blobs": [{"source": "Reuters", "url": "https://r.example/hbm",
                    "date": "2026-07-23", "entity": "market", "content": "x"}]}),
        encoding="utf-8")
    inp = build_narrator_inputs(CAT, store, dt.date(2026, 7, 23), run)
    for f in inp["findings"]:
        assert isinstance(f["freshnessWeight"], float)
    for d in inp["docPool"]:
        assert isinstance(d["freshnessWeight"], float)


def test_finding_freshness_weight_is_max_over_evidence():
    from gpu_agent.narrator.inputs import _finding_trim
    from gpu_agent.freshness import load_freshness

    cfg = load_freshness()
    today = dt.date(2026, 7, 23)
    f = {
        "id": "f-x",
        "statement": "s",
        "evidence": [
            {"source": "Old", "url": "https://example.com/old", "date": "2026-06-01", "tier": "1"},
            {"source": "New", "url": "https://example.com/new", "date": "2026-07-22", "tier": "1"},
        ],
    }
    trimmed = _finding_trim(f, today, cfg)
    # freshest evidence (2026-07-22, age 1 day) should dominate over the
    # much older 2026-06-01 evidence -- max-over-evidence, not min or average.
    assert trimmed["freshnessWeight"] > 0.5
