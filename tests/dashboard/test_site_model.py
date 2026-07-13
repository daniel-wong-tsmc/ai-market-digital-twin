import json
import shutil
from pathlib import Path

from gpu_agent.dashboard.site_model import build_site_model, read_implication

FIX = "tests/dashboard/fixtures"
CAT = "chips.merchant-gpu"


def _model(price_fn=lambda d: {}):
    return build_site_model(CAT, FIX, work_dir="work-nonexistent",
                            plain_path=f"{FIX}/plain-2026-07-06.json", price_fn=price_fn)


def test_model_has_the_f95_extras():
    m = _model()
    assert m["as_of"] == m["latest_date"]
    assert m["alert"].keys() >= {"color", "prior", "raw", "triggers"}
    assert m["contributions"], "fixture must yield contribution rows"
    topics = [w["topic"] for w in m["why"]]
    assert topics[:1] == ["alert"] and {"demand", "supply", "gap", "trust"} <= set(topics)
    for w in m["why"]:
        assert w["text"].strip()


def test_featured_with_stub_price_and_reason_present():
    prices = {"H100": 2.31}
    m = _model(price_fn=lambda d: prices)
    f = m["featured"]
    assert f is not None and f["metric_id"] in {"gpu-rent-h100", "gap-score",
                                                "demand-momentum", "supply-momentum"}
    assert f["reason_text"] and f["reason_code"] in {"alert-rule", "biggest-move", "priority"}
    assert any(w["topic"] == "featured" for w in m["why"])


def test_no_price_data_still_selects_an_index_metric():
    f = _model()["featured"]
    assert f is not None and f["metric_id"] != "gpu-rent-h100"


def test_gap_why_shows_the_equation():
    m = _model()
    gap = next(w for w in m["why"] if w["topic"] == "gap")
    ds = m["demand_supply"]
    assert f'{ds["dmi"]:+.2f}' in gap["text"] and f'{ds["sdgi"]:+.2f}' in gap["text"]


def test_implication_read_defensively(tmp_path):
    root = tmp_path / "store"
    (root / "implications" / CAT).mkdir(parents=True)
    art = {"asOf": "2026-07-06", "lines": [
        {"text": "Watch CoWoS allocation notes in earnings calls.",
         "watchItem": "cowosSoicAllocation", "dimensions": ["bottleneck"]},
        {"watchItem": "waferStartsByNode"},
        "A bare string line survives too."]}
    (root / "implications" / CAT / "2026-07-06.json").write_text(
        json.dumps(art), encoding="utf-8")
    got = read_implication(root, CAT, "2026-07-06")
    assert got == {"lines": ["Watch CoWoS allocation notes in earnings calls.",
                             "waferStartsByNode",
                             "A bare string line survives too."]}
    assert read_implication(root, CAT, "2026-07-05") is None
    assert read_implication(tmp_path / "nowhere", CAT, "2026-07-06") is None


def test_single_run_store_degrades_no_prior(tmp_path):
    cat_dir = tmp_path / "store" / CAT
    cat_dir.mkdir(parents=True)
    shutil.copy(Path(FIX) / "2026-07-06-v1.json", cat_dir / "2026-07-06-v1.json")
    m = build_site_model(CAT, str(cat_dir), work_dir="work-nonexistent",
                         plain_path=None, price_fn=lambda d: {})
    assert m["featured"]["reason_code"] == "priority"
    assert m["alert"]["prior"] is None
