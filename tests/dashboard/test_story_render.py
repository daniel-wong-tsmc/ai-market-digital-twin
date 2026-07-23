import json
from gpu_agent.dashboard.story_render import evidence_json, render_evidence_panel

EV = {"kpi:x": {"title": "X: 1 — says who?", "claim_text": "X measures x.",
                "findings": [{"source": "S", "date": "2026-06-01",
                               "take": "t", "url": "https://s.example/a"}],
                "series": [1.0, 2.0], "explore": "appendix.html"}}


def test_evidence_json_blob_escapes_lt():
    blob = evidence_json({"k": {"title": "<script>alert(1)</script>"}})
    assert 'id="ev-data"' in blob and "<script>alert" not in blob.split(">", 1)[1]
    body = blob.split(">", 1)[1].rsplit("<", 1)[0]
    assert json.loads(body)["k"]["title"] == "<script>alert(1)</script>"


def test_panel_script_contract():
    js = render_evidence_panel()
    assert "window.openEV" in js and "window.closeEV" in js
    assert "encodeURI(" in js               # F100 XSS regression carry-over
    assert "data-ev" in js                  # delegated trigger
    assert "Escape" in js                   # keyboard close
    assert js.count("<script>") == 1 and js.count("</script>") == 1
