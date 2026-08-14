import json
from pathlib import Path
import jsonschema

SCHEMA = Path("web/schema/dashboard.schema.json")

def _minimal_payload():
    ref = {"title": "AMD Q2 2026 results", "outlet": "AMD investor relations",
           "url": "https://ir.amd.com/x", "date": "2026-08-04", "tier": "primary"}
    return {
        "schemaVersion": "1.2", "categoryId": "chips.merchant-gpu", "asOf": "2026-08-05",
        "verdict": {"question": "q", "answer": "a", "chip": {"label": "Gap narrowing", "direction": "narrowing"},
                     "confidence": "c", "soWhat": "s", "sources": [ref]},
        "gapChart": {"points": [{"date": "2026-07-03", "demand": 0.6, "supply": -0.4}],
                      "annotation": {"date": "2026-07-28", "label": "Widest gap so far"},
                      "caption": "cap", "sources": [ref]},
        "bullets": [
            {"date": "2026-08-05", "text": "t", "storyHref": "story/", "chart": None,
             "noChartReason": {"reason": "No published number behind this yet.",
                                "cause": "no-published-number"},
             "sources": [ref]}] * 3,
        "dimensions": [{"id": f"d{i}", "plainName": "n", "ratingWord": "Strained", "tone": "bad",
                         "direction": "flat", "confidence": "medium", "summary": "s",
                         "reasoning": "r", "evidence": [ref]} for i in range(6)],
        "footerLinks": [{"label": "Every finding", "href": "findings/"}],
        "issues": {"open": [], "resolved": []},
    }


def _open_issue(ref):
    return {
        "id": "constraint-hbm4-stacked-memory-supply",
        "title": "HBM4 stacked-memory supply",
        "status": "worsened",
        "assessedAsOf": "2026-08-10",
        "trackedSince": "2026-08-01",
        "worsenedCount": 3,
        "checkCount": 5,
        "reasoning": "Supply remains tight.",
        "sources": [ref],
        "history": [{"asOf": "2026-08-09", "status": "unchanged"}],
    }


def _resolved_issue():
    return {
        "id": "dim-competitiveStructure",
        "title": "Competitive structure",
        "resolvedAsOf": "2026-08-01",
        "finalNote": "Improved for five straight checks.",
    }

def _chart(ref):
    return {"form": "columns", "title": "t", "caption": "c", "unit": "USD bn",
            "points": [{"label": "Q1", "value": 1.0, "hollow": False, "sourceUrl": None}],
            "source": ref, "researched": False}

def test_minimal_payload_validates():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(_minimal_payload(), schema)

def test_bullet_chart_xor_reason():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    bad = _minimal_payload()
    bad["bullets"][0]["chart"] = _chart(bad["bullets"][0]["sources"][0])
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

def test_object_form_reason_validates():
    # The 1.1 shape: noChartReason is {reason, cause}, cause a fixed enum.
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(_minimal_payload(), schema)

def test_bare_string_reason_rejected():
    # STRICT: the app never accepts the old 1.0 bare-string shape. No
    # compatibility branch is added -- this is a deliberate, user-decided
    # break, not an oversight.
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    bad = _minimal_payload()
    bad["bullets"][0]["noChartReason"] = "No published number."
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)

def test_cause_enum_enforced():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    bad = _minimal_payload()
    bad["bullets"][0]["noChartReason"]["cause"] = "something-else"
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)

def test_chart_researched_field_is_boolean_but_its_absence_is_allowed():
    # "researched defaults allowed" (brief): a chart that doesn't say
    # `researched` at all still validates -- every chart this lane's Python
    # side emits sets it explicitly to false, but the field is additive and
    # optional at the schema level, not a required key.
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    good = _minimal_payload()
    good["bullets"][0]["chart"] = _chart(good["bullets"][0]["sources"][0])
    good["bullets"][0]["noChartReason"] = None
    jsonschema.validate(good, schema)

    missing = _minimal_payload()
    chart = _chart(missing["bullets"][0]["sources"][0])
    del chart["researched"]
    missing["bullets"][0]["chart"] = chart
    missing["bullets"][0]["noChartReason"] = None
    jsonschema.validate(missing, schema)  # still valid -- researched is optional

    wrong_type = _minimal_payload()
    chart = _chart(wrong_type["bullets"][0]["sources"][0])
    chart["researched"] = "yes"
    wrong_type["bullets"][0]["chart"] = chart
    wrong_type["bullets"][0]["noChartReason"] = None
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(wrong_type, schema)

def test_schema_version_is_1_2():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["properties"]["schemaVersion"]["const"] == "1.2"
    bad = _minimal_payload()
    bad["schemaVersion"] = "1.1"
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


# ---------------------------------------------------------------------------
# F115: the `issues` section is required, and its shapes are strict.
# ---------------------------------------------------------------------------

def test_payload_with_issues_section_validates():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    ref = {"title": "AMD Q2 2026 results", "outlet": "AMD investor relations",
           "url": "https://ir.amd.com/x", "date": "2026-08-04", "tier": "primary"}
    good = _minimal_payload()
    good["issues"] = {"open": [_open_issue(ref)], "resolved": [_resolved_issue()]}
    jsonschema.validate(good, schema)


def test_payload_without_issues_is_rejected():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    bad = _minimal_payload()
    del bad["issues"]
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_unknown_key_inside_an_open_issue_is_rejected():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    ref = {"title": "AMD Q2 2026 results", "outlet": "AMD investor relations",
           "url": "https://ir.amd.com/x", "date": "2026-08-04", "tier": "primary"}
    bad = _minimal_payload()
    issue = _open_issue(ref)
    issue["extraField"] = "not allowed"
    bad["issues"] = {"open": [issue], "resolved": []}
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_open_issue_status_enum_includes_not_assessed():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    ref = {"title": "AMD Q2 2026 results", "outlet": "AMD investor relations",
           "url": "https://ir.amd.com/x", "date": "2026-08-04", "tier": "primary"}
    good = _minimal_payload()
    issue = _open_issue(ref)
    issue["status"] = "not-assessed"
    good["issues"] = {"open": [issue], "resolved": []}
    jsonschema.validate(good, schema)


def test_open_issue_status_rejects_unknown_value():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    ref = {"title": "AMD Q2 2026 results", "outlet": "AMD investor relations",
           "url": "https://ir.amd.com/x", "date": "2026-08-04", "tier": "primary"}
    bad = _minimal_payload()
    issue = _open_issue(ref)
    issue["status"] = "regressed"
    bad["issues"] = {"open": [issue], "resolved": []}
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_issue_history_entries_are_strict_asof_status_objects():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    ref = {"title": "AMD Q2 2026 results", "outlet": "AMD investor relations",
           "url": "https://ir.amd.com/x", "date": "2026-08-04", "tier": "primary"}
    bad = _minimal_payload()
    issue = _open_issue(ref)
    issue["history"] = [{"asOf": "2026-08-09", "status": "unchanged", "extra": "no"}]
    bad["issues"] = {"open": [issue], "resolved": []}
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_resolved_issue_unknown_key_is_rejected():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    bad = _minimal_payload()
    resolved = _resolved_issue()
    resolved["extra"] = "no"
    bad["issues"] = {"open": [], "resolved": [resolved]}
    import pytest
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
