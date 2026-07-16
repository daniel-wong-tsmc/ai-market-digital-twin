import json
from gpu_agent.dashboard.agenda import AGENDA_REGISTRY_PATH, format_value, load_slots
from gpu_agent.dashboard.agenda import Candidate, candidates_for_slot, read_series


def test_load_slots_real_registry():
    slots = load_slots()
    assert [s["id"] for s in slots] == [
        "demand-durability", "binding-constraint", "customer-mix",
        "end-market-economics", "demand-quality"]
    for s in slots:
        assert s["label"] and s["question"] and s["indicators"]


def test_load_slots_custom_path(tmp_path):
    p = tmp_path / "slots.json"
    p.write_text(json.dumps({"slots": [
        {"id": "x", "label": "X", "question": "q?", "indicators": ["a"]}]}),
        encoding="utf-8")
    assert load_slots(str(p))[0]["id"] == "x"


def test_format_value_units():
    assert format_value(75.2, "USD_B") == "$75.2B"
    assert format_value(75.0, "pct") == "75%"
    assert format_value(68.8, "pct_yoy") == "+68.8% YoY"
    assert format_value(-50.0, "pct_yoy") == "-50% YoY"
    assert format_value(6.69, "USD_per_hr") == "$6.69/hr"
    assert format_value(210000, "units") == "210,000 units"
    assert format_value(3.0, "widgets") == "3 widgets"   # unknown unit: honest fallback


SLOT = {"id": "demand-durability", "label": "Demand durability",
        "question": "q?", "indicators": ["D2", "odmMonthlyAiRevenue"]}

F_MEASURED = {"indicatorId": "D2", "kind": "measured",
              "value": {"number": 75.2, "unit": "USD_B"}, "trend": "rising",
              "observedAt": "2026-07-01", "magnitude": 3,
              "statement": "NVIDIA Q1 FY2027 Data Center revenue was a record $75.2 billion.",
              "evidence": [{"tier": "primary", "source": "NVIDIA IR"}]}
F_OBSERVED = {"indicatorId": "D2", "kind": "observed", "value": None,
              "trend": "rising", "observedAt": "2026-07-02", "magnitude": 2,
              "statement": "prose only", "evidence": []}
F_OTHER_IND = dict(F_MEASURED, indicatorId="S10")

SERIES_ROW = {"indicatorId": "odmMonthlyAiRevenue", "period": "2026-06",
              "value": 68.788, "unit": "pct_yoy", "publishedAt": "2026-07-10",
              "source": {"title": "TWSE MOPS monthly revenue summary"},
              "estimateGrade": False}
SERIES_PRIOR = dict(SERIES_ROW, period="2026-05", value=50.0, publishedAt="2026-06-10")


def test_candidates_measured_finding_only():
    got = candidates_for_slot(SLOT, [F_MEASURED, F_OBSERVED, F_OTHER_IND], {})
    assert len(got) == 1
    c = got[0]
    assert (c.indicator_id, c.display, c.trend_word, c.tier, c.magnitude) == \
        ("D2", "$75.2B", "rising", "primary", 3)
    assert c.observed_at == "2026-07-01" and c.source_name == "NVIDIA IR"


def test_candidates_series_newest_row_with_trend_from_prior():
    got = candidates_for_slot(SLOT, [], {"odmMonthlyAiRevenue": [SERIES_PRIOR, SERIES_ROW]})
    assert len(got) == 1
    c = got[0]
    assert c.display == "+68.788% YoY" and c.trend_word == "rising"
    assert c.observed_at == "2026-07-10" and c.tier == "secondary"


def test_read_series_reads_only_requested_files(tmp_path):
    import json
    d = tmp_path / "series"
    d.mkdir()
    (d / "a.jsonl").write_text(json.dumps({"indicatorId": "a", "value": 1}) + "\n",
                               encoding="utf-8")
    (d / "b.jsonl").write_text("{}\n", encoding="utf-8")
    rows = read_series(d, {"a", "missing"})
    assert set(rows) == {"a"} and rows["a"][0]["value"] == 1
