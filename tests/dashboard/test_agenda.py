import json
from gpu_agent.dashboard.agenda import AGENDA_REGISTRY_PATH, format_value, load_slots


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
