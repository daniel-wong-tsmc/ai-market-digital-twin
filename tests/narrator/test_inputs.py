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
