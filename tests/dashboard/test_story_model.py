import datetime as dt
import json
from pathlib import Path
from gpu_agent.dashboard.story_model import build_story_model

CAT = "chips.merchant-gpu"


def _store(tmp_path, dmi_smi=((1.0, 0.5), (2.0, 0.2))):
    cat = tmp_path / CAT
    cat.mkdir(parents=True)
    months = ["2026-06", "2026-07"]
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
