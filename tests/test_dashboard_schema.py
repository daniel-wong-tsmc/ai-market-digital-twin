import json
from pathlib import Path
import jsonschema

SCHEMA = Path("web/schema/dashboard.schema.json")

def _minimal_payload():
    ref = {"title": "AMD Q2 2026 results", "outlet": "AMD investor relations",
           "url": "https://ir.amd.com/x", "date": "2026-08-04", "tier": "primary"}
    return {
        "schemaVersion": "1.0", "categoryId": "chips.merchant-gpu", "asOf": "2026-08-05",
        "verdict": {"question": "q", "answer": "a", "chip": {"label": "Gap narrowing", "direction": "narrowing"},
                     "confidence": "c", "soWhat": "s", "sources": [ref]},
        "gapChart": {"points": [{"date": "2026-07-03", "demand": 0.6, "supply": -0.4}],
                      "annotation": {"date": "2026-07-28", "label": "Widest gap so far"},
                      "caption": "cap", "sources": [ref]},
        "bullets": [
            {"date": "2026-08-05", "text": "t", "storyHref": "story/", "chart": None,
             "noChartReason": "No published number.", "sources": [ref]}] * 3,
        "dimensions": [{"id": f"d{i}", "plainName": "n", "ratingWord": "Strained", "tone": "bad",
                         "direction": "flat", "confidence": "medium", "summary": "s",
                         "reasoning": "r", "evidence": [ref]} for i in range(6)],
        "footerLinks": [{"label": "Every finding", "href": "findings/"}],
    }

def test_minimal_payload_validates():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(_minimal_payload(), schema)

def test_bullet_chart_xor_reason():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    bad = _minimal_payload()
    bad["bullets"][0]["chart"] = {"form": "columns", "title": "t", "caption": "c", "unit": "USD bn",
                                    "points": [{"label": "Q1", "value": 1.0, "hollow": False, "sourceUrl": None}],
                                    "source": bad["bullets"][0]["sources"][0]}
    # chart set AND noChartReason set -> invalid
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)

def test_wrong_bullet_count_fails():
    import pytest
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    bad = _minimal_payload(); bad["bullets"] = bad["bullets"][:2]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
